#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
[[ -s out/qy-arm64-images.tar.gz && -s out/docker-debs/PACKAGES.lock ]]
# Explicit allowlist excludes all generated secrets, .env and runtime backups.
tar -czf out/qy-jetson-config.tar.gz \
  .env.example compose.yml Dockerfile versions.env sources.lock.json \
  build.sh package.sh install.sh provision.sh init-mqtt.sh mariadb-client.cnf \
  bootstrap-docker.sh prepare_offline.sh wait-ready.sh healthcheck.py \
  backup.sh upgrade.sh rollback.sh ci_acceptance.sh runtime_acceptance.py browser_acceptance.py load_acceptance.py \
  prepare_recipe.py patch_portal.py verify_image.py verify_archive.py verify_sources.py \
  README.md PRODUCTION.md ACCEPTANCE.md mosquitto/mosquitto.conf \
  -C out docker-debs
(cd out && sha256sum qy-arm64-images.tar.gz qy-jetson-config.tar.gz > SHA256SUMS)
