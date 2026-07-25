$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $ProjectRoot
$missing = @()
foreach ($path in @(
    ".env.example",
    "pyproject.toml",
    "README.md",
    "docs\documentation-index.md",
    "docs\requirements-baseline.md",
    "frontend\package.json",
    "frontend\frontend-module-guide.md",
    "backend\backend-module-guide.md",
    "worker\media-worker-guide.md",
    "agent\agent-module-guide.md",
    "tests\testing-guide.md",
    "tests\fixtures\fixture-catalog.md",
    "reports\reporting-guide.md",
    "reports\evidence\evidence-index.md",
    "scripts\script-guide.md"
)) {
    if (-not (Test-Path -LiteralPath $path)) { $missing += $path }
}
if ($missing.Count -gt 0) {
    Write-Error ("阶段 0 骨架缺少：" + ($missing -join ", "))
    exit 1
}

$readmeFiles = @(
    Get-ChildItem -LiteralPath $ProjectRoot -Recurse -Force -File -Filter "README.md" |
        Where-Object { $_.FullName -notmatch '[\\/]\.git[\\/]' }
)
if ($readmeFiles.Count -ne 1 -or $readmeFiles[0].FullName -ne (Join-Path $ProjectRoot "README.md")) {
    Write-Error "仓库必须且只能在根目录保留一个 README.md；子目录说明文件应使用职责明确的唯一名称。"
    exit 1
}

$frontendPackage = Get-Content -LiteralPath "frontend\package.json" -Raw | ConvertFrom-Json
$pythonProject = Get-Content -LiteralPath "pyproject.toml" -Raw

if ($frontendPackage.engines.node -ne ">=24 <25") {
    Write-Error "Node.js 版本基线不一致：frontend/package.json 必须限制为 >=24 <25。"
    exit 1
}
if ($pythonProject -notmatch '(?m)^requires-python = ">=3\.13,<3\.14"$') {
    Write-Error "Python 版本基线不一致：pyproject.toml 必须限制为 >=3.13,<3.14。"
    exit 1
}

Write-Host "阶段 0 骨架检查通过。核心流程测试将在实现后启用。"
