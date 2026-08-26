[CmdletBinding()]
param(
    [switch]$PreflightOnly
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$frontendDirectory = Join-Path $repositoryRoot "frontend"
$frontendProcess = $null
$tunnelProcess = $null
$tunnelOrigin = $null
$tunnelLog = $null
$previousAccessCode = [Environment]::GetEnvironmentVariable(
    "TEAM_TUNNEL_ACCESS_CODE",
    "Process"
)
$previousInstanceId = [Environment]::GetEnvironmentVariable(
    "TEAM_TUNNEL_INSTANCE_ID",
    "Process"
)

function Restore-ProcessEnvironment {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [AllowNull()]
        [string]$PreviousValue
    )

    if ($null -eq $PreviousValue) {
        Remove-Item -LiteralPath "Env:$Name" -ErrorAction SilentlyContinue
    }
    else {
        [Environment]::SetEnvironmentVariable($Name, $PreviousValue, "Process")
    }
}

function Assert-CommandAvailable {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [string]$InstallHint
    )

    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if ($null -eq $command) {
        throw "未找到 $Name。$InstallHint"
    }
    return $command
}

function Resolve-Cloudflared {
    $command = Get-Command "cloudflared.exe" -ErrorAction SilentlyContinue
    if ($null -ne $command) {
        return $command.Source
    }

    $knownInstallPath = "C:\Program Files (x86)\cloudflared\cloudflared.exe"
    if (Test-Path -LiteralPath $knownInstallPath) {
        return $knownInstallPath
    }

    throw ("未找到 cloudflared。请运行：" +
        "winget install --id Cloudflare.cloudflared --exact")
}

