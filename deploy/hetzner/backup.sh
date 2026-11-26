#!/bin/sh
# Daily Postgres backup. Works from cron (it moves to the repository folder itself): 0 3 * * * /opt/ringlark/deploy/hetzner/backup.sh
# The dump holds every call transcript, phone number and consent record, so it is readable by its owner only (umask 077).
# Set BACKUP_AGE_RECIPIENT to an age public key (https://age-encryption.org) to encrypt each dump; set BACKUP_COPY_TO to a folder
# on another disk or machine (for example a mounted share) to keep a second copy there. Neither is done for you.
set -eu
umask 077
cd "$(dirname "$0")/../.."
OUT="${BACKUP_DIR:-/var/backups/ringlark}"
mkdir -p "$OUT"
STAMP=$(date +%Y%m%d-%H%M)
FILE="$OUT/ringlark-$STAMP.dump"
TMP="$FILE.part"
trap 'rm -f -- "$TMP"' EXIT
docker compose exec -T db pg_dump -U ringlark -Fc ringlark > "$TMP"
test -s "$TMP"  # an empty file means pg_dump failed: stop here, nothing is kept and no older dump is pushed out
if [ -n "${BACKUP_AGE_RECIPIENT:-}" ]; then
  age -r "$BACKUP_AGE_RECIPIENT" -o "$FILE.age" "$TMP"
  FILE="$FILE.age"
else
  mv "$TMP" "$FILE"
fi
if [ -n "${BACKUP_COPY_TO:-}" ]; then cp -- "$FILE" "$BACKUP_COPY_TO"/; fi
# keep the newest 14 dumps
ls -1t "$OUT"/ringlark-*.dump* 2>/dev/null | tail -n +15 | while read -r old; do rm -f -- "$old"; done
echo "wrote $FILE"
