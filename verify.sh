#!/usr/bin/env bash
set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"
for path in .env.example pyproject.toml frontend/package.json docs/requirements-baseline.md; do
  [[ -e "$path" ]] || { echo "阶段 0 骨架缺少：$path" >&2; exit 1; }
done
echo "阶段 0 骨架检查通过。核心流程测试将在实现后启用。"
