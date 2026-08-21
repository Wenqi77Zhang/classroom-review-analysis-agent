[CmdletBinding()]
param(
    [switch]$PreflightOnly
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$frontendDirectory = Join-Path $repositoryRoot "frontend"
$frontendProcess = $null
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
        $ready = Invoke-RestMethod `
            -Uri "http://127.0.0.1:$backendPort/health/ready" `
            -Method Get `
            -TimeoutSec 5
    }
    catch {
        throw "本地后端未就绪。请先启动 PostgreSQL、执行迁移并启动 $backendPort 端口后端。"
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
    Write-Host "下面将由 Cloudflare 输出随机 https://*.trycloudflare.com 地址。"
    Write-Host "该地址是临时测试入口，不是最终部署；关闭本窗口即停止服务。"
    Write-Host "首次用真实 B2 上传前，必须把这个精确 HTTPS 地址加入 Bucket CORS。"
    Write-Host "按 Ctrl+C 关闭入口。"
    Write-Host ""

    $tunnelProcess = Start-Process `
        -FilePath $cloudflaredPath `
        -ArgumentList @("tunnel", "--url", "http://127.0.0.1:$frontendPort") `
        -UseNewEnvironment `
        -NoNewWindow `
        -Wait `
        -PassThru
    if ($tunnelProcess.ExitCode -ne 0) {
        throw "cloudflared 异常退出。若提示 config.yml 冲突，请按统一环境文档处理。"
    }
}
finally {
    if ($null -ne $frontendProcess -and -not $frontendProcess.HasExited) {
        & taskkill.exe /PID $frontendProcess.Id /T /F *> $null
    }
    Restore-ProcessEnvironment `
        -Name "TEAM_TUNNEL_ACCESS_CODE" `
        -PreviousValue $previousAccessCode
    Restore-ProcessEnvironment `
        -Name "TEAM_TUNNEL_INSTANCE_ID" `
        -PreviousValue $previousInstanceId
}
