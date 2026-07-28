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
  frontend/package-lock.json \
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

# 只检查 Git 跟踪的文件。find 会扫到被忽略目录里的第三方 README.md
# （pytest 生成 .pytest_cache/README.md，node_modules 与 .venv 里也有大量 README.md），
# 导致任何人装过依赖或跑过一次测试之后本检查就永久误报。
if ! readme_files="$(git ls-files '*README.md' | sort)"; then
  echo "无法读取 Git 跟踪文件，README 唯一性检查未执行；请确认当前目录是可访问的 Git 仓库。" >&2
  exit 1
fi
if [[ "$readme_files" != "README.md" ]]; then
  echo "仓库必须且只能在根目录保留一个 README.md；子目录说明文件应使用职责明确的唯一名称。" >&2
  exit 1
fi

if ! grep -Eq '"node"[[:space:]]*:[[:space:]]*">=24 <25"' frontend/package.json; then
  echo "Node.js 版本基线不一致：frontend/package.json 必须限制为 >=24 <25。" >&2
  exit 1
fi
if ! grep -Eq '"lockfileVersion"[[:space:]]*:[[:space:]]*3' frontend/package-lock.json; then
  echo "前端依赖锁文件必须使用 lockfileVersion 3。" >&2
  exit 1
fi
if ! grep -Eq '^requires-python = ">=3\.13,<3\.14"$' pyproject.toml; then
  echo "Python 版本基线不一致：pyproject.toml 必须限制为 >=3.13,<3.14。" >&2
  exit 1
fi

echo "阶段 0 骨架检查通过。核心流程测试将在实现后启用。"
