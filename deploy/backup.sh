#!/usr/bin/env bash
# Knight Labs — nightly snapshot of the live data.
#
# Runs from cron as the service user. Keeps 30 days of compressed snapshots of
# the JSON files. These are the only irreplaceable things on the server: the
# code is in git, but accounts, orders, inventory and analytics are not.

set -euo pipefail

DATA_DIR="${KL_DATA_DIR:-/var/lib/knight-labs}"
BACKUP_DIR="$DATA_DIR/backups"
KEEP_DAYS=30
STAMP=$(date -u +%Y%m%d-%H%M%S)

mkdir -p "$BACKUP_DIR"

FILES=()
for name in accounts.json orders.json inventory.json analytics.json admin-config.json affiliates.json; do
  [[ -f "$DATA_DIR/$name" ]] && FILES+=("$name")
done

if [[ ${#FILES[@]} -eq 0 ]]; then
  echo "Nothing to back up in $DATA_DIR"
  exit 0
fi

ARCHIVE="$BACKUP_DIR/knight-labs-$STAMP.tar.gz"
# smtp-config.json and telegram-config.json are deliberately excluded: they hold
# a mail password and a bot token, and a
# backup archive is a poor place for a credential.
tar -czf "$ARCHIVE" -C "$DATA_DIR" "${FILES[@]}"
chmod 600 "$ARCHIVE"

# Prune old snapshots.
find "$BACKUP_DIR" -name 'knight-labs-*.tar.gz' -mtime "+$KEEP_DAYS" -delete

COUNT=$(find "$BACKUP_DIR" -name 'knight-labs-*.tar.gz' | wc -l)
echo "Backed up ${#FILES[@]} files to $ARCHIVE (${COUNT} snapshots retained)"
