$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $ProjectRoot
$missing = @()
foreach ($path in @(".env.example", "pyproject.toml", "frontend\package.json", "docs\requirements-baseline.md")) {
    if (-not (Test-Path -LiteralPath $path)) { $missing += $path }
}
if ($missing.Count -gt 0) {
    Write-Error ("阶段 0 骨架缺少：" + ($missing -join ", "))
    exit 1
}
Write-Host "阶段 0 骨架检查通过。核心流程测试将在实现后启用。"
