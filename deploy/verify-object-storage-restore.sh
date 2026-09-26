#!/usr/bin/env sh
set -eu

PROJECT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
ENV_FILE=${ENV_FILE:-"$PROJECT_ROOT/.env.production"}
BASE_COMPOSE="$PROJECT_ROOT/deploy/compose.production.yml"
AWS_COMPOSE="$PROJECT_ROOT/deploy/compose.aws.yml"
MC_IMAGE=${MC_IMAGE:-quay.io/minio/mc:latest}
MINIO_IMAGE=${MINIO_IMAGE:-quay.io/minio/minio:latest}

if [ ! -f "$ENV_FILE" ]; then
  echo "Missing production environment file: $ENV_FILE" >&2
  exit 1
fi

umask 077
WORK_DIR=$(mktemp -d "${TMPDIR:-/tmp}/classroom-object-restore.XXXXXX")
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)-$$"
RESTORE_CONTAINER="classroom-object-restore-$RUN_ID"
NETWORK_NAME="classroom-object-restore-$RUN_ID"
RESTORE_USER=restorecheck
RESTORE_PASSWORD="restore-$RUN_ID-private"

cleanup() {
  docker rm -f "$RESTORE_CONTAINER" >/dev/null 2>&1 || true
  docker network rm "$NETWORK_NAME" >/dev/null 2>&1 || true
  rm -rf "$WORK_DIR"
}
trap cleanup EXIT HUP INT TERM

mkdir -p "$WORK_DIR/source" "$WORK_DIR/restore-input" "$WORK_DIR/verification"

# Read the live bucket through the private Compose network. Production objects are
# copied to a mode-700 temporary directory and the source service is never mutated.
docker compose --env-file "$ENV_FILE" -f "$BASE_COMPOSE" -f "$AWS_COMPOSE" \
  run --rm --no-deps --user "$(id -u):$(id -g)" -e HOME=/tmp \
  -v "$WORK_DIR:/work" --entrypoint /bin/sh minio-init -ec '
    mc alias set source http://minio:9000 \
      "$OBJECT_STORAGE_ACCESS_KEY_ID" "$OBJECT_STORAGE_SECRET_ACCESS_KEY" >/dev/null
    mc mirror --overwrite "source/$OBJECT_STORAGE_BUCKET" /work/source >/dev/null
  '

OBJECT_COUNT=$(find "$WORK_DIR/source" -type f | wc -l | tr -d ' ')
if [ "$OBJECT_COUNT" -eq 0 ]; then
  echo "Object-storage restore drill refused: the source bucket is empty." >&2
  exit 1
fi

(
  cd "$WORK_DIR/source"
  find . -type f -print0 | LC_ALL=C sort -z | xargs -0 sha256sum
) > "$WORK_DIR/source.sha256"
SOURCE_BYTES=$(find "$WORK_DIR/source" -type f -printf '%s\n' | awk '{total += $1} END {print total + 0}')

tar -C "$WORK_DIR/source" -czf "$WORK_DIR/object-storage-backup.tar.gz" .
ARCHIVE_SHA256=$(sha256sum "$WORK_DIR/object-storage-backup.tar.gz" | awk '{print $1}')
SOURCE_MANIFEST_SHA256=$(sha256sum "$WORK_DIR/source.sha256" | awk '{print $1}')

# Restore only from the archive, not from the original mirror.
tar -C "$WORK_DIR/restore-input" -xzf "$WORK_DIR/object-storage-backup.tar.gz"
rm -rf "$WORK_DIR/source"

docker network create "$NETWORK_NAME" >/dev/null
docker run -d --rm --name "$RESTORE_CONTAINER" --network "$NETWORK_NAME" \
  -e "MINIO_ROOT_USER=$RESTORE_USER" \
  -e "MINIO_ROOT_PASSWORD=$RESTORE_PASSWORD" \
  "$MINIO_IMAGE" server /data >/dev/null

attempt=0
until docker exec "$RESTORE_CONTAINER" curl --fail --silent \
  http://127.0.0.1:9000/minio/health/ready >/dev/null 2>&1; do
  attempt=$((attempt + 1))
  if [ "$attempt" -ge 30 ]; then
    echo "Isolated MinIO did not become ready." >&2
    exit 1
  fi
  sleep 2
done

docker run --rm --network "$NETWORK_NAME" --entrypoint /bin/sh \
  --user "$(id -u):$(id -g)" -e HOME=/tmp \
  -e "RESTORE_USER=$RESTORE_USER" \
  -e "RESTORE_PASSWORD=$RESTORE_PASSWORD" \
  -e "RESTORE_HOST=$RESTORE_CONTAINER" \
  -v "$WORK_DIR:/work" "$MC_IMAGE" -ec '
    mc alias set restore "http://$RESTORE_HOST:9000" \
      "$RESTORE_USER" "$RESTORE_PASSWORD" >/dev/null
    mc mb --ignore-existing restore/classroom-restore >/dev/null
    mc anonymous set none restore/classroom-restore >/dev/null
    mc mirror --overwrite /work/restore-input restore/classroom-restore >/dev/null
    mc mirror --overwrite restore/classroom-restore /work/verification >/dev/null
  '

(
  cd "$WORK_DIR/verification"
  find . -type f -print0 | LC_ALL=C sort -z | xargs -0 sha256sum
) > "$WORK_DIR/verification.sha256"
diff -u "$WORK_DIR/source.sha256" "$WORK_DIR/verification.sha256"

VERIFIED_COUNT=$(find "$WORK_DIR/verification" -type f | wc -l | tr -d ' ')
VERIFIED_BYTES=$(find "$WORK_DIR/verification" -type f -printf '%s\n' | awk '{total += $1} END {print total + 0}')
if [ "$VERIFIED_COUNT" -ne "$OBJECT_COUNT" ] || [ "$VERIFIED_BYTES" -ne "$SOURCE_BYTES" ]; then
  echo "Restored object count or byte total does not match the source." >&2
  exit 1
fi

echo "OBJECT_STORAGE_RESTORE_DRILL=PASS"
echo "RUN_ID=$RUN_ID"
echo "OBJECT_COUNT=$OBJECT_COUNT"
echo "TOTAL_BYTES=$SOURCE_BYTES"
echo "ARCHIVE_SHA256=$ARCHIVE_SHA256"
echo "MANIFEST_SHA256=$SOURCE_MANIFEST_SHA256"
echo "Production source remained read-only; the archive, isolated container, network, and temporary files will now be removed."
