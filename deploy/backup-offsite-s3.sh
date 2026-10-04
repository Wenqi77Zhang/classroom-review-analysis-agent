#!/usr/bin/env sh
set -eu

PROJECT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
ENV_FILE=${ENV_FILE:-"$PROJECT_ROOT/.env.production"}
BASE_COMPOSE="$PROJECT_ROOT/deploy/compose.production.yml"
AWS_COMPOSE="$PROJECT_ROOT/deploy/compose.aws.yml"
OFFSITE_BACKUP_BUCKET=${OFFSITE_BACKUP_BUCKET:-}
OFFSITE_BACKUP_PREFIX=${OFFSITE_BACKUP_PREFIX:-classroom-review-agent}
OFFSITE_BACKUP_REGION=${OFFSITE_BACKUP_REGION:-ap-southeast-2}

if [ -z "$OFFSITE_BACKUP_BUCKET" ]; then
  echo "OFFSITE_BACKUP_BUCKET is required." >&2
  exit 2
fi
if [ ! -f "$ENV_FILE" ]; then
  echo "Missing production environment file: $ENV_FILE" >&2
  exit 1
fi
if ! command -v aws >/dev/null 2>&1; then
  echo "AWS CLI is required on the host." >&2
  exit 1
fi

umask 077
WORK_DIR=$(mktemp -d "${TMPDIR:-/tmp}/classroom-offsite-backup.XXXXXX")
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)-$$"
REMOTE_PREFIX="$OFFSITE_BACKUP_PREFIX/$RUN_ID"

cleanup() {
  rm -rf "$WORK_DIR"
}
trap cleanup EXIT HUP INT TERM

mkdir -p "$WORK_DIR/database" "$WORK_DIR/object-source"
BACKUP_DIR="$WORK_DIR/database" sh "$PROJECT_ROOT/deploy/backup-database.sh" >/dev/null
DATABASE_FILE=$(find "$WORK_DIR/database" -maxdepth 1 -type f -name 'classroom-review-*.dump' -print -quit)
if [ -z "$DATABASE_FILE" ] || [ ! -s "$DATABASE_FILE" ]; then
  echo "Off-site backup refused: database dump is missing or empty." >&2
  exit 1
fi
mv "$DATABASE_FILE" "$WORK_DIR/database.dump"

# Mirror the live private bucket read-only into the mode-700 work directory.
docker compose --env-file "$ENV_FILE" -f "$BASE_COMPOSE" -f "$AWS_COMPOSE" \
  run --rm --no-deps --user "$(id -u):$(id -g)" -e HOME=/tmp \
  -v "$WORK_DIR:/work" --entrypoint /bin/sh minio-init -ec '
    mc alias set source http://minio:9000 \
      "$OBJECT_STORAGE_ACCESS_KEY_ID" "$OBJECT_STORAGE_SECRET_ACCESS_KEY" >/dev/null
    mc mirror --overwrite "source/$OBJECT_STORAGE_BUCKET" /work/object-source >/dev/null
  '

OBJECT_COUNT=$(find "$WORK_DIR/object-source" -type f | wc -l | tr -d ' ')
if [ "$OBJECT_COUNT" -eq 0 ]; then
  echo "Off-site backup refused: the production object bucket is empty." >&2
  exit 1
fi
(
  cd "$WORK_DIR/object-source"
  find . -type f -print0 | LC_ALL=C sort -z | xargs -0 sha256sum
) > "$WORK_DIR/objects.sha256"
OBJECT_BYTES=$(find "$WORK_DIR/object-source" -type f -printf '%s\n' | awk '{total += $1} END {print total + 0}')
tar -C "$WORK_DIR/object-source" -czf "$WORK_DIR/objects.tar.gz" .
rm -rf "$WORK_DIR/object-source" "$WORK_DIR/database"

DATABASE_BYTES=$(stat -c '%s' "$WORK_DIR/database.dump")
ARCHIVE_BYTES=$(stat -c '%s' "$WORK_DIR/objects.tar.gz")
(
  cd "$WORK_DIR"
  sha256sum database.dump objects.tar.gz objects.sha256 > backup.sha256
)
cat > "$WORK_DIR/metadata.txt" <<EOF
run_id=$RUN_ID
created_at_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)
database_bytes=$DATABASE_BYTES
object_count=$OBJECT_COUNT
object_source_bytes=$OBJECT_BYTES
object_archive_bytes=$ARCHIVE_BYTES
encryption=AES256
EOF

for file in database.dump objects.tar.gz objects.sha256 backup.sha256 metadata.txt; do
  aws s3 cp "$WORK_DIR/$file" "s3://$OFFSITE_BACKUP_BUCKET/$REMOTE_PREFIX/$file" \
    --region "$OFFSITE_BACKUP_REGION" --sse AES256 --only-show-errors
done
# Upload the completion marker last so restore automation ignores partial runs.
printf 'complete\n' > "$WORK_DIR/COMPLETE"
aws s3 cp "$WORK_DIR/COMPLETE" "s3://$OFFSITE_BACKUP_BUCKET/$REMOTE_PREFIX/COMPLETE" \
  --region "$OFFSITE_BACKUP_REGION" --sse AES256 --only-show-errors

echo "OFFSITE_BACKUP=PASS"
echo "RUN_ID=$RUN_ID"
echo "REMOTE_PREFIX=$REMOTE_PREFIX"
echo "DATABASE_BYTES=$DATABASE_BYTES"
echo "OBJECT_COUNT=$OBJECT_COUNT"
echo "OBJECT_SOURCE_BYTES=$OBJECT_BYTES"
echo "OBJECT_ARCHIVE_BYTES=$ARCHIVE_BYTES"
echo "Local temporary plaintext copies have been removed by the exit trap."
