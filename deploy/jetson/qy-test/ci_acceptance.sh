#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
[[ $(uname -m) == aarch64 ]] || exit 1
# Run only in an ephemeral CI runner, never against an existing operator site.
[[ ${GITHUB_ACTIONS:-} == true && ! -e .env ]] || { echo 'Requires fresh GitHub runner'; exit 1; }
export QY_SITE=qy-ci.lan QY_BASE_URL=http://127.0.0.1:18080 STATION_ID=qy-ci-01
sudo -E QY_INSTALL_DIR="$PWD" READY_TIMEOUT_SECONDS=1800 bash out/qy-jetson-install.run
# CI owns the ephemeral credentials file; production installer keeps it root-only.
sudo chown "$(id -u):$(id -g)" .env
set -a; source .env; set +a
for secret in "$FRAPPE_ADMIN_PASSWORD" "$FRAPPE_DB_ROOT_PASSWORD" "$MQTT_PASSWORD"; do printf '::add-mask::%s\n' "$secret"; done
# Login proves an actual site rather than a static proxy health response.
python3 - <<'PY'
import os, urllib.request, urllib.parse, http.cookiejar
jar=http.cookiejar.CookieJar()
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPCookieProcessor(jar))
data=urllib.parse.urlencode({'usr':'Administrator','pwd':os.environ['FRAPPE_ADMIN_PASSWORD']}).encode()
r=opener.open(urllib.request.Request('http://127.0.0.1:18080/api/method/login',data=data),timeout=30)
assert r.status==200 and any(c.name=='sid' for c in jar)
r=opener.open('http://127.0.0.1:18080/desk/visioncare',timeout=30)
assert r.status==200
print('Administrator login and authenticated Desk route: PASS')
PY
docker compose exec -T backend ./env/bin/python < runtime_acceptance.py > out/acceptance-runtime.json
docker compose cp "backend:/home/frappe/frappe-bench/sites/$QY_SITE/private/files/qy-arm64-report.pdf" out/qy-arm64-report.pdf
# Full container stop/start tests volume survival, not a physical device reboot.
docker compose stop db redis-cache redis-queue mqtt backend frontend worker scheduler websocket
docker compose start db redis-cache redis-queue mqtt backend frontend worker scheduler websocket
bash ./wait-ready.sh
docker compose exec -T -e CHECK_PERSISTENCE=1 backend ./env/bin/python < runtime_acceptance.py > out/acceptance-restart.json
backup="$PWD/out/ci-backup"
sudo ./backup.sh "$backup"
docker compose exec -T -e BREAK_PERSISTENCE=1 backend ./env/bin/python < runtime_acceptance.py
sudo ./rollback.sh "$backup" --restore-data
sudo chown "$(id -u):$(id -g)" .env
docker compose exec -T -e CHECK_PERSISTENCE=1 backend ./env/bin/python < runtime_acceptance.py > out/acceptance-restore.json
python3 load_acceptance.py
sudo cp install-report.json out/acceptance-install.json
sudo chown "$(id -u):$(id -g)" out/acceptance-install.json
docker compose ps -a
