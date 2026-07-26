$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $ProjectRoot

foreach ($command in @("node", "npm", "git", "ffmpeg")) {
    if (-not (Get-Command $command -ErrorAction SilentlyContinue)) {
        throw "缺少系统工具：$command。请先安装后重新运行 setup.ps1。"
    }
}

$nodeVersion = (node --version).Trim()
if ($nodeVersion -notmatch '^v(?<major>\d+)\.' -or [int]$Matches.major -ne 24) {
    throw "需要 Node.js 24 LTS。当前版本为 $nodeVersion，请切换版本后再运行 setup.ps1。"
}

$pythonCommand = $null
$pythonArguments = @()

if (Get-Command "py" -ErrorAction SilentlyContinue) {
    $pythonProbe = & py -3.13 -c "import sys; print(int(sys.version_info[:2] == (3, 13)))" 2>$null
    if ($LASTEXITCODE -eq 0 -and $pythonProbe -eq "1") {
        $pythonCommand = "py"
        $pythonArguments = @("-3.13")
    }
}

if (-not $pythonCommand -and (Get-Command "python" -ErrorAction SilentlyContinue)) {
    $pythonProbe = & python -c "import sys; print(int(sys.version_info[:2] == (3, 13)))" 2>$null
    if ($LASTEXITCODE -eq 0 -and $pythonProbe -eq "1") {
        $pythonCommand = "python"
    }
}

if (-not $pythonCommand) {
    throw "需要 Python 3.13。请安装后确认 `py -3.13 --version` 可用；系统默认 Python 可以保留其他版本。"
}

if (-not (Test-Path -LiteralPath ".venv")) {
    & $pythonCommand @pythonArguments -m venv .venv
    if ($LASTEXITCODE -ne 0) {
        throw "使用 Python 3.13 创建 .venv 失败。"
    }
}

& ".\.venv\Scripts\python.exe" -m pip install --upgrade pip
& ".\.venv\Scripts\python.exe" -m pip install -e ".[dev]"

if (Test-Path -LiteralPath "frontend\package.json") {
    Push-Location "frontend"
    npm install
    Pop-Location
}

if (-not (Test-Path -LiteralPath ".env")) {
    Copy-Item -LiteralPath ".env.example" -Destination ".env"
    Write-Host "已创建 .env，请人工填写必要配置；不要提交该文件。"
}

& ".\verify.ps1"
