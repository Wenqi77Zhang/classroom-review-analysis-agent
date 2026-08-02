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
    return $process
}

try {
    $processes += Start-LoggedProcess "backend" $python `
        @("-m", "uvicorn", "--factory", "backend.app.main:create_app", "--host", "127.0.0.1", "--port", "8000") $root
    $processes += Start-LoggedProcess "frontend" "npm.cmd" `
        @("run", "dev", "--", "--hostname", "127.0.0.1") $frontend
    $processes += Start-LoggedProcess "worker" $python `
        @("scripts/run_service_loop.py", "worker") $root
    $processes += Start-LoggedProcess "agent" $python `
        @("scripts/run_service_loop.py", "agent") $root
    Write-Host "前端、后端、Worker 与 Agent 已启动。日志位于 logs/；按 Ctrl+C 停止。"
    Wait-Process -Id ($processes | ForEach-Object Id)
}
finally {
    foreach ($process in $processes) {
        if (-not $process.HasExited) {
            & taskkill.exe /PID $process.Id /T /F 2>$null | Out-Null
        }
    }
}
