#!/usr/bin/env bash
# Knight Labs — deploy the latest code.
#
#     sudo bash /opt/knight-labs/deploy/update.sh
#
# Pulls main, restarts the service, and checks the site actually answers.
# Rolls back to the previous commit automatically if it does not.

set -euo pipefail

APP_DIR=/opt/knight-labs
PORT="${KL_PORT:-8123}"

if [[ $EUID -ne 0 ]]; then
  echo "Run with sudo: sudo bash $APP_DIR/deploy/update.sh" >&2
  exit 1
fi

cd "$APP_DIR"
PREVIOUS=$(git rev-parse HEAD)
echo "==> Current commit: ${PREVIOUS:0:7}"

echo "==> Fetching"
git fetch --quiet origin
TARGET=$(git rev-parse origin/main)
if [[ "$PREVIOUS" == "$TARGET" ]]; then
  echo "Already up to date. Nothing to deploy."
  exit 0
fi

echo "==> Deploying ${TARGET:0:7}"
git reset --hard --quiet origin/main
# The checkout is owned by the service user; keep it that way.
chown -R knightlabs:knightlabs "$APP_DIR"

# Refresh the unit and Caddy config in case they changed in this commit.
if ! diff -q deploy/knight-labs.service /etc/systemd/system/knight-labs.service.src >/dev/null 2>&1; then
  cp deploy/knight-labs.service /etc/systemd/system/knight-labs.service.src
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
git reset --hard --quiet "$PREVIOUS"
chown -R knightlabs:knightlabs "$APP_DIR"
systemctl restart knight-labs
sleep 2
if curl -fsS -o /dev/null "http://127.0.0.1:${PORT}/"; then
  echo "Rolled back successfully. Check logs: journalctl -u knight-labs -n 50" >&2
else
  echo "Rollback did not restore service either. Check: journalctl -u knight-labs -n 50" >&2
fi
exit 1
