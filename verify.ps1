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

# 只检查 Git 跟踪的文件。扫描整个工作区会把被忽略目录里的第三方 README.md 算进来
# （pytest 会生成 .pytest_cache/README.md，node_modules 与 .venv 里也有大量 README.md），
# 导致任何人装过依赖或跑过一次测试之后本检查就永久误报。
$trackedReadmes = @(git ls-files "*README.md")
if ($LASTEXITCODE -ne 0) {
    Write-Error "无法读取 Git 跟踪文件，README 唯一性检查未执行；请确认当前目录是可访问的 Git 仓库。"
    exit 1
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
if ($pythonProject -notmatch '(?m)^requires-python = ">=3\.13,<3\.14"$') {
    Write-Error "Python 版本基线不一致：pyproject.toml 必须限制为 >=3.13,<3.14。"
    exit 1
}

Write-Host "阶段 0 骨架检查通过。核心流程测试将在实现后启用。"
# 显式退出码：project-plan-v5.md §2.2 要求"全部通过为 0，任一必要检查失败为非 0"。
# 隐式成功会让调用方读到上一条命令残留的 $LASTEXITCODE。
exit 0
