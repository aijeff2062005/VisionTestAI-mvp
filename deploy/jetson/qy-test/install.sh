#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
[[ $(uname -m) == aarch64 ]] || { echo 'Installer requires a native ARM64 Jetson.' >&2; exit 1; }
[[ $EUID == 0 ]] || { echo 'Run: sudo ./install.sh' >&2; exit 1; }
command -v python3 >/dev/null
command -v curl >/dev/null
if ! command -v docker >/dev/null || ! docker compose version >/dev/null 2>&1; then
  echo 'Docker Engine and Compose plugin required. For offline installation include OS-matched Docker packages; no network installer is run implicitly.' >&2
  exit 1
fi
docker info >/dev/null
BUNDLE_DIR="${BUNDLE_DIR:-$PWD/out}"
(cd "$BUNDLE_DIR" && sha256sum -c SHA256SUMS)
# Preserve existing configuration and generated credentials on every rerun.
if [[ ! -f .env ]]; then
  umask 077
  python3 - <<'PY'
import os, secrets, shlex
from pathlib import Path
values = dict(line.split('=', 1) for line in Path('.env.example').read_text().splitlines() if line and not line.startswith('#'))
for key in values:
    if key in os.environ:
        values[key] = os.environ[key]
for key in ('MQTT_PASSWORD', 'FRAPPE_ADMIN_PASSWORD', 'FRAPPE_DB_ROOT_PASSWORD'):
    if not values[key]: values[key] = secrets.token_hex(24)
Path('.env').write_text(''.join(f'{k}={shlex.quote(v)}\n' for k,v in values.items()))
PY
fi
chmod 600 .env
set -a
source .env
set +a
: "${QY_SITE:?}" "${FRONTEND_PORT:?}" "${CUSTOM_IMAGE:?}"
# Validate before starting or loading anything.
docker compose --env-file .env config --quiet
docker load -i "$BUNDLE_DIR/qy-arm64-images.tar.gz"
[[ $(docker image inspect --format '{{.Architecture}}' "$CUSTOM_IMAGE") == arm64 ]]
bash ./init-mqtt.sh
docker compose --env-file .env up -d
start=$SECONDS
timeout="${READY_TIMEOUT_SECONDS:-1800}"
until [[ $(curl --noproxy '*' --max-time 5 -fsS -H "Host: $QY_SITE" "http://127.0.0.1:$FRONTEND_PORT/api/method/ping" 2>/dev/null || true) == *'"pong"'* ]]; do
  if (( SECONDS - start > timeout )); then
    docker compose ps -a
    echo 'Readiness timeout; inspect provision logs. Data retained.' >&2
    exit 1
  fi
  sleep 5
done
printf 'Site ready: %s/desk/visioncare\nUser: Administrator\nCredentials: %s/.env (root-readable)\n' "$QY_BASE_URL" "$PWD"
echo 'LAN clients must resolve the configured hostname to the Jetson IP.'
