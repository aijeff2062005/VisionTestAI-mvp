#!/usr/bin/env bash
set -euo pipefail
INSTALL_START=$SECONDS
cd "$(dirname "$0")"
[[ $(uname -m) == aarch64 ]] || { echo 'Installer requires a native ARM64 Jetson.' >&2; exit 1; }
[[ $EUID == 0 ]] || { echo 'Run: sudo ./install.sh' >&2; exit 1; }
exec 9>/var/lock/qy-jetson-install.lock
flock -n 9 || { echo 'Another installation is active'; exit 1; }
bash ./bootstrap-docker.sh
command -v python3 >/dev/null
command -v curl >/dev/null
docker info >/dev/null
systemctl enable docker >/dev/null
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
if 'QY_BASE_URL' not in os.environ:
    import subprocess, re
    routes = subprocess.check_output(['ip','-4','route','get','1.1.1.1'], text=True)
    match = re.search(r'\bsrc\s+(\S+)', routes)
    if not match: raise SystemExit('Set QY_BASE_URL=http://JETSON_LAN_IP:18080 explicitly')
    values['QY_BASE_URL'] = f"http://{match.group(1)}:{values['FRONTEND_PORT']}"
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
available_kb=$(awk '/MemAvailable:/{print $2}' /proc/meminfo)
(( available_kb >= 1048576 )) || { echo 'Less than 1 GiB MemAvailable before install'; exit 1; }
docker_root=$(docker info --format '{{.DockerRootDir}}')
free_kb=$(df -Pk "$docker_root" | awk 'NR==2{print $4}')
(( free_kb >= 12582912 )) || { echo 'Need at least 12 GiB free on Docker storage'; exit 1; }
docker load -i "$BUNDLE_DIR/qy-arm64-images.tar.gz"
[[ $(docker image inspect --format '{{.Architecture}}' "$CUSTOM_IMAGE") == arm64 ]]
if [[ ! -s mosquitto/passwd || ! -s mosquitto/acl ]]; then
  bash ./init-mqtt.sh
fi
docker compose --env-file .env up -d
bash ./wait-ready.sh
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
echo 'Frontend routes LAN requests to the configured site; AC must use the reported URL.'

remaining_kb=$(awk '/MemAvailable:/{print $2}' /proc/meminfo)
(( remaining_kb >= 1048576 )) || { echo 'Services started but memory is below 1 GiB guardrail; not accepted. Inspect resource usage before proceeding.' >&2; exit 1; }
export INSTALL_ELAPSED_SECONDS=$((SECONDS - INSTALL_START))
python3 - <<'PYREPORT'
import json, os, platform, time
from pathlib import Path
Path('install-report.json').write_text(json.dumps({'timestamp':time.time(), 'architecture':platform.machine(), 'elapsed_seconds':int(os.environ['INSTALL_ELAPSED_SECONDS']), 'url':os.environ['QY_BASE_URL'], 'result':'HTTP_AND_HEALTH_PASS'}, indent=2))
PYREPORT
