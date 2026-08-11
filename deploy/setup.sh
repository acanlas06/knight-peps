#!/usr/bin/env bash
# Knight Labs — one-time server setup for a fresh Hetzner Ubuntu box.
#
# Run as root on a brand new server:
#     bash setup.sh yourdomain.com
#
# What it does:
#   - creates an unprivileged service user (the app never runs as root)
#   - installs Python and Caddy
#   - clones the repo to /opt/knight-labs and puts live data in /var/lib
#   - installs the systemd service and Caddy config
#   - locks the firewall down to SSH + HTTP + HTTPS
#   - enables automatic security updates
#
# It is safe to re-run; existing pieces are left alone.

set -euo pipefail

DOMAIN="${1:-}"
REPO="${KL_REPO:-https://github.com/acanlas06/knight-peps.git}"
APP_DIR=/opt/knight-labs
DATA_DIR=/var/lib/knight-labs
SERVICE_USER=knightlabs
PORT="${KL_PORT:-8123}"

if [[ -z "$DOMAIN" ]]; then
  echo "Usage: bash setup.sh yourdomain.com" >&2
  exit 1
fi
if [[ $EUID -ne 0 ]]; then
  echo "Run this as root: sudo bash setup.sh $DOMAIN" >&2
  exit 1
fi

echo "==> Knight Labs setup for ${DOMAIN}"

echo "==> Installing packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq \
  python3 git ufw curl ca-certificates \
  debian-keyring debian-archive-keyring apt-transport-https \
  unattended-upgrades

# Caddy handles HTTPS certificates automatically — no certbot cron to forget.
if ! command -v caddy >/dev/null 2>&1; then
  echo "==> Installing Caddy"
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
    | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
    > /etc/apt/sources.list.d/caddy-stable.list
  apt-get update -qq
  apt-get install -y -qq caddy
fi

echo "==> Creating service user '${SERVICE_USER}'"
id -u "$SERVICE_USER" >/dev/null 2>&1 || \
  useradd --system --create-home --shell /usr/sbin/nologin "$SERVICE_USER"

echo "==> Fetching application to ${APP_DIR}"
if [[ -d "$APP_DIR/.git" ]]; then
  # On a re-run the checkout is already owned by the service user, so git must
  # run as that user: as root it refuses with "dubious ownership". Adding
  # safe.directory would silence it but give up a real protection, since a
  # compromised service account could plant a hook for root to execute.
  if command -v runuser >/dev/null 2>&1; then
    runuser -u "$SERVICE_USER" -- git -C "$APP_DIR" fetch --quiet origin
    runuser -u "$SERVICE_USER" -- git -C "$APP_DIR" reset --hard --quiet origin/main
  else
    sudo -u "$SERVICE_USER" -H git -C "$APP_DIR" fetch --quiet origin
    sudo -u "$SERVICE_USER" -H git -C "$APP_DIR" reset --hard --quiet origin/main
  fi
else
  git clone --quiet "$REPO" "$APP_DIR"
fi

echo "==> Preparing data directory ${DATA_DIR}"
# Live data lives outside the checkout so deploys never touch it.
mkdir -p "$DATA_DIR/outbox" "$DATA_DIR/backups"
chown -R "$SERVICE_USER:$SERVICE_USER" "$DATA_DIR" "$APP_DIR"
# Only the service user may read the secrets and customer data.
chmod 750 "$DATA_DIR"

# Seed config placeholders if absent. Real values are added by hand afterwards.
if [[ ! -f "$DATA_DIR/admin-config.json" ]]; then
  echo '{"admins":[]}' > "$DATA_DIR/admin-config.json"
  chown "$SERVICE_USER:$SERVICE_USER" "$DATA_DIR/admin-config.json"
  chmod 640 "$DATA_DIR/admin-config.json"
fi
if [[ ! -f "$DATA_DIR/smtp-config.json" ]]; then
  cat > "$DATA_DIR/smtp-config.json" <<'JSON'
{
  "host": "smtp.gmail.com",
  "port": 587,
  "tls": true,
  "user": "knightpeps@gmail.com",
  "from": "knightpeps@gmail.com",
  "password": "PUT_YOUR_APP_PASSWORD_HERE"
}
JSON
  chown "$SERVICE_USER:$SERVICE_USER" "$DATA_DIR/smtp-config.json"
  chmod 600 "$DATA_DIR/smtp-config.json"
fi

echo "==> Installing systemd service"
sed -e "s|__APP_DIR__|$APP_DIR|g" \
    -e "s|__DATA_DIR__|$DATA_DIR|g" \
    -e "s|__USER__|$SERVICE_USER|g" \
    -e "s|__PORT__|$PORT|g" \
    -e "s|__DOMAIN__|$DOMAIN|g" \
    "$APP_DIR/deploy/knight-labs.service" > /etc/systemd/system/knight-labs.service
systemctl daemon-reload
systemctl enable --now knight-labs

echo "==> Configuring Caddy for ${DOMAIN}"
sed -e "s|__DOMAIN__|$DOMAIN|g" \
    -e "s|__PORT__|$PORT|g" \
    "$APP_DIR/deploy/Caddyfile" > /etc/caddy/Caddyfile
systemctl reload caddy 2>/dev/null || systemctl restart caddy

echo "==> Firewall"
ufw allow OpenSSH >/dev/null
ufw allow 80/tcp  >/dev/null
ufw allow 443/tcp >/dev/null
ufw --force enable >/dev/null
# Note: the Python server binds 127.0.0.1 only, so it is unreachable from
# outside regardless of firewall rules. Caddy is the only public listener.

echo "==> Automatic security updates"
dpkg-reconfigure -f noninteractive unattended-upgrades >/dev/null 2>&1 || true

echo "==> Nightly backups"
install -m 755 "$APP_DIR/deploy/backup.sh" /usr/local/bin/knight-labs-backup
cat > /etc/cron.d/knight-labs-backup <<CRON
# Nightly snapshot of the JSON data files at 03:15
15 3 * * * $SERVICE_USER /usr/local/bin/knight-labs-backup >/dev/null 2>&1
CRON

echo
echo "========================================================"
echo " Setup complete."
echo
echo " Still to do:"
echo "   1. Point DNS: an A record for ${DOMAIN} -> this server's IP"
echo "      (Caddy cannot get a certificate until DNS resolves here.)"
echo "   2. Add your Gmail app password:"
echo "        nano ${DATA_DIR}/smtp-config.json"
echo "   3. Register your admin account on the live site, then add it:"
echo "        nano ${DATA_DIR}/admin-config.json"
echo "   4. Restart to pick up the mail config:"
echo "        systemctl restart knight-labs"
echo
echo " Check status:  systemctl status knight-labs caddy"
echo " Watch logs:    journalctl -u knight-labs -f"
echo "========================================================"
