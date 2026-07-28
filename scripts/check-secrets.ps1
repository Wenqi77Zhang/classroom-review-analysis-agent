$ErrorActionPreference = "Stop"
$tracked = git ls-files
if ($LASTEXITCODE -ne 0) {
    throw "无法读取 Git 跟踪文件，敏感文件检查未执行；请先确认当前目录是可信且可访问的 Git 仓库。"
}
$forbiddenPaths = $tracked | Where-Object {
    $_ -match '(^|/)\.env$' -or
    $_ -match '\.(mp4|mov|avi|mkv|wav|mp3|pem|key|sqlite|sqlite3)$'
}
if ($forbiddenPaths) {
    Write-Error ("禁止提交的文件：" + ($forbiddenPaths -join ", "))
    exit 1
}
Write-Host "路径级敏感文件检查通过。"
