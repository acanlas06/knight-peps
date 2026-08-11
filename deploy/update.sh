#!/usr/bin/env bash
# Knight Labs — deploy the latest code.
#
#     sudo bash /opt/knight-labs/deploy/update.sh
#
# Pulls main, restarts the service, and checks the site actually answers.
# Rolls back to the previous commit automatically if it does not.

set -euo pipefail

APP_DIR=/opt/knight-labs
SERVICE_USER=knightlabs
PORT="${KL_PORT:-8123}"

if [[ $EUID -ne 0 ]]; then
  echo "Run with sudo: sudo bash $APP_DIR/deploy/update.sh" >&2
  exit 1
fi

# The checkout is owned by the service user, so run git AS that user rather
# than as root. Doing it as root trips git's dubious-ownership guard, and the
# usual workaround (adding safe.directory) removes a real protection: a
# compromised service account could plant a hook in .git and have root run it.
if command -v runuser >/dev/null 2>&1; then
  git_svc() { runuser -u "$SERVICE_USER" -- git -C "$APP_DIR" "$@"; }
elif command -v sudo >/dev/null 2>&1; then
  git_svc() { sudo -u "$SERVICE_USER" -H git -C "$APP_DIR" "$@"; }
else
  echo "Need runuser or sudo to run git as ${SERVICE_USER}." >&2
  exit 1
fi

PREVIOUS=$(git_svc rev-parse HEAD)
echo "==> Current commit: ${PREVIOUS:0:7}"

echo "==> Fetching"
git_svc fetch --quiet origin
TARGET=$(git_svc rev-parse origin/main)
if [[ "$PREVIOUS" == "$TARGET" ]]; then
  echo "Already up to date. Nothing to deploy."
  exit 0
fi

echo "==> Deploying ${TARGET:0:7}"
git_svc reset --hard --quiet origin/main
# Belt and braces: anything git created is already service-user owned, but a
# previous root-run deploy may have left root-owned files behind.
chown -R "$SERVICE_USER:$SERVICE_USER" "$APP_DIR"

# Refresh the unit and Caddy config if this commit changed them. The previous
# version of this block only copied the template to a ".src" file that nothing
# ever read, so unit changes silently never reached systemd.
UNIT=/etc/systemd/system/knight-labs.service
CADDYFILE=/etc/caddy/Caddyfile

# Recover the values setup.sh substituted, so we can re-render faithfully.
DOMAIN=$(sed -n 's|^Environment=KL_BASE_URL=https\?://\(.*\)$|\1|p' "$UNIT" | head -1)
DATA_DIR=$(sed -n 's|^Environment=KL_DATA_DIR=\(.*\)$|\1|p' "$UNIT" | head -1)
DATA_DIR="${DATA_DIR:-/var/lib/knight-labs}"

render_unit() {
  sed -e "s|__APP_DIR__|$APP_DIR|g" \
      -e "s|__DATA_DIR__|$DATA_DIR|g" \
      -e "s|__USER__|$SERVICE_USER|g" \
      -e "s|__PORT__|$PORT|g" \
      -e "s|__DOMAIN__|$DOMAIN|g" \
      "$APP_DIR/deploy/knight-labs.service"
}

if [[ -n "$DOMAIN" ]]; then
  if ! render_unit | diff -q - "$UNIT" >/dev/null 2>&1; then
    echo "==> Unit file changed; reinstalling"
    render_unit > "$UNIT"
    systemctl daemon-reload
  fi

  RENDERED_CADDY=$(sed -e "s|__DOMAIN__|$DOMAIN|g" -e "s|__PORT__|$PORT|g" \
                       "$APP_DIR/deploy/Caddyfile")
  if ! printf '%s\n' "$RENDERED_CADDY" | diff -q - "$CADDYFILE" >/dev/null 2>&1; then
    echo "==> Caddy config changed; reinstalling"
    printf '%s\n' "$RENDERED_CADDY" > "$CADDYFILE"
    systemctl reload caddy 2>/dev/null || systemctl restart caddy
  fi
else
  echo "    (could not read the domain from $UNIT; skipping config refresh)" >&2
fi

echo "==> Restarting"
systemctl restart knight-labs

echo "==> Health check"
sleep 2
for attempt in 1 2 3 4 5; do
  if curl -fsS -o /dev/null "http://127.0.0.1:${PORT}/"; then
    echo "==> OK — serving on port ${PORT}"
    echo "==> Deployed ${TARGET:0:7}"
    exit 0
  fi
  echo "    attempt ${attempt} failed, retrying..."
  sleep 2
done

echo "!!! Site is not responding after deploy. Rolling back to ${PREVIOUS:0:7}" >&2
git_svc reset --hard --quiet "$PREVIOUS"
chown -R "$SERVICE_USER:$SERVICE_USER" "$APP_DIR"
systemctl restart knight-labs
sleep 2
if curl -fsS -o /dev/null "http://127.0.0.1:${PORT}/"; then
  echo "Rolled back successfully. Check logs: journalctl -u knight-labs -n 50" >&2
else
  echo "Rollback did not restore service either. Check: journalctl -u knight-labs -n 50" >&2
fi
exit 1
