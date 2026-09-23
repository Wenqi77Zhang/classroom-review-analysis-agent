#!/usr/bin/env sh
set -eu

REPOSITORY_URL=${REPOSITORY_URL:-https://github.com/Wenqi77Zhang/classroom-review-analysis-agent.git}
REPOSITORY_REF=${REPOSITORY_REF:-main}
INSTALL_ROOT=${INSTALL_ROOT:-/opt/classroom-review-agent}
SERVICE_USER=${SERVICE_USER:-classroom}

if [ "$(id -u)" -ne 0 ]; then
  echo "Run this bootstrap as root." >&2
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install --no-install-recommends -y ca-certificates curl git gnupg
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
. /etc/os-release
printf '%s\n' \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $VERSION_CODENAME stable" \
  > /etc/apt/sources.list.d/docker.list
apt-get update
apt-get install --no-install-recommends -y \
  docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
systemctl enable --now docker

# The largest Sydney Free Plan instance currently has 8 GiB RAM.  A private
# swap file prevents an Ollama/Whisper memory spike from killing PostgreSQL or
# the API, while the single-worker topology keeps normal requests in RAM.
if ! swapon --show=NAME --noheadings | grep -q '^/swapfile$'; then
  fallocate -l 8G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  printf '%s\n' '/swapfile none swap sw 0 0' >> /etc/fstab
fi

if ! id "$SERVICE_USER" >/dev/null 2>&1; then
  useradd --create-home --shell /bin/bash "$SERVICE_USER"
fi
usermod -aG docker "$SERVICE_USER"

if [ -e "$INSTALL_ROOT/.git" ]; then
  git -C "$INSTALL_ROOT" fetch --prune origin
else
  git clone "$REPOSITORY_URL" "$INSTALL_ROOT"
fi
git -C "$INSTALL_ROOT" checkout "$REPOSITORY_REF"
git -C "$INSTALL_ROOT" pull --ff-only origin "$REPOSITORY_REF"
chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_ROOT"

cat <<EOF
AWS host bootstrap completed.
Repository: $INSTALL_ROOT
Next: create $INSTALL_ROOT/.env.production with mode 0600, then run deploy/aws-start.sh.
EOF