try {
    $npm = Assert-CommandAvailable `
        -Name "npm.cmd" `
        -InstallHint "请先按 ../docs/product-and-technology-handbook.md 安装项目指定 Node.js。"
    $node = Assert-CommandAvailable `
        -Name "node.exe" `
        -InstallHint "请先按 ../docs/product-and-technology-handbook.md 安装项目指定 Node.js。"
    $cloudflaredPath = Resolve-Cloudflared

    $backendPort = 8100
    $envFile = Join-Path $repositoryRoot ".env"
    if (Test-Path -LiteralPath $envFile) {
        $portLine = Get-Content -LiteralPath $envFile -Encoding UTF8 |
            Where-Object { $_ -match '^\s*BACKEND_PORT\s*=' } |
            Select-Object -Last 1
        if ($portLine) {
            $candidate = ($portLine -split '=', 2)[1].Trim()
            $parsedPort = 0
            if ([int]::TryParse($candidate, [ref]$parsedPort)) {
                $backendPort = $parsedPort
            }
        }
    }
    try {
        $live = Invoke-RestMethod `
            -Uri "http://127.0.0.1:$backendPort/health" `
            -Method Get `
            -TimeoutSec 5
    }
    catch {
        throw "本地后端进程不可达。请先启动 $backendPort 端口的课堂后端。"
    }
    if ($live.status -ne "ok") {
        throw "本地端口存在服务，但不是可用的课堂后端。"
    }
    try {
        $ready = Invoke-RestMethod `
            -Uri "http://127.0.0.1:$backendPort/health/ready" `
            -Method Get `
            -TimeoutSec 15
    }
    catch {
        throw "课堂后端在线，但数据库或对象存储尚未就绪；为避免公网用户上传失败，未开放入口。"
    }
    if ($ready.status -ne "ready") {
        throw "后端 /health/ready 未返回 ready，不能创建团队联调入口。"
    }

    if (-not (Test-Path -LiteralPath (Join-Path $frontendDirectory "node_modules"))) {
        throw "前端依赖尚未安装。请先在 frontend 目录运行 npm ci。"
    }

    $accessCodeBytes = New-Object byte[] 12
    [Security.Cryptography.RandomNumberGenerator]::Fill($accessCodeBytes)
    $accessCode = [Convert]::ToHexString($accessCodeBytes)
    $instanceIdBytes = New-Object byte[] 16
    [Security.Cryptography.RandomNumberGenerator]::Fill($instanceIdBytes)
    $instanceId = [Convert]::ToHexString($instanceIdBytes)
    [Environment]::SetEnvironmentVariable(
        "TEAM_TUNNEL_ACCESS_CODE",
        $accessCode,
        "Process"
    )
    [Environment]::SetEnvironmentVariable(
        "TEAM_TUNNEL_INSTANCE_ID",
        $instanceId,
        "Process"
    )

    Write-Host "正在构建生产版前端（尚未开放公网）……"
    & $npm.Source run build --prefix $frontendDirectory
    if ($LASTEXITCODE -ne 0) {
        throw "前端生产构建失败，未创建公网入口。"
    }

    $portReservation = [Net.Sockets.TcpListener]::new(
        [Net.IPAddress]::Loopback,
        0
    )
    $portReservation.Start()
    $frontendPort = ([Net.IPEndPoint]$portReservation.LocalEndpoint).Port
    $portReservation.Stop()

    $nextCli = Join-Path $frontendDirectory "node_modules\next\dist\bin\next"
    $frontendProcess = Start-Process `
        -FilePath $node.Source `
        -ArgumentList @($nextCli, "start", "-H", "127.0.0.1", "-p", $frontendPort) `
        -WorkingDirectory $frontendDirectory `
        -WindowStyle Hidden `
        -PassThru

    $frontendReady = $false
    foreach ($attempt in 1..30) {
        if ($frontendProcess.HasExited) {
            throw "生产版前端启动失败。请在 frontend 目录手动运行 npm start 查看错误。"
        }
        try {
            $response = Invoke-WebRequest `
                -Uri "http://127.0.0.1:$frontendPort/api/team-access" `
                -Method Get `
                -TimeoutSec 2 `
                -UseBasicParsing
            $probe = $response.Content | ConvertFrom-Json
            if (
                $response.StatusCode -eq 200 -and
                $probe.enabled -eq $true -and
                $probe.instanceId -eq $instanceId
            ) {
                $frontendReady = $true
                break
            }
        }
        catch {
            Start-Sleep -Milliseconds 500
        }
    }
    if (-not $frontendReady) {
        throw "生产版前端在等待时间内未就绪，未创建公网入口。"
    }

    if ($PreflightOnly) {
        Write-Host "预检通过：后端、生产版前端和访问码门禁均可启动；未创建公网入口。"
        return
    }

    Write-Host ""
    Write-Host "团队联调访问码（仅通过私聊发送，本次进程停止后失效）："
    Write-Host $accessCode -ForegroundColor Cyan
    Write-Host ""
    $tunnelLog = Join-Path ([IO.Path]::GetTempPath()) `
        ("classroom-review-tunnel-{0}.log" -f $instanceId)
    $tunnelProcess = Start-Process `
        -FilePath $cloudflaredPath `
        -ArgumentList @(
            "tunnel",
            "--url", "http://127.0.0.1:$frontendPort",
            "--logfile", $tunnelLog,
            "--loglevel", "info"
        ) `
        -UseNewEnvironment `
        -WindowStyle Hidden `
        -PassThru

    foreach ($attempt in 1..60) {
        if ($tunnelProcess.HasExited) {
            throw "cloudflared 异常退出。请检查网络、代理或 cloudflared 配置。"
        }
        if (Test-Path -LiteralPath $tunnelLog) {
            $logText = Get-Content -LiteralPath $tunnelLog -Raw -ErrorAction SilentlyContinue
            $match = [regex]::Match(
                $logText,
                'https://[a-z0-9-]+\.trycloudflare\.com',
                [Text.RegularExpressions.RegexOptions]::IgnoreCase
            )
            if ($match.Success) {
                $tunnelOrigin = $match.Value.ToLowerInvariant()
                break
            }
        }
        Start-Sleep -Seconds 1
    }
    if (-not $tunnelOrigin) {
        throw "60 秒内没有取得 Quick Tunnel HTTPS 地址，已停止且未修改 B2 CORS。"
    }

    $projectPython = Join-Path $repositoryRoot ".venv\Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $projectPython)) {
        throw "项目 .venv 不存在，无法安全配置本次 B2 CORS。"
    }
    $corsScript = Join-Path $PSScriptRoot "configure-team-tunnel-cors.py"
    & $projectPython $corsScript --env-file $envFile apply --origin $tunnelOrigin
    if ($LASTEXITCODE -ne 0) {
        throw "无法为本次精确 HTTPS 地址配置 B2 CORS，公网入口已停止。"
    }
    & $projectPython $corsScript --env-file $envFile verify --origin $tunnelOrigin
    if ($LASTEXITCODE -ne 0) {
        throw "B2 CORS 预检失败，公网入口已停止。"
    }

    Write-Host ""
    Write-Host "临时公网验收地址：" -NoNewline
    Write-Host $tunnelOrigin -ForegroundColor Cyan
    Write-Host "团队联调访问码（仅私聊发送，本次进程停止后失效）："
    Write-Host $accessCode -ForegroundColor Cyan
    Write-Host "B2 已只授权本次精确 HTTPS 地址；关闭入口时会自动撤销。"
    Write-Host "该地址仅用于短时验收，不是永久生产域名。按 Ctrl+C 关闭入口。"
    Write-Host ""

    Wait-Process -Id $tunnelProcess.Id
}
finally {
    if ($null -ne $tunnelProcess -and -not $tunnelProcess.HasExited) {
        & taskkill.exe /PID $tunnelProcess.Id /T /F *> $null
    }
    if ($tunnelOrigin) {
        $projectPython = Join-Path $repositoryRoot ".venv\Scripts\python.exe"
        $corsScript = Join-Path $PSScriptRoot "configure-team-tunnel-cors.py"
        if (
            (Test-Path -LiteralPath $projectPython) -and
            (Test-Path -LiteralPath $corsScript) -and
            (Test-Path -LiteralPath (Join-Path $repositoryRoot ".env"))
        ) {
            try {
                & $projectPython $corsScript `
                    --env-file (Join-Path $repositoryRoot ".env") remove
            }
            catch {
                Write-Warning "入口已关闭，但 B2 临时 CORS 撤销失败；请运行配置脚本 remove。"
            }
        }
    }
    if ($null -ne $frontendProcess -and -not $frontendProcess.HasExited) {
        & taskkill.exe /PID $frontendProcess.Id /T /F *> $null
    }
    if ($tunnelLog -and (Test-Path -LiteralPath $tunnelLog)) {
        Remove-Item -LiteralPath $tunnelLog -Force -ErrorAction SilentlyContinue
    }
    Restore-ProcessEnvironment `
        -Name "TEAM_TUNNEL_ACCESS_CODE" `
        -PreviousValue $previousAccessCode
    Restore-ProcessEnvironment `
        -Name "TEAM_TUNNEL_INSTANCE_ID" `
        -PreviousValue $previousInstanceId
}
