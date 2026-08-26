$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $ProjectRoot
$missing = @()
foreach ($path in @(
    ".env.example",
    "pyproject.toml",
    "README.md",
    "docs\product-and-technology-handbook.md",
    "frontend\package.json",
    "frontend\package-lock.json",
    "tests\test-and-acceptance-record.md",
    "reports\group-report.md",
    "AGENTS.md"
)) {
    if (-not (Test-Path -LiteralPath $path)) { $missing += $path }
}
if ($missing.Count -gt 0) {
    Write-Error ("阶段 0 骨架缺少：" + ($missing -join ", "))
    exit 1
}

# Prefer tracked files. Source archives without .git use an explicit dependency/cache exclusion.
if (Test-Path -LiteralPath ".git" -PathType Container) {
    $trackedReadmes = @(git ls-files "*README.md")
} else {
    $excluded = '\\(\.venv|node_modules|\.next|\.pytest_cache|\.ruff_cache|logs|tmp|data|artifacts)\\'
    $trackedReadmes = @(Get-ChildItem -Recurse -File -Filter README.md -ErrorAction SilentlyContinue | Where-Object {
        $_.FullName -notmatch $excluded
    } | ForEach-Object {
        $_.FullName.Substring($ProjectRoot.Length).TrimStart('\').Replace('\', '/')
    })
}
if ($trackedReadmes.Count -ne 1 -or $trackedReadmes[0] -ne "README.md") {
    Write-Error "仓库必须且只能在根目录保留一个 README.md；子目录说明文件应使用职责明确的唯一名称。"
    exit 1
}

$frontendPackage = Get-Content -LiteralPath "frontend\package.json" -Raw | ConvertFrom-Json
$pythonProject = Get-Content -LiteralPath "pyproject.toml" -Raw

if ($frontendPackage.engines.node -ne ">=24 <25") {
    Write-Error "Node.js 版本基线不一致：frontend/package.json 必须限制为 >=24 <25。"
    exit 1
}
# 校验逻辑与原实现一致，只修正引号写法。原写法把 JS 代码放在 PowerShell 单引号串里并
# 在其中使用双引号，而 Windows PowerShell 向原生命令传参时会吃掉这些双引号，node 收到的
# 是 require(./frontend/package.json)（缺引号），必然抛 SyntaxError，使本检查恒失败。
# 改为 JS 侧用单引号、PowerShell 侧用双引号（串内无 $，不会被插值）。
# 不改用 ConvertFrom-Json：package-lock.json 含空字符串键 "packages": { "": {...} }，
# Windows PowerShell 5.1 的 ConvertFrom-Json 无法处理空属性名，会直接报错。
& node -e "const p=require('./frontend/package.json'); const l=require('./frontend/package-lock.json'); if(l.name!==p.name || l.version!==p.version || l.lockfileVersion!==3) process.exit(1);"
if ($LASTEXITCODE -ne 0) {
    Write-Error "前端依赖锁文件与 package.json 不一致，或 lockfileVersion 不是 3。"
    exit 1
}
if ($pythonProject -notmatch '(?m)^requires-python = ">=3\.13,<3\.14"$') {
    Write-Error "Python 版本基线不一致：pyproject.toml 必须限制为 >=3.13,<3.14。"
    exit 1
}

$python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    Write-Error "Missing .venv; run .\setup.ps1 before verification."
    exit 1
}

if (Test-Path -LiteralPath ".git") {
    & "$ProjectRoot\scripts\check-secrets.ps1"
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} else {
    $excluded = '\\(\.venv|node_modules|\.next|\.pytest_cache|\.ruff_cache|logs|tmp|data|artifacts)\\'
    $forbidden = @(Get-ChildItem -Recurse -File -ErrorAction SilentlyContinue | Where-Object {
        $_.FullName -notmatch $excluded -and (
            $_.Name -eq ".env" -or $_.Extension -match '^\.(mp4|mov|avi|mkv|wav|mp3|pem|key|sqlite|sqlite3)$'
        )
    })
    if ($forbidden) {
        Write-Error ("Forbidden source files: " + (($forbidden | ForEach-Object FullName) -join ", "))
        exit 1
    }
}

$previousTemp = $env:TEMP
$previousTmp = $env:TMP
$pytestTemp = Join-Path $ProjectRoot "tmp\pytest-verify-$PID"
New-Item -ItemType Directory -Force -Path $pytestTemp | Out-Null
$env:TEMP = $pytestTemp
$env:TMP = $pytestTemp
try {
    & $python -m pytest -q -p no:cacheprovider --basetemp (Join-Path $pytestTemp "run")
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} finally {
    $env:TEMP = $previousTemp
    $env:TMP = $previousTmp
    if (Test-Path -LiteralPath $pytestTemp) {
        Remove-Item -LiteralPath $pytestTemp -Recurse -Force -ErrorAction SilentlyContinue
    }
}
& $python -m ruff check backend agent tests
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Push-Location -LiteralPath "frontend"
try {
    & npm.cmd test
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & npm.cmd run typecheck
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & npm.cmd run build
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} finally {
    Pop-Location
}

Write-Host "Release verification passed: Python tests/lint and frontend test/typecheck/build."
exit 0
