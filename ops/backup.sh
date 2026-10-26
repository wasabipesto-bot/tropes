#!/usr/bin/env bash
# Nightly backup (plan Phase 6): a consistent SQLite snapshot (VACUUM INTO, the site keeps running) kept as
# 14 daily and 8 weekly copies, plus the files that cannot be regenerated — evidence, posters, the owner's
# linked sources and the extracted texts — rsynced to the Hetzner storage box. Sheets and the lookup cache
# are regenerable and are not copied. Runs from the repo on the site's host; the timer is ops/tropes-backup.timer.
#
#   TROPES_BACKUP_REMOTE   rsync target, default braize:tropes (the `braize` ssh host, port 23)
#   TROPES_BACKUP_DAILY/WEEKLY   copies kept, default 14 and 8
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
DB=${DATABASE_PATH:-$ROOT/web/data/tropes.db}
REMOTE=${TROPES_BACKUP_REMOTE:-braize:tropes}
DAILY=${TROPES_BACKUP_DAILY:-14}
WEEKLY=${TROPES_BACKUP_WEEKLY:-8}
LOCAL=$ROOT/backups
mkdir -p "$LOCAL/daily" "$LOCAL/weekly"

stamp=$(date -u +%F)
snap="$LOCAL/daily/tropes-$stamp.sqlite"
rm -f "$snap" "$snap.gz" "$snap.tmp"
(cd "$ROOT/web" && npx tsx scripts/snapshot.ts "$DB" "$snap.tmp" >/dev/null)
mv "$snap.tmp" "$snap"
gzip -f "$snap"
if [ "$(date -u +%u)" = 7 ]; then cp -f "$snap.gz" "$LOCAL/weekly/"; fi
prune() { find "$1" -maxdepth 1 -name 'tropes-*.sqlite.gz' -printf '%T@ %p\n' | sort -rn | tail -n +"$(($2 + 1))" | cut -d' ' -f2- | xargs -r rm -f; }
prune "$LOCAL/daily" "$DAILY"
prune "$LOCAL/weekly" "$WEEKLY"
echo "snapshot $(du -h "$snap.gz" | cut -f1): $(ls "$LOCAL/daily" | wc -l) daily, $(ls "$LOCAL/weekly" | wc -l) weekly kept"

if [ -z "$REMOTE" ]; then echo "no remote; done"; exit 0; fi
# Snapshots mirror the local retention; files are only ever added remotely.
rsync -a --delete --mkpath "$LOCAL/" "$REMOTE/db/"
for d in web/data/evidence web/data/posters data/sources data/text; do
  [ -d "$ROOT/$d" ] || continue
  rsync -a --mkpath "$ROOT/$d/" "$REMOTE/$(basename "$d")/"
done
echo "copied to $REMOTE"
