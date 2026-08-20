$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $root ".venv\Scripts\python.exe"
$frontend = Join-Path $root "frontend"
$logs = Join-Path $root "logs"
$envFile = Join-Path $root ".env"

if (-not (Test-Path -LiteralPath $python)) {
    throw "缺少根目录 .venv，请先运行 setup.ps1。"
}
if (-not (Test-Path -LiteralPath (Join-Path $frontend "node_modules"))) {
    throw "缺少 frontend/node_modules，请先运行 setup.ps1。"
}
if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) {
    throw "未找到 npm.cmd，请安装 README 指定的 Node.js 版本。"
}
if (-not (Test-Path -LiteralPath $envFile)) {
    throw "缺少 .env，请从 .env.example 复制并填写真实本地配置。"
}

foreach ($line in Get-Content -LiteralPath $envFile -Encoding UTF8) {
    $trimmed = $line.Trim()
    if (-not $trimmed -or $trimmed.StartsWith("#") -or -not $trimmed.Contains("=")) {
        continue
    }
    $name, $value = $trimmed.Split("=", 2)
    if (-not [Environment]::GetEnvironmentVariable($name.Trim(), "Process")) {
        [Environment]::SetEnvironmentVariable($name.Trim(), $value.Trim(), "Process")
    }
}

$required = @(
    "DATABASE_URL", "JWT_SECRET", "DEMO_ACCOUNT_PASSWORD",
    "WORKER_SERVICE_TOKEN", "AGENT_SERVICE_TOKEN",
    "LOCAL_MODEL_CHAT_COMPLETIONS_URL", "LOCAL_MODEL_NAME"
)
$missing = $required | Where-Object { -not [Environment]::GetEnvironmentVariable($_) }
if ($missing) {
    throw "以下必需环境变量尚未填写：$($missing -join ', ')"
}
if ($env:WORKER_SERVICE_TOKEN -eq $env:AGENT_SERVICE_TOKEN) {
    throw "WORKER_SERVICE_TOKEN 与 AGENT_SERVICE_TOKEN 必须不同。"
}

New-Item -ItemType Directory -Path $logs -Force | Out-Null
& $python "scripts/runtime_preflight.py"
if ($LASTEXITCODE -ne 0) {
    throw "运行配置校验失败；未启动任何服务。"
}
$processes = @()
$runtimeManifest = Join-Path $logs "runtime-processes.json"
$runtimeMutex = [System.Threading.Mutex]::new(
    $false,
    "Local\ClassroomReviewAnalysisAgent.Runtime"
)
$ownsRuntimeMutex = $false
try {
    $ownsRuntimeMutex = $runtimeMutex.WaitOne(0)
}
catch [System.Threading.AbandonedMutexException] {
    # 上一启动器被强制关闭时，系统会把互斥锁所有权交给当前进程并抛出此异常。
    $ownsRuntimeMutex = $true
}
if (-not $ownsRuntimeMutex) {
    $runtimeMutex.Dispose()
    throw "本项目已有一套服务正在运行。请回到原启动窗口使用，或先按 Ctrl+C 正常停止。"
}

function Stop-StaleRuntimeProcesses {
    if (-not (Test-Path -LiteralPath $runtimeManifest)) {
        return
    }
    try {
        $manifest = Get-Content -LiteralPath $runtimeManifest -Raw -Encoding UTF8 |
            ConvertFrom-Json
        foreach ($entry in @($manifest.services)) {
            $process = Get-Process -Id ([int]$entry.pid) -ErrorAction SilentlyContinue
            if (-not $process) {
                continue
            }
            # PID 会被系统复用；只有 PID 与启动时刻同时匹配，才可确认是上次遗留服务。
            if ($process.StartTime.ToUniversalTime().Ticks -eq [long]$entry.startTimeUtcTicks) {
                Write-Host "正在清理上次异常退出后遗留的 $($entry.name)，PID=$($entry.pid)"
                & taskkill.exe /PID $process.Id /T /F 2>$null | Out-Null
            }
        }
    }
    catch {
        Write-Warning "旧运行清单无法读取；为避免误杀其他进程，本次不自动清理。"
    }
    finally {
        Remove-Item -LiteralPath $runtimeManifest -Force -ErrorAction SilentlyContinue
    }
}

function Write-RuntimeManifest {
    $manifest = [ordered]@{
        root = $root
        startedAtUtc = [DateTime]::UtcNow.ToString("o")
        services = @(
            $processes | ForEach-Object {
                [ordered]@{
                    name = $_.ServiceName
                    pid = $_.Process.Id
                    startTimeUtcTicks = $_.Process.StartTime.ToUniversalTime().Ticks
                }
            }
        )
    }
    $manifest | ConvertTo-Json -Depth 4 |
        Set-Content -LiteralPath $runtimeManifest -Encoding UTF8
}

function Start-LoggedProcess {
    param(
        [string]$Name,
        [string]$FilePath,
        [string[]]$Arguments,
        [string]$WorkingDirectory
    )
    $process = Start-Process -FilePath $FilePath -ArgumentList $Arguments `
        -WorkingDirectory $WorkingDirectory -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $logs "$Name.log") `
        -RedirectStandardError (Join-Path $logs "$Name.err.log") -PassThru
    Write-Host "$Name 已启动，PID=$($process.Id)"
    return [pscustomobject]@{
        ServiceName = $Name
        Process = $process
    }
}

try {
    Stop-StaleRuntimeProcesses
    $processes += Start-LoggedProcess "backend" $python `
        @("-m", "uvicorn", "--factory", "backend.app.main:create_app", "--host", "127.0.0.1", "--port", "8000") $root
    Write-RuntimeManifest
    $processes += Start-LoggedProcess "frontend" "npm.cmd" `
        @("run", "dev", "--", "--hostname", "127.0.0.1") $frontend
    Write-RuntimeManifest
    $processes += Start-LoggedProcess "worker" $python `
        @("scripts/run_service_loop.py", "worker") $root
    Write-RuntimeManifest
    $processes += Start-LoggedProcess "agent" $python `
        @("scripts/run_service_loop.py", "agent") $root
    Write-RuntimeManifest
    Write-Host "前端、后端、Worker 与 Agent 已启动。日志位于 logs/；按 Ctrl+C 停止。"
    Wait-Process -Id ($processes | ForEach-Object { $_.Process.Id })
}
finally {
    foreach ($entry in $processes) {
        if (-not $entry.Process.HasExited) {
            & taskkill.exe /PID $entry.Process.Id /T /F 2>$null | Out-Null
        }
    }
    Remove-Item -LiteralPath $runtimeManifest -Force -ErrorAction SilentlyContinue
    if ($ownsRuntimeMutex) {
        $runtimeMutex.ReleaseMutex()
    }
    $runtimeMutex.Dispose()
}
