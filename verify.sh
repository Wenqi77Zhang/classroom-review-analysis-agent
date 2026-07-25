#!/usr/bin/env bash
set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"
for path in \
  .env.example \
  pyproject.toml \
  README.md \
  docs/documentation-index.md \
  docs/requirements-baseline.md \
  frontend/package.json \
  frontend/frontend-module-guide.md \
  backend/backend-module-guide.md \
  worker/media-worker-guide.md \
  agent/agent-module-guide.md \
  tests/testing-guide.md \
  tests/fixtures/fixture-catalog.md \
  reports/reporting-guide.md \
  reports/evidence/evidence-index.md \
  scripts/script-guide.md; do
  [[ -e "$path" ]] || { echo "阶段 0 骨架缺少：$path" >&2; exit 1; }
done

readme_files="$(find . -path ./.git -prune -o -type f -name README.md -print | sort)"
if [[ "$readme_files" != "./README.md" ]]; then
  echo "仓库必须且只能在根目录保留一个 README.md；子目录说明文件应使用职责明确的唯一名称。" >&2
  exit 1
fi

node_baseline="$(tr -d '[:space:]' < .nvmrc)"
python_baseline="$(tr -d '[:space:]' < .python-version)"
if [[ "$node_baseline" != "24" ]] || ! grep -Eq '"node"[[:space:]]*:[[:space:]]*">=24 <25"' frontend/package.json; then
  echo "Node.js 版本基线不一致：.nvmrc 必须为 24，frontend/package.json 必须限制为 >=24 <25。" >&2
  exit 1
fi
if [[ "$python_baseline" != "3.13" ]] || ! grep -Eq '^requires-python = ">=3\.13,<3\.14"$' pyproject.toml; then
  echo "Python 版本基线不一致：.python-version 必须为 3.13，pyproject.toml 必须限制为 >=3.13,<3.14。" >&2
  exit 1
fi

echo "阶段 0 骨架检查通过。核心流程测试将在实现后启用。"
