#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

for command in python3 node npm git ffmpeg; do
  command -v "$command" >/dev/null 2>&1 || {
    echo "缺少系统工具：$command。请先安装后重新运行 setup.sh。" >&2
    exit 1
  }
done

python3 -c 'import sys; raise SystemExit(0 if (3, 12) <= sys.version_info[:2] < (3, 14) else 1)' || {
  echo "需要 Python 3.12 或 3.13。当前版本不兼容，请安装后再运行 setup.sh。" >&2
  exit 1
}

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
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
