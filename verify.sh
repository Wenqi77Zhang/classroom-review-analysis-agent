#!/usr/bin/env bash
set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"
for path in \
  .env.example \
  pyproject.toml \
  README.md \
  docs/product-and-technology-handbook.md \
  frontend/package.json \
  frontend/package-lock.json \
  tests/test-and-acceptance-record.md \
  reports/group-report.md \
  AGENTS.md; do
  [[ -e "$path" ]] || { echo "阶段 0 骨架缺少：$path" >&2; exit 1; }
done

if readme_files="$(git ls-files '*README.md' 2>/dev/null | sort)"; then
  :
else
  readme_files="$(find . -type d \( -name .venv -o -name node_modules -o -name .next -o -name .pytest_cache -o -name .ruff_cache -o -name logs \) -prune -o -type f -name README.md -print | sed 's#^./##' | sort)"
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

if [[ "${1:-}" == "--scaffold-only" ]]; then
  echo "Stage-0 scaffold verification passed."
  exit 0
fi

python="$PROJECT_ROOT/.venv/bin/python"
[[ -x "$python" ]] || { echo "Missing .venv; run ./setup.sh before verification." >&2; exit 1; }

if [[ -d .git ]]; then
  bash scripts/check-secrets.sh
else
  forbidden="$(find . -type d \( -name .venv -o -name node_modules -o -name .next -o -name .pytest_cache -o -name .ruff_cache -o -name logs \) -prune -o -type f \( -name .env -o -iregex '.*\.\(mp4\|mov\|avi\|mkv\|wav\|mp3\|pem\|key\|sqlite\|sqlite3\)' \) -print)"
  [[ -z "$forbidden" ]] || { echo "Forbidden source files:" >&2; echo "$forbidden" >&2; exit 1; }
fi

"$python" -m pytest -q
"$python" -m ruff check backend agent worker scripts tests
(cd frontend && npm test && npm run test:e2e:spec && npm run typecheck && npm run build)

echo "Release verification passed: Python tests/lint and frontend contract/E2E collection/typecheck/build."
