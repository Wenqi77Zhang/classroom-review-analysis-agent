#!/usr/bin/env sh
set -eu

OFFSITE_BACKUP_BUCKET=${OFFSITE_BACKUP_BUCKET:-}
OFFSITE_BACKUP_PREFIX=${OFFSITE_BACKUP_PREFIX:-classroom-review-agent}
OFFSITE_BACKUP_REGION=${OFFSITE_BACKUP_REGION:-ap-southeast-2}
POSTGRES_IMAGE=${POSTGRES_IMAGE:-postgres:17-alpine}

if [ -z "$OFFSITE_BACKUP_BUCKET" ]; then
  echo "OFFSITE_BACKUP_BUCKET is required." >&2
  exit 2
fi
if ! command -v aws >/dev/null 2>&1; then
  echo "AWS CLI is required on the host." >&2
  exit 1
fi

umask 077
WORK_DIR=$(mktemp -d "${TMPDIR:-/tmp}/classroom-offsite-restore.XXXXXX")
RESTORE_CONTAINER="classroom-offsite-restore-$$"
RESTORE_USER=restore_test
RESTORE_DATABASE=restore_test
RESTORE_PASSWORD="restore-$$-private"

cleanup() {
  docker rm -f "$RESTORE_CONTAINER" >/dev/null 2>&1 || true
  rm -rf "$WORK_DIR"
}
trap cleanup EXIT HUP INT TERM

COMPLETE_KEY=$(aws s3api list-objects-v2 \
  --bucket "$OFFSITE_BACKUP_BUCKET" \
  --prefix "$OFFSITE_BACKUP_PREFIX/" \
  --region "$OFFSITE_BACKUP_REGION" \
  --query "reverse(sort_by(Contents[?ends_with(Key, '/COMPLETE')], &LastModified))[0].Key" \
  --output text)
if [ -z "$COMPLETE_KEY" ] || [ "$COMPLETE_KEY" = "None" ]; then
  echo "No complete off-site backup was found." >&2
  exit 1
fi
REMOTE_PREFIX=${COMPLETE_KEY%/COMPLETE}
aws s3 sync "s3://$OFFSITE_BACKUP_BUCKET/$REMOTE_PREFIX/" "$WORK_DIR" \
  --region "$OFFSITE_BACKUP_REGION" --only-show-errors

for file in COMPLETE database.dump objects.tar.gz objects.sha256 backup.sha256 metadata.txt; do
  if [ ! -s "$WORK_DIR/$file" ]; then
    echo "Downloaded backup is incomplete: $file is missing or empty." >&2
    exit 1
  fi
done
(
  cd "$WORK_DIR"
  sha256sum -c backup.sha256
)

mkdir "$WORK_DIR/object-restore"
tar -C "$WORK_DIR/object-restore" -xzf "$WORK_DIR/objects.tar.gz"
(
  cd "$WORK_DIR/object-restore"
  sha256sum -c "$WORK_DIR/objects.sha256"
)
OBJECT_COUNT=$(find "$WORK_DIR/object-restore" -type f | wc -l | tr -d ' ')
OBJECT_BYTES=$(find "$WORK_DIR/object-restore" -type f -printf '%s\n' | awk '{total += $1} END {print total + 0}')

docker run -d --rm --name "$RESTORE_CONTAINER" \
  -e POSTGRES_USER="$RESTORE_USER" \
  -e POSTGRES_PASSWORD="$RESTORE_PASSWORD" \
  -e POSTGRES_DB="$RESTORE_DATABASE" \
  "$POSTGRES_IMAGE" >/dev/null
attempt=0
until docker exec "$RESTORE_CONTAINER" pg_isready \
  -U "$RESTORE_USER" -d "$RESTORE_DATABASE" >/dev/null 2>&1; do
  attempt=$((attempt + 1))
  if [ "$attempt" -ge 30 ]; then
    echo "Isolated PostgreSQL did not become ready." >&2
    exit 1
  fi
  sleep 1
done
docker exec -i "$RESTORE_CONTAINER" pg_restore --list < "$WORK_DIR/database.dump" >/dev/null
docker exec -i "$RESTORE_CONTAINER" pg_restore \
  --username "$RESTORE_USER" --dbname "$RESTORE_DATABASE" \
  --no-owner --exit-on-error < "$WORK_DIR/database.dump"
TABLE_COUNT=$(docker exec "$RESTORE_CONTAINER" psql \
  -U "$RESTORE_USER" -d "$RESTORE_DATABASE" -Atc \
  "select count(*) from pg_tables where schemaname = 'public'")
ALEMBIC_VERSION=$(docker exec "$RESTORE_CONTAINER" psql \
  -U "$RESTORE_USER" -d "$RESTORE_DATABASE" -Atc \
  "select version_num from alembic_version")

echo "OFFSITE_RESTORE_DRILL=PASS"
echo "REMOTE_PREFIX=$REMOTE_PREFIX"
echo "OBJECT_COUNT=$OBJECT_COUNT"
echo "OBJECT_BYTES=$OBJECT_BYTES"
echo "TABLE_COUNT=$TABLE_COUNT"
echo "ALEMBIC_VERSION=$ALEMBIC_VERSION"
echo "Production services and source data remained untouched; isolated restore resources will now be removed."
