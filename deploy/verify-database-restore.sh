#!/usr/bin/env sh
set -eu

PROJECT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
ENV_FILE=${ENV_FILE:-"$PROJECT_ROOT/.env.production"}
COMPOSE_FILE="$PROJECT_ROOT/deploy/compose.production.yml"
RUN_ID="restore-drill-$$"
WORK_DIR=$(mktemp -d "${TMPDIR:-/tmp}/classroom-${RUN_ID}.XXXXXX")
RESTORE_CONTAINER="classroom-${RUN_ID}"
RESTORE_USER=restore_test
RESTORE_DATABASE=restore_test
RESTORE_PASSWORD="${RUN_ID}-only"

cleanup() {
  docker rm -f "$RESTORE_CONTAINER" >/dev/null 2>&1 || true
  rm -rf "$WORK_DIR"
}
trap cleanup EXIT HUP INT TERM

if [ ! -f "$ENV_FILE" ]; then
  echo "Missing production environment file: $ENV_FILE" >&2
  exit 1
fi

umask 077
BACKUP_DIR="$WORK_DIR" sh "$PROJECT_ROOT/deploy/backup-database.sh" >/dev/null
BACKUP_FILE=$(find "$WORK_DIR" -maxdepth 1 -type f -name 'classroom-review-*.dump' -print -quit)
if [ -z "$BACKUP_FILE" ] || [ ! -s "$BACKUP_FILE" ]; then
  echo "The isolated restore drill did not receive a non-empty backup." >&2
  exit 1
fi

BACKUP_MODE=$(stat -c '%a' "$BACKUP_FILE")
if [ "$BACKUP_MODE" != "600" ]; then
  echo "The backup mode is $BACKUP_MODE; expected 600." >&2
  exit 1
fi
BACKUP_BYTES=$(stat -c '%s' "$BACKUP_FILE")

docker run -d --rm \
  --name "$RESTORE_CONTAINER" \
  -e POSTGRES_USER="$RESTORE_USER" \
  -e POSTGRES_PASSWORD="$RESTORE_PASSWORD" \
  -e POSTGRES_DB="$RESTORE_DATABASE" \
  postgres:17-alpine >/dev/null

attempt=0
until docker exec "$RESTORE_CONTAINER" pg_isready \
  -U "$RESTORE_USER" -d "$RESTORE_DATABASE" >/dev/null 2>&1; do
  attempt=$((attempt + 1))
  if [ "$attempt" -ge 30 ]; then
    echo "The disposable PostgreSQL container did not become ready." >&2
    exit 1
  fi
  sleep 1
done

docker exec -i "$RESTORE_CONTAINER" pg_restore --list < "$BACKUP_FILE" >/dev/null
docker exec -i "$RESTORE_CONTAINER" pg_restore \
  --username "$RESTORE_USER" \
  --dbname "$RESTORE_DATABASE" \
  --no-owner \
  --exit-on-error < "$BACKUP_FILE"

PRODUCTION_POSTGRES=$(docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" ps -q postgres)
if [ -z "$PRODUCTION_POSTGRES" ]; then
  echo "The production PostgreSQL container is not running." >&2
  exit 1
fi

count_rows() {
  container=$1
  docker exec "$container" sh -ec '
    for table_name in $(psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc \
      "select tablename from pg_tables where schemaname = '\''public'\'' order by tablename"); do
      printf "%s=" "$table_name"
      psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc \
        "select count(*) from \"$table_name\";"
    done
  '
}

count_rows "$PRODUCTION_POSTGRES" > "$WORK_DIR/production-counts.txt"
count_rows "$RESTORE_CONTAINER" > "$WORK_DIR/restored-counts.txt"
diff -u "$WORK_DIR/production-counts.txt" "$WORK_DIR/restored-counts.txt"

TABLE_COUNT=$(wc -l < "$WORK_DIR/restored-counts.txt" | tr -d ' ')
ROW_COUNT_DIGEST=$(sha256sum "$WORK_DIR/restored-counts.txt" | awk '{print $1}')
ALEMBIC_VERSION=$(docker exec "$RESTORE_CONTAINER" sh -ec \
  'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "select version_num from alembic_version"')

printf 'RESTORE_DRILL_ID=%s\n' "$RUN_ID"
printf 'BACKUP_BYTES=%s\n' "$BACKUP_BYTES"
printf 'BACKUP_MODE=%s\n' "$BACKUP_MODE"
printf 'TABLE_COUNT=%s\n' "$TABLE_COUNT"
printf 'ROW_COUNT_DIGEST=%s\n' "$ROW_COUNT_DIGEST"
printf 'ALEMBIC_VERSION=%s\n' "$ALEMBIC_VERSION"
printf 'RESTORE_DRILL=PASS\n'
