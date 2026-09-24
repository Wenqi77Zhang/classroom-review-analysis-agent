#!/usr/bin/env sh
set -eu

PROJECT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
ENV_FILE=${ENV_FILE:-"$PROJECT_ROOT/.env.production"}
BASE_COMPOSE="$PROJECT_ROOT/deploy/compose.production.yml"
AWS_COMPOSE="$PROJECT_ROOT/deploy/compose.aws.yml"

if [ ! -f "$ENV_FILE" ]; then
  echo "Missing production environment file: $ENV_FILE" >&2
  exit 1
fi
if [ "$(stat -c '%a' "$ENV_FILE")" != "600" ]; then
  echo "Refusing to start: .env.production must have mode 600." >&2
  exit 1
fi

PUBLIC_HOST=$(sed -n 's/^PUBLIC_HOST=//p' "$ENV_FILE" | tail -n 1)
FRONTEND_ORIGIN=$(sed -n 's/^FRONTEND_ORIGIN=//p' "$ENV_FILE" | tail -n 1)
LOCAL_MODEL_CHAT_COMPLETIONS_URL=$(
  sed -n 's/^LOCAL_MODEL_CHAT_COMPLETIONS_URL=//p' "$ENV_FILE" | tail -n 1
)
OBJECT_STORAGE_ENDPOINT=$(sed -n 's/^OBJECT_STORAGE_ENDPOINT=//p' "$ENV_FILE" | tail -n 1)
OBJECT_STORAGE_PROVIDER=$(sed -n 's/^OBJECT_STORAGE_PROVIDER=//p' "$ENV_FILE" | tail -n 1)
OBJECT_STORAGE_PUBLIC_HOST=$(sed -n 's/^OBJECT_STORAGE_PUBLIC_HOST=//p' "$ENV_FILE" | tail -n 1)
OBJECT_STORAGE_PUBLIC_ENDPOINT=$(
  sed -n 's/^OBJECT_STORAGE_PUBLIC_ENDPOINT=//p' "$ENV_FILE" | tail -n 1
)

: "${PUBLIC_HOST:?PUBLIC_HOST is required}"
: "${FRONTEND_ORIGIN:?FRONTEND_ORIGIN is required}"
case "$FRONTEND_ORIGIN" in
  "https://$PUBLIC_HOST") ;;
  *) echo "FRONTEND_ORIGIN must equal https://PUBLIC_HOST." >&2; exit 1 ;;
esac
case "$LOCAL_MODEL_CHAT_COMPLETIONS_URL" in
  http://ollama:11434/v1/chat/completions) ;;
  *) echo "AWS local-model deployment requires the internal Ollama endpoint." >&2; exit 1 ;;
esac
case "$OBJECT_STORAGE_ENDPOINT" in
  http://minio:9000) ;;
  *) echo "AWS deployment requires the internal MinIO endpoint." >&2; exit 1 ;;
esac
: "${OBJECT_STORAGE_PUBLIC_HOST:?OBJECT_STORAGE_PUBLIC_HOST is required}"
case "$OBJECT_STORAGE_PUBLIC_ENDPOINT" in
  "https://$OBJECT_STORAGE_PUBLIC_HOST") ;;
  *) echo "OBJECT_STORAGE_PUBLIC_ENDPOINT must equal https://OBJECT_STORAGE_PUBLIC_HOST." >&2; exit 1 ;;
esac

docker compose --env-file "$ENV_FILE" \
  -f "$BASE_COMPOSE" -f "$AWS_COMPOSE" config --quiet
docker compose --env-file "$ENV_FILE" \
  -f "$BASE_COMPOSE" -f "$AWS_COMPOSE" up -d --build
if [ "$OBJECT_STORAGE_PROVIDER" != "minio" ]; then
  docker compose --env-file "$ENV_FILE" \
    -f "$BASE_COMPOSE" -f "$AWS_COMPOSE" run --rm --no-deps backend \
    python scripts/configure_production_cors.py apply --origin "$FRONTEND_ORIGIN"
fi
docker compose --env-file "$ENV_FILE" \
  -f "$BASE_COMPOSE" -f "$AWS_COMPOSE" run --rm --no-deps backend \
  python scripts/configure_production_cors.py verify --origin "$FRONTEND_ORIGIN"
docker compose --env-file "$ENV_FILE" \
  -f "$BASE_COMPOSE" -f "$AWS_COMPOSE" ps

echo "Deployment started at https://$PUBLIC_HOST"
