#!/usr/bin/env sh
set -eu

INSTALL_ROOT=${INSTALL_ROOT:-/opt/classroom-review-agent}
SERVICE_USER=${SERVICE_USER:-classroom}
OFFSITE_BACKUP_BUCKET=${OFFSITE_BACKUP_BUCKET:-}
OFFSITE_BACKUP_PREFIX=${OFFSITE_BACKUP_PREFIX:-classroom-review-agent}
OFFSITE_BACKUP_REGION=${OFFSITE_BACKUP_REGION:-ap-southeast-2}
CONFIG_DIR=/etc/classroom-review-agent
ENV_FILE="$CONFIG_DIR/offsite-backup.env"

if [ "$(id -u)" -ne 0 ]; then
  echo "Run this installer as root." >&2
  exit 1
fi
if [ -z "$OFFSITE_BACKUP_BUCKET" ]; then
  echo "OFFSITE_BACKUP_BUCKET is required." >&2
  exit 2
fi
if ! id "$SERVICE_USER" >/dev/null 2>&1; then
  echo "Service user does not exist: $SERVICE_USER" >&2
  exit 1
fi
if [ ! -x "$INSTALL_ROOT/deploy/backup-offsite-s3.sh" ] || \
   [ ! -x "$INSTALL_ROOT/deploy/verify-offsite-s3-restore.sh" ]; then
  echo "Off-site backup scripts are missing or not executable in $INSTALL_ROOT." >&2
  exit 1
fi

install -d -m 0750 -o root -g "$SERVICE_USER" "$CONFIG_DIR"
umask 077
cat > "$ENV_FILE" <<EOF
OFFSITE_BACKUP_BUCKET=$OFFSITE_BACKUP_BUCKET
OFFSITE_BACKUP_PREFIX=$OFFSITE_BACKUP_PREFIX
OFFSITE_BACKUP_REGION=$OFFSITE_BACKUP_REGION
EOF
chown root:"$SERVICE_USER" "$ENV_FILE"
chmod 0640 "$ENV_FILE"

cat > /etc/systemd/system/classroom-offsite-backup.service <<EOF
[Unit]
Description=Classroom Review Agent encrypted off-site backup
After=docker.service network-online.target
Wants=network-online.target
Requires=docker.service

[Service]
Type=oneshot
User=$SERVICE_USER
Group=$SERVICE_USER
SupplementaryGroups=docker
WorkingDirectory=$INSTALL_ROOT
EnvironmentFile=$ENV_FILE
Environment=TMPDIR=/var/lib/classroom-offsite-backup
Environment=HOME=/var/lib/classroom-offsite-backup
Environment=DOCKER_CONFIG=/var/lib/classroom-offsite-backup/docker
ExecStart=/bin/sh $INSTALL_ROOT/deploy/backup-offsite-s3.sh
StateDirectory=classroom-offsite-backup
StateDirectoryMode=0700
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/classroom-offsite-backup
EOF

cat > /etc/systemd/system/classroom-offsite-backup.timer <<'EOF'
[Unit]
Description=Run the Classroom Review Agent off-site backup daily

[Timer]
OnCalendar=*-*-* 03:20:00 UTC
Persistent=true
RandomizedDelaySec=30m
Unit=classroom-offsite-backup.service

[Install]
WantedBy=timers.target
EOF

cat > /etc/systemd/system/classroom-offsite-restore-check.service <<EOF
[Unit]
Description=Verify the latest Classroom Review Agent off-site backup
After=docker.service network-online.target
Wants=network-online.target
Requires=docker.service

[Service]
Type=oneshot
User=$SERVICE_USER
Group=$SERVICE_USER
SupplementaryGroups=docker
WorkingDirectory=$INSTALL_ROOT
EnvironmentFile=$ENV_FILE
Environment=TMPDIR=/var/lib/classroom-offsite-backup
Environment=HOME=/var/lib/classroom-offsite-backup
Environment=DOCKER_CONFIG=/var/lib/classroom-offsite-backup/docker
ExecStart=/bin/sh $INSTALL_ROOT/deploy/verify-offsite-s3-restore.sh
StateDirectory=classroom-offsite-backup
StateDirectoryMode=0700
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/classroom-offsite-backup
EOF

cat > /etc/systemd/system/classroom-offsite-restore-check.timer <<'EOF'
[Unit]
Description=Verify the Classroom Review Agent off-site restore weekly

[Timer]
OnCalendar=Sun *-*-* 04:20:00 UTC
Persistent=true
RandomizedDelaySec=30m
Unit=classroom-offsite-restore-check.service

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now classroom-offsite-backup.timer classroom-offsite-restore-check.timer
echo "Off-site backup timers installed. Run each service once and inspect journalctl before relying on the schedule."
