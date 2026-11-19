#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
[[ $EUID == 0 ]] || exit 1
next="${1:?Usage: sudo ./upgrade.sh IMAGE_TAG NEW_BACKUP_DIRECTORY}"
[[ "$next" == *:* && "$next" != *:latest ]] || exit 1
[[ $(docker image inspect --format '{{.Architecture}}' "$next") == arm64 ]]
bash ./backup.sh "${2:?New absolute backup directory required}"
exec 9>/var/lock/qy-jetson-install.lock
flock -n 9 || exit 1
docker compose stop frontend websocket worker scheduler backend
printf '\nCUSTOM_IMAGE=%s\n' "$next" >> .env
export CUSTOM_IMAGE="$next"
# Existing provisioner installs missing apps and migrates once for this upgrade.
docker compose up -d --force-recreate configurator provision
docker compose up -d backend websocket worker scheduler frontend
bash ./wait-ready.sh
echo 'Upgrade healthy. Run the clinical acceptance tests before opening writes.'
