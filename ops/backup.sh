#!/usr/bin/env bash
# Nightly backup: a consistent SQLite snapshot kept as 14 daily and 8 weekly copies, plus the files that cannot
# be regenerated — evidence, posters, the owner's linked sources and the extracted texts — rsynced to the Hetzner
# storage box. Contact sheets and the lookup cache are regenerable and are not copied.
#
# Runs inside the backup container (see compose.yml) or on a host that has sqlite3 and rsync:
#   TROPES_DATA          the site's data directory (db, posters, evidence, texts)   default /data
#   TROPES_WORKER_DATA   the worker's data directory (sources, text cache)           default /worker-data
#   TROPES_BACKUP_LOCAL  where snapshots are kept                                     default /backups
#   TROPES_BACKUP_REMOTE rsync target, default braize:tropes; empty skips the copy
#   TROPES_BACKUP_DAILY / TROPES_BACKUP_WEEKLY  copies kept, default 14 and 8
set -euo pipefail
DATA=${TROPES_DATA:-/data}
WDATA=${TROPES_WORKER_DATA:-/worker-data}
LOCAL=${TROPES_BACKUP_LOCAL:-/backups}
REMOTE=${TROPES_BACKUP_REMOTE-braize:tropes}
DAILY=${TROPES_BACKUP_DAILY:-14}
WEEKLY=${TROPES_BACKUP_WEEKLY:-8}
mkdir -p "$LOCAL/daily" "$LOCAL/weekly"

stamp=$(date -u +%F)
snap="$LOCAL/daily/tropes-$stamp.sqlite"
rm -f "$snap" "$snap.gz" "$snap.tmp"
sqlite3 "$DATA/tropes.db" ".backup '$snap.tmp'"
mv "$snap.tmp" "$snap"
gzip -f "$snap"
if [ "$(date -u +%u)" = 7 ]; then cp -f "$snap.gz" "$LOCAL/weekly/"; fi
prune() { find "$1" -maxdepth 1 -name 'tropes-*.sqlite.gz' -printf '%T@ %p\n' | sort -rn | tail -n +"$(($2 + 1))" | cut -d' ' -f2- | xargs -r rm -f; }
prune "$LOCAL/daily" "$DAILY"
prune "$LOCAL/weekly" "$WEEKLY"
echo "$(date -u +%FT%TZ) snapshot $(du -h "$snap.gz" | cut -f1): $(ls "$LOCAL/daily" | wc -l) daily, $(ls "$LOCAL/weekly" | wc -l) weekly kept"

if [ -z "$REMOTE" ]; then echo "no remote; done"; exit 0; fi
# Snapshots mirror the local retention; files are only ever added remotely.
rsync -a --delete --mkpath "$LOCAL/" "$REMOTE/db/"
for d in "$DATA/evidence" "$DATA/posters" "$DATA/texts" "$WDATA/sources" "$WDATA/text"; do
  [ -d "$d" ] || continue
  rsync -a --mkpath "$d/" "$REMOTE/$(basename "$d")/"
done
echo "$(date -u +%FT%TZ) copied to $REMOTE"
