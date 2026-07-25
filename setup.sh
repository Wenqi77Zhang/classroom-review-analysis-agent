#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

for command in node npm git ffmpeg; do
  command -v "$command" >/dev/null 2>&1 || {
    echo "缺少系统工具：$command。请先安装后重新运行 setup.sh。" >&2
    exit 1
  }
done

node_version="$(node --version)"
if [[ ! "$node_version" =~ ^v24\. ]]; then
  echo "需要 Node.js 24 LTS。当前版本为 $node_version，请切换版本后再运行 setup.sh。" >&2
  exit 1
fi

if command -v python3.13 >/dev/null 2>&1; then
  python_command="python3.13"
elif command -v python3 >/dev/null 2>&1 &&
  python3 -c 'import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 13) else 1)'; then
  python_command="python3"
else
  echo "需要 Python 3.13。请安装 python3.13；系统默认 Python 可以保留其他版本。" >&2
  exit 1
fi

if [[ ! -d .venv ]]; then
  "$python_command" -m venv .venv
fi

.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e ".[dev]"

if [[ -f frontend/package.json ]]; then
  (cd frontend && npm install)
fi

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "已创建 .env，请人工填写必要配置；不要提交该文件。"
fi

./verify.sh
