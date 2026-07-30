#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="$ROOT/.venv/bin/python"
FRONTEND="$ROOT/frontend"
LOGS="$ROOT/logs"

[[ -x "$PYTHON" ]] || { echo "缺少根目录 .venv，请先运行 setup.sh。" >&2; exit 1; }
[[ -d "$FRONTEND/node_modules" ]] || { echo "缺少 frontend/node_modules，请先运行 setup.sh。" >&2; exit 1; }
[[ -f "$ROOT/.env" ]] || { echo "缺少 .env，请从 .env.example 复制并填写真实本地配置。" >&2; exit 1; }
command -v npm >/dev/null 2>&1 || { echo "未找到 npm，请安装 README 指定的 Node.js 版本。" >&2; exit 1; }

set -a
# shellcheck disable=SC1091
source "$ROOT/.env"
set +a
required=(DATABASE_URL JWT_SECRET DEMO_ACCOUNT_PASSWORD WORKER_SERVICE_TOKEN AGENT_SERVICE_TOKEN LOCAL_MODEL_CHAT_COMPLETIONS_URL LOCAL_MODEL_NAME)
for name in "${required[@]}"; do
  [[ -n "${!name:-}" ]] || { echo "必需环境变量尚未填写：$name" >&2; exit 1; }
done
[[ "$WORKER_SERVICE_TOKEN" != "$AGENT_SERVICE_TOKEN" ]] || { echo "Worker 与 Agent 服务令牌必须不同。" >&2; exit 1; }
mkdir -p "$LOGS"
(cd "$ROOT" && "$PYTHON" scripts/runtime_preflight.py)

pids=()
cleanup() {
  if ((${#pids[@]})); then
    kill "${pids[@]}" 2>/dev/null || true
    wait "${pids[@]}" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

(cd "$ROOT" && "$PYTHON" -m uvicorn --factory backend.app.main:create_app --host 127.0.0.1 --port 8000) >"$LOGS/backend.log" 2>"$LOGS/backend.err.log" &
pids+=("$!")
(cd "$FRONTEND" && npm run dev -- --hostname 127.0.0.1) >"$LOGS/frontend.log" 2>"$LOGS/frontend.err.log" &
pids+=("$!")
(cd "$ROOT" && "$PYTHON" scripts/run_service_loop.py worker) >"$LOGS/worker.log" 2>"$LOGS/worker.err.log" &
pids+=("$!")
(cd "$ROOT" && "$PYTHON" scripts/run_service_loop.py agent) >"$LOGS/agent.log" 2>"$LOGS/agent.err.log" &
pids+=("$!")

echo "前端、后端、Worker 与 Agent 已启动。日志位于 logs/；按 Ctrl+C 停止。"
wait "${pids[@]}"
