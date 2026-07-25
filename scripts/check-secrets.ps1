$ErrorActionPreference = "Stop"
$tracked = git ls-files
$forbiddenPaths = $tracked | Where-Object {
    $_ -match '(^|/)\.env$' -or
    $_ -match '\.(mp4|mov|avi|mkv|wav|mp3|pem|key|sqlite|sqlite3)$'
}
if ($forbiddenPaths) {
    Write-Error ("禁止提交的文件：" + ($forbiddenPaths -join ", "))
    exit 1
}
Write-Host "路径级敏感文件检查通过。"
