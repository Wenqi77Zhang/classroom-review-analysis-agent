#!/usr/bin/env bash
set -euo pipefail

forbidden="$(git ls-files | grep -Ei '(^|/)\.env$|\.(mp4|mov|avi|mkv|wav|mp3|pem|key|sqlite|sqlite3)$' || true)"
if [[ -n "$forbidden" ]]; then
  echo "禁止提交的文件：" >&2
  echo "$forbidden" >&2
  exit 1
fi
echo "路径级敏感文件检查通过。"
