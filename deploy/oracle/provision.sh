#!/usr/bin/env bash
# Provision a fresh Ubuntu 24.04 (arm64) host for the Clipora staging stack.
#
# Run as root:  sudo bash provision.sh
#
# This script is intentionally conservative: it installs Docker and Compose,
# creates the unprivileged state directory, caps logs, hardens SSH, and opens
# only 80/443 in the host firewall. It does not start the application, obtain
# certificates, or change Oracle Cloud networking; see README.md for those.
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
    echo "run as root: sudo bash $0" >&2
    exit 1
fi

export DEBIAN_FRONTEND=noninteractive

# Non-interactive answers for packages that otherwise prompt.
echo "iptables-persistent iptables-persistent/autosave_v4 boolean true" | debconf-set-selections
echo "iptables-persistent iptables-persistent/autosave_v6 boolean true" | debconf-set-selections
echo "unattended-upgrades unattended-upgrades/enable_auto_updates boolean true" | debconf-set-selections

apt-get update
apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    docker.io \
    docker-compose-v2 \
    iptables \
    iptables-persistent \
    rsync \
    unattended-upgrades

systemctl enable --now docker
systemctl enable --now unattended-upgrades

# The deploy user owns the source tree; the app runs as UID 10001 and owns only
# its state directory.
DEPLOY_USER="${SUDO_USER:-ubuntu}"
if ! id -u "$DEPLOY_USER" >/dev/null 2>&1; then
    DEPLOY_USER=clipora
fi
if ! id -u clipora >/dev/null 2>&1; then
    useradd --create-home --shell /bin/bash clipora
fi
usermod -aG docker clipora
usermod -aG docker "$DEPLOY_USER" 2>/dev/null || true

install -d -m 0755 /opt/clipora
install -d -m 0755 -o "$DEPLOY_USER" -g "$DEPLOY_USER" /opt/clipora/src
install -d -m 0700 -o 10001 -g 10001 /opt/clipora/data

# Docker log rotation: a media proxy can log a lot, and an unbounded json-file
# log is a disk-fill risk.
install -d -m 0755 /etc/docker
cat >/etc/docker/daemon.json <<'JSON'
{
  "log-driver": "json-file",
  "log-opts": {"max-size": "10m", "max-file": "3"},
  "live-restore": true,
  "no-new-privileges": true
}
JSON
systemctl restart docker

# Cap the journal as well.
install -d -m 0755 /etc/systemd/journald.conf.d
cat >/etc/systemd/journald.conf.d/99-clipora.conf <<'CONF'
[Journal]
SystemMaxUse=200M
SystemMaxFileSize=50M
CONF
systemctl restart systemd-journald

# Oracle's Ubuntu images ship a restrictive INPUT chain that rejects everything
# except SSH. Open HTTP/HTTPS at the host as well as in the VCN security list.
# Rules are inserted at the top and then persisted.
for tool in iptables ip6tables; do
    command -v "$tool" >/dev/null 2>&1 || continue
    for port in 80 443; do
        "$tool" -C INPUT -p tcp --dport "$port" -j ACCEPT 2>/dev/null \
            || "$tool" -I INPUT -p tcp --dport "$port" -j ACCEPT
    done
    "$tool" -C INPUT -p udp --dport 443 -j ACCEPT 2>/dev/null \
        || "$tool" -I INPUT -p udp --dport 443 -j ACCEPT
done
netfilter-persistent save

# Key-only SSH. The instance was created with an SSH key, so password login is
# not needed. Validate before reloading so a typo cannot lock the host out.
install -d -m 0755 /etc/ssh/sshd_config.d
cat >/etc/ssh/sshd_config.d/99-clipora.conf <<'CONF'
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
CONF
sshd -t
systemctl reload ssh

cat <<'DONE'

Host provisioning finished.

Next:
  1. Point DNS at this host and confirm with: getent hosts <domain>
  2. Copy the repository to /opt/clipora/src (see README.md).
  3. Create deploy/staging/.env with CLIPORA_DOMAIN=<domain>.
  4. Run: docker compose up -d --build
DONE
