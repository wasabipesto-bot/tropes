# The nightly backup: sqlite3 for a consistent snapshot, rsync over ssh to the storage box.
FROM alpine:3.20
RUN apk add --no-cache bash sqlite rsync openssh-client gzip coreutils findutils tzdata
COPY ops/backup.sh /backup.sh
COPY ops/docker/backup-entrypoint.sh /entrypoint.sh
RUN chmod +x /backup.sh /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
