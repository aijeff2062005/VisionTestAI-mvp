#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
[[ -s out/qy-arm64-images.tar.gz ]] || { echo 'Build images first' >&2; exit 1; }
# Explicit allowlist: never package .env, generated MQTT credentials or site backups.
tar -czf out/qy-jetson-config.tar.gz \
  .env.example compose.yml Dockerfile versions.env sources.lock.json \
  build.sh package.sh install.sh provision.sh init-mqtt.sh mariadb-client.cnf \
  prepare_recipe.py patch_portal.py verify_image.py verify_archive.py \
  README.md PRODUCTION.md mosquitto/mosquitto.conf
(cd out && sha256sum qy-arm64-images.tar.gz qy-jetson-config.tar.gz > SHA256SUMS)
echo 'Bundle: out/{qy-arm64-images.tar.gz,qy-jetson-config.tar.gz,SHA256SUMS}'
