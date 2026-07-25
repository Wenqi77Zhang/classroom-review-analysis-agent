#!/usr/bin/env bash
set -euo pipefail

if ! tracked="$(git ls-files)"; then
  echo "无法读取 Git 跟踪文件，敏感文件检查未执行；请先确认当前目录是可信且可访问的 Git 仓库。" >&2
  exit 1
fi

forbidden="$(printf '%s\n' "$tracked" | grep -Ei '(^|/)\.env$|\.(mp4|mov|avi|mkv|wav|mp3|pem|key|sqlite|sqlite3)$' || true)"
if [[ -n "$forbidden" ]]; then
  echo "禁止提交的文件：" >&2
  echo "$forbidden" >&2
  exit 1
fi
echo "路径级敏感文件检查通过。"
