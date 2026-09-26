#!/usr/bin/env sh
set -eu

PROJECT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
ENV_FILE=${ENV_FILE:-"$PROJECT_ROOT/.env.production"}
BACKUP_DIR=${BACKUP_DIR:-"$PROJECT_ROOT/deploy/backups"}
COMPOSE_FILE="$PROJECT_ROOT/deploy/compose.production.yml"

if [ ! -f "$ENV_FILE" ]; then
  echo "Missing production environment file: $ENV_FILE" >&2
  exit 1
fi

umask 077
mkdir -p "$BACKUP_DIR"
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
TARGET="$BACKUP_DIR/classroom-review-$STAMP.dump"
TEMP_TARGET="$TARGET.partial.$$"
trap 'rm -f "$TEMP_TARGET"' EXIT HUP INT TERM

if ! docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec -T postgres \
  sh -ec 'pg_dump --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --format=custom' \
  > "$TEMP_TARGET"; then
  echo "Database backup failed; the incomplete temporary file was removed." >&2
  exit 1
fi

if [ ! -s "$TEMP_TARGET" ]; then
  echo "Database backup failed: output was empty." >&2
  exit 1
fi
mv "$TEMP_TARGET" "$TARGET"
trap - EXIT HUP INT TERM

echo "Database backup created: $TARGET"
echo "This file contains private classroom metadata. Store it encrypted and never commit it."
