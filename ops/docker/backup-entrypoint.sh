#!/usr/bin/env bash
# Run the backup once a day at BACKUP_UTC_HOUR:BACKUP_UTC_MINUTE (default 03:30 UTC), and once at start if
# RUN_AT_START=1. A loop rather than cron so the container has one process and logs go to docker.
set -euo pipefail
# With arguments (docker compose run backup /backup.sh), run that and exit instead of looping.
if [ "$#" -gt 0 ]; then exec "$@"; fi
hour=${BACKUP_UTC_HOUR:-3}
minute=${BACKUP_UTC_MINUTE:-30}
if [ "${RUN_AT_START:-0}" = "1" ]; then /backup.sh || echo "backup failed (will retry at the scheduled time)"; fi
while true; do
  now=$(date -u +%s)
  next=$(date -u -d "$(date -u +%F) ${hour}:${minute}:00" +%s)
  [ "$next" -le "$now" ] && next=$((next + 86400))
  sleep $((next - now))
  /backup.sh || echo "backup failed"
done
