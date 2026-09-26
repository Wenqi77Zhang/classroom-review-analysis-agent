#!/usr/bin/env sh
set -eu

if [ "$#" -ne 1 ]; then
  echo "Usage: CONFIRM_DATABASE_RESTORE=classroom_review $0 /absolute/path/backup.dump" >&2
  exit 2
fi
if [ "${CONFIRM_DATABASE_RESTORE:-}" != "classroom_review" ]; then
  echo "Restore refused. Set CONFIRM_DATABASE_RESTORE=classroom_review after verifying the target." >&2
  exit 2
fi

PROJECT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
ENV_FILE=${ENV_FILE:-"$PROJECT_ROOT/.env.production"}
COMPOSE_FILE="$PROJECT_ROOT/deploy/compose.production.yml"
BACKUP_FILE=$1

if [ ! -f "$ENV_FILE" ] || [ ! -s "$BACKUP_FILE" ]; then
  echo "Environment file or non-empty backup file is missing." >&2
  exit 1
fi

# Validate the custom-format archive before stopping any application service.
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec -T postgres \
  sh -ec 'pg_restore --list >/dev/null' < "$BACKUP_FILE"
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" stop frontend backend worker agent
cat "$BACKUP_FILE" | docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec -T postgres \
  sh -ec 'pg_restore --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --clean --if-exists --no-owner --exit-on-error'
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d backend worker agent frontend

echo "Database restore completed. Verify health, login, one classroom, evidence, and report export now."
