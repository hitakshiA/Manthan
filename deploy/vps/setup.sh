#!/usr/bin/env bash
# Manthan - generic VPS bootstrap.
#
# Idempotent installer for a fresh Ubuntu 22.04 / 24.04 VPS (DigitalOcean,
# Vultr, Linode, Hetzner, AWS Lightsail - anywhere that gives you an Ubuntu
# box with root SSH). Installs Docker + compose, clones the repo, writes a
# placeholder .env, opens the firewall, and runs `docker compose up -d`.
#
# Manual usage:
#   curl -fsSL https://raw.githubusercontent.com/akash-mondal/manthan/main/deploy/vps/setup.sh | bash
#
# After it finishes:
#   ssh root@<your-vps-ip>
#   nano /opt/manthan/.env                    # paste your GEMINI_API_KEY
#   docker compose -f /opt/manthan/docker-compose.yml restart

set -euo pipefail

REPO_URL="${MANTHAN_REPO_URL:-https://github.com/akash-mondal/manthan.git}"
INSTALL_DIR="${MANTHAN_INSTALL_DIR:-/opt/manthan}"
BRANCH="${MANTHAN_BRANCH:-main}"

echo "──────────────────────────────────────────────────────────────"
echo "  Manthan · VPS bootstrap"
echo "    repo:    $REPO_URL"
echo "    branch:  $BRANCH"
echo "    install: $INSTALL_DIR"
echo "──────────────────────────────────────────────────────────────"

# 1. base packages
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq \
  ca-certificates curl git gnupg lsb-release ufw

# 2. Docker (official convenience script - idempotent)
if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sh
fi
systemctl enable --now docker

# 3. clone (or update) the repo
if [[ -d "$INSTALL_DIR/.git" ]]; then
  echo "→ updating existing checkout at $INSTALL_DIR"
  git -C "$INSTALL_DIR" fetch --quiet origin "$BRANCH"
  git -C "$INSTALL_DIR" reset --hard "origin/$BRANCH"
else
  echo "→ cloning into $INSTALL_DIR"
  mkdir -p "$(dirname "$INSTALL_DIR")"
  git clone --depth 1 -b "$BRANCH" "$REPO_URL" "$INSTALL_DIR"
fi

# 4. placeholder .env if absent
if [[ ! -f "$INSTALL_DIR/.env" ]]; then
  cp "$INSTALL_DIR/.env.example" "$INSTALL_DIR/.env"
  echo "→ wrote placeholder .env at $INSTALL_DIR/.env"
  echo "  (paste your GEMINI_API_KEY before the next restart)"
fi

# 5. minimal firewall - SSH + 80 + 443 + the FastAPI port if you want direct access
ufw --force reset >/dev/null
ufw default deny incoming >/dev/null
ufw default allow outgoing >/dev/null
ufw allow ssh >/dev/null
ufw allow 80/tcp >/dev/null
ufw allow 443/tcp >/dev/null
ufw allow 8000/tcp >/dev/null
ufw --force enable >/dev/null

# 6. up the stack
cd "$INSTALL_DIR"
docker compose up -d --build

PUBLIC_IP="$(curl -fsSL https://ifconfig.me 2>/dev/null || echo "<your-vps-ip>")"

echo
echo "──────────────────────────────────────────────────────────────"
echo "  ✓ Manthan is up at http://${PUBLIC_IP}:8000/"
echo
echo "  Next steps:"
echo "    1. ssh root@${PUBLIC_IP}"
echo "    2. nano ${INSTALL_DIR}/.env"
echo "       - paste your GEMINI_API_KEY from https://aistudio.google.com/apikey"
echo "    3. docker compose -f ${INSTALL_DIR}/docker-compose.yml restart"
echo
echo "  To put a hostname + TLS in front, see deploy/vps/Caddyfile.example"
echo "──────────────────────────────────────────────────────────────"
