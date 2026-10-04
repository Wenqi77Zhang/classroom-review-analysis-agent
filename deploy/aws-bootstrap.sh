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
apt-get install --no-install-recommends -y ca-certificates curl git gnupg unzip

# Ubuntu 24.04 does not currently publish the awscli package in every EC2
# image repository configuration. Install AWS CLI v2 from AWS's official
# distribution so backup and restore timers do not depend on that package.
if ! command -v aws >/dev/null 2>&1; then
  case "$(dpkg --print-architecture)" in
    amd64) aws_cli_arch=x86_64 ;;
    arm64) aws_cli_arch=aarch64 ;;
    *)
      echo "Unsupported architecture for AWS CLI v2: $(dpkg --print-architecture)" >&2
      exit 1
      ;;
  esac
  aws_cli_tmp=$(mktemp -d)
  trap 'rm -rf "$aws_cli_tmp"' EXIT HUP INT TERM
  curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-${aws_cli_arch}.zip" \
    -o "$aws_cli_tmp/awscliv2.zip"
  (
    # Recovery sessions use umask 077 for secrets. Public executable files
    # must remain readable by the unprivileged backup service account.
    umask 022
    unzip -q "$aws_cli_tmp/awscliv2.zip" -d "$aws_cli_tmp"
    "$aws_cli_tmp/aws/install" --bin-dir /usr/local/bin --install-dir /usr/local/aws-cli
  )
  rm -rf "$aws_cli_tmp"
  trap - EXIT HUP INT TERM
fi
# Reconcile an earlier official install made with a restrictive caller umask.
# This tree contains vendor binaries only; production secrets stay mode 0600.
if [ -d /usr/local/aws-cli/v2 ]; then
  chmod -R a+rX /usr/local/aws-cli
fi
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
runuser -u "$SERVICE_USER" -- aws --version >/dev/null

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
