#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
[[ $EUID == 0 ]] || { echo 'Run with sudo'; exit 1; }
exec 9>/var/lock/qy-jetson-install.lock
flock -n 9 || exit 1
set -a; source .env; set +a
umask 077
backup="${1:?Usage: sudo ./backup.sh /absolute/new-backup-directory}"
[[ "$backup" == /* && ! -e "$backup" ]] || { echo 'Backup destination must be a new absolute directory'; exit 1; }
mkdir -m 700 "$backup"
cp .env "$backup/deployment.env"
docker image inspect --format '{{.Id}}' "$CUSTOM_IMAGE" > "$backup/image-id"
# Save exact prior application image for rollback even if a tag is overwritten.
docker save "$CUSTOM_IMAGE" | gzip > "$backup/app-image.tar.gz"
docker compose stop frontend websocket worker scheduler backend
# Leave services stopped on error so a partial backup cannot be treated as consistent.
docker compose run --rm --no-deps --user 0 -v "$backup:/backup" --entrypoint bash backend -euc '
chown 1000:0 /backup
runuser -u frappe -- bench --site "$QY_SITE" backup --with-files --compress --backup-path /backup
cp "sites/$QY_SITE/site_config.json" /backup/site_config.json
chown -R 0:0 /backup
chmod -R go-rwx /backup
'
(cd "$backup" && sha256sum ./* > SHA256SUMS)
docker compose up -d --no-deps backend websocket worker scheduler frontend
bash ./wait-ready.sh
printf 'Backup ready (contains secrets): %s\nCopy securely off the device.\n' "$backup"
