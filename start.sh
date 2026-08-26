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
BACKEND_PORT="${BACKEND_PORT:-8100}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"
[[ "$BACKEND_PORT" =~ ^[0-9]+$ && "$BACKEND_PORT" -ge 1 && "$BACKEND_PORT" -le 65535 ]] || { echo "BACKEND_PORT 无效。" >&2; exit 1; }
[[ "$FRONTEND_PORT" =~ ^[0-9]+$ && "$FRONTEND_PORT" -ge 1 && "$FRONTEND_PORT" -le 65535 ]] || { echo "FRONTEND_PORT 无效。" >&2; exit 1; }
[[ "$BACKEND_PORT" != "$FRONTEND_PORT" ]] || { echo "后端与前端端口不能相同。" >&2; exit 1; }
export BACKEND_PORT FRONTEND_PORT
export BACKEND_URL="http://127.0.0.1:$BACKEND_PORT"
mkdir -p "$LOGS"
(cd "$ROOT" && "$PYTHON" scripts/runtime_preflight.py)
(cd "$ROOT" && "$PYTHON" -m alembic -c backend/alembic.ini upgrade head)
echo "数据库迁移已就绪。"
if (cd "$ROOT" && "$PYTHON" scripts/ensure_storage_readiness.py); then
  echo "对象存储就绪对象已核验。"
else
  echo "警告：对象存储尚未就绪；网站将降级启动，真实上传暂不可用。" >&2
fi

assert_port_available() {
  "$PYTHON" -c 'import socket,sys; s=socket.socket(); s.bind(("127.0.0.1", int(sys.argv[1]))); s.close()' "$1" \
    || { echo "端口 $1 已被占用；未启动任何课堂项目服务。" >&2; exit 1; }
}
assert_port_available "$BACKEND_PORT"
assert_port_available "$FRONTEND_PORT"

wait_for_json() {
  local url="$1"
  local mode="$2"
  "$PYTHON" - "$url" "$mode" <<'PY'
import json
import sys
import urllib.request

with urllib.request.urlopen(sys.argv[1], timeout=2) as response:
    payload = json.load(response)
if sys.argv[2] == "backend":
    valid = payload.get("status") == "ok" and bool(payload.get("app_env"))
else:
    valid = payload.get("reachable") is True and payload.get("status") == "ok"
raise SystemExit(0 if valid else 1)
PY
}

wait_until_ready() {
  local pid="$1"
  local service="$2"
  local url="$3"
  local mode="$4"
  local attempts="$5"
  for ((attempt = 1; attempt <= attempts; attempt++)); do
    kill -0 "$pid" 2>/dev/null || { echo "$service 启动失败；请查看 logs/$service.err.log。" >&2; exit 1; }
    if wait_for_json "$url" "$mode" 2>/dev/null; then
      echo "$service 已就绪：$url"
      return
    fi
    sleep 0.5
  done
  echo "$service 未在预期时间内就绪；请查看 logs/$service.err.log。" >&2
  exit 1
}

pids=()
cleanup() {
  if ((${#pids[@]})); then
    kill "${pids[@]}" 2>/dev/null || true
    wait "${pids[@]}" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

(cd "$ROOT" && "$PYTHON" -m uvicorn --factory backend.app.main:create_app --host 127.0.0.1 --port "$BACKEND_PORT") >"$LOGS/backend.log" 2>"$LOGS/backend.err.log" &
pids+=("$!")
wait_until_ready "${pids[0]}" "backend" "$BACKEND_URL/health" "backend" 30
(cd "$FRONTEND" && npm run dev -- --hostname 127.0.0.1 --port "$FRONTEND_PORT") >"$LOGS/frontend.log" 2>"$LOGS/frontend.err.log" &
pids+=("$!")
wait_until_ready "${pids[1]}" "frontend" "http://127.0.0.1:$FRONTEND_PORT/api/backend-health" "frontend" 40
(cd "$ROOT" && "$PYTHON" scripts/run_service_loop.py worker) >"$LOGS/worker.log" 2>"$LOGS/worker.err.log" &
pids+=("$!")
(cd "$ROOT" && "$PYTHON" scripts/run_service_loop.py agent) >"$LOGS/agent.log" 2>"$LOGS/agent.err.log" &
pids+=("$!")

sleep 1
for pid in "${pids[@]}"; do
  kill -0 "$pid" 2>/dev/null || { echo "服务启动后提前退出；请查看 logs/*.err.log。" >&2; exit 1; }
done
echo "前端、后端、Worker 与 Agent 已真实启动。日志位于 logs/；按 Ctrl+C 停止。"
wait "${pids[@]}"
