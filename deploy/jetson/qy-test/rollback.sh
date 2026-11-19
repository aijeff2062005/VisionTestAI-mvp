#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
[[ $EUID == 0 ]] || { echo 'Run with sudo'; exit 1; }
backup="${1:?Usage: sudo ./rollback.sh /absolute/backup --restore-data}"
[[ ${2:-} == --restore-data && "$backup" == /* ]] || { echo 'Explicit --restore-data is required: replaces this test site database and files'; exit 1; }
exec 9>/var/lock/qy-jetson-install.lock
flock -n 9 || exit 1
(cd "$backup" && sha256sum -c SHA256SUMS)
set -a; source .env; set +a
current_site=$QY_SITE
current_project=$COMPOSE_PROJECT_NAME
# Refuse cross-site/cross-project restores.
set -a; source "$backup/deployment.env"; set +a
[[ "$QY_SITE" == "$current_site" && "$COMPOSE_PROJECT_NAME" == "$current_project" ]] || exit 1
docker compose stop frontend websocket worker scheduler backend
docker load -i "$backup/app-image.tar.gz"
CUSTOM_IMAGE=$(cat "$backup/image-id")
export CUSTOM_IMAGE
docker compose run --rm --no-deps --user 0 -e QY_SITE -e FRAPPE_DB_ROOT_PASSWORD -v "$backup:/backup:ro" --entrypoint bash backend -euc '
cp /backup/site_config.json "sites/$QY_SITE/site_config.json"
chown 1000:0 "sites/$QY_SITE/site_config.json"
shopt -s nullglob
db=(/backup/*database.sql.gz); public=(/backup/*-files.tar*); private=(/backup/*-private-files.tar*)
[[ ${#db[@]} == 1 && ${#public[@]} == 1 && ${#private[@]} == 1 ]]
# Set DB credentials through the environment, not host process arguments.
runuser -u frappe -- bench --site "$QY_SITE" --force restore "${db[0]}" --db-root-password "$FRAPPE_DB_ROOT_PASSWORD" --with-public-files "${public[0]}" --with-private-files "${private[0]}"
'
cp "$backup/deployment.env" .env
# Save the digest as runtime selection so tag reuse cannot silently select a new image.
printf '\nCUSTOM_IMAGE=%s\n' "$CUSTOM_IMAGE" >> .env
chmod 600 .env
docker compose up -d --no-deps backend websocket worker scheduler frontend
bash ./wait-ready.sh
echo 'Restored previous database, site key, attachments and application image.'
