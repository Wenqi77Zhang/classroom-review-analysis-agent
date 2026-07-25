$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $ProjectRoot

foreach ($command in @("python", "node", "npm", "git", "ffmpeg")) {
    if (-not (Get-Command $command -ErrorAction SilentlyContinue)) {
        throw "缺少系统工具：$command。请先安装后重新运行 setup.ps1。"
    }
}

$pythonVersionOk = python -c "import sys; print(int((3, 12) <= sys.version_info[:2] < (3, 14)))"
if ($pythonVersionOk -ne "1") {
    throw "需要 Python 3.12 或 3.13。当前版本不兼容，请安装后再运行 setup.ps1。"
}

if (-not (Test-Path -LiteralPath ".venv")) {
    python -m venv .venv
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
