#!/bin/sh
# Daily Postgres backup. Run from the repository folder: deploy/hetzner/backup.sh
set -eu
OUT=/var/backups/ringlark
mkdir -p "$OUT"
STAMP=$(date +%Y%m%d-%H%M)
docker compose exec -T db pg_dump -U ringlark -Fc ringlark > "$OUT/ringlark-$STAMP.dump"
# keep the newest 14 dumps
ls -1t "$OUT"/ringlark-*.dump | tail -n +15 | while read -r old; do rm -f -- "$old"; done
echo "wrote $OUT/ringlark-$STAMP.dump"
