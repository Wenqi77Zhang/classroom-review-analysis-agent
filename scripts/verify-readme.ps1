$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$readme = Get-Content -LiteralPath (Join-Path $root "README.md") -Raw -Encoding UTF8
$requiredCommands = @(".\setup.ps1", ".\start.ps1", ".\verify.ps1", "qwen3.5:4b")
$missing = $requiredCommands | Where-Object { -not $readme.Contains($_) }
if ($missing) {
    throw "README is missing reproducible commands or model configuration: $($missing -join ', ')"
}

powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root "verify.ps1")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "README command contract and release verification passed."
