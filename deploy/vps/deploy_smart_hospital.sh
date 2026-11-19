#!/usr/bin/env bash
# Hot-deploy smart_hospital into running Frappe containers (no image rebuild).
#
#   ./deploy_smart_hospital.sh              # sync backend + workers, restart Python processes
#
# Page JS (patient_registration / face_service_test) lives in the backend container.
# public/js assets are copied into BOTH backend app public and frontend nginx assets.
# Never wipe frontend assets/smart_hospital (MediaPipe lives there).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SSH_HOST="${VPS_SSH:-main.aquamarine-leopon-37.vupham.coder}"
REMOTE_DIR="${REMOTE_DIR:-/home/coder/workspace/VisionTestAI-mvp}"
APP_LOCAL="${ROOT}/services/hospital/smart-hospital/smart_hospital"
APP_REMOTE="${REMOTE_DIR}/mvp_platform/services/hospital/smart-hospital/smart_hospital"
BACKEND="${FRAPPE_BACKEND:-visiontestai-frappe-backend}"
WORKER_SHORT="${FRAPPE_WORKER_SHORT:-visiontestai-frappe-queue-short}"
WORKER_LONG="${FRAPPE_WORKER_LONG:-visiontestai-frappe-queue-long}"
SCHEDULER="${FRAPPE_SCHEDULER:-visiontestai-frappe-scheduler}"
FRONTEND="${FRAPPE_FRONTEND:-visiontestai-frappe-frontend}"
BENCH_APP="/home/frappe/frappe-bench/apps/smart_hospital/smart_hospital"
FRONTEND_ASSETS="/home/frappe/frappe-bench/assets/smart_hospital"
RESTART_BACKEND="${RESTART_BACKEND:-1}"
TV_SITE="${TRUNG_VUONG_SITE_HOST:-trungvuong.vision.primetek.ai}"
QY_SITE="${QUAN_Y_SITE_HOST:-qdymd.vision.primetek.ai}"

if [[ ! -d "${APP_LOCAL}" ]]; then
  echo "ERROR: missing app at ${APP_LOCAL}"
  exit 1
fi

echo "==> sync smart_hospital → ${SSH_HOST}:${APP_REMOTE}"
ssh "${SSH_HOST}" "mkdir -p '${APP_REMOTE}'"
COPYFILE_DISABLE=1 tar -C "${APP_LOCAL}" -czf - \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  --exclude '.git' \
  . | ssh "${SSH_HOST}" "tar --warning=no-unknown-keyword -C '${APP_REMOTE}' -xzf -"

echo "==> docker cp into ${BACKEND} (${BENCH_APP})"
ssh "${SSH_HOST}" bash -s <<EOF
set -euo pipefail
HOST_APP='${APP_REMOTE}'
BACKEND='${BACKEND}'
WORKER_SHORT='${WORKER_SHORT}'
WORKER_LONG='${WORKER_LONG}'
SCHEDULER='${SCHEDULER}'
FRONTEND='${FRONTEND}'
BENCH_APP='${BENCH_APP}'
FRONTEND_ASSETS='${FRONTEND_ASSETS}'
TV_SITE='${TV_SITE}'
QY_SITE='${QY_SITE}'

# Full app tree into backend (pages + api + public + overrides)
docker cp "\${HOST_APP}/." "\${BACKEND}:\${BENCH_APP}/"
docker cp "\${HOST_APP}/." "\${WORKER_SHORT}:\${BENCH_APP}/"
docker cp "\${HOST_APP}/." "\${WORKER_LONG}:\${BENCH_APP}/"
docker cp "\${HOST_APP}/." "\${SCHEDULER}:\${BENCH_APP}/"

# public/js → frontend nginx assets (merge overwrite; never rm -rf the tree)
if [[ -d "\${HOST_APP}/public/js" ]]; then
  docker exec "\${FRONTEND}" mkdir -p "\${FRONTEND_ASSETS}/js"
  # Top-level JS only — leave frontend lib/mediapipe alone
  for f in "\${HOST_APP}"/public/js/*.js; do
    [[ -f "\${f}" ]] || continue
    docker cp "\${f}" "\${FRONTEND}:\${FRONTEND_ASSETS}/js/\$(basename "\${f}")"
  done
fi

echo "==> migrate shared app on both hospital sites"
for SITE in frontend "\${QY_SITE}"; do
  docker exec "\${BACKEND}" test -d "/home/frappe/frappe-bench/sites/\${SITE}" || continue
  docker exec "\${BACKEND}" bench --site "\${SITE}" migrate
  docker exec "\${BACKEND}" bench --site "\${SITE}" clear-cache
done

if [[ "${RESTART_BACKEND}" == "1" ]]; then
  echo "==> restart backend, queue workers and scheduler (Python API changes)"
  docker restart "\${BACKEND}" "\${WORKER_SHORT}" "\${WORKER_LONG}" "\${SCHEDULER}" >/dev/null
  # wait briefly for ping
  for i in 1 2 3 4 5 6 7 8 9 10; do
    if docker exec "\${BACKEND}" curl -sf -H "Host: \${TV_SITE}" http://127.0.0.1:8000/api/method/frappe.ping >/dev/null 2>&1; then
      echo "==> backend up"
      break
    fi
    sleep 2
  done
fi
EOF

echo "==> done. Hard-refresh Desk (patient registration / face pages)."
echo "    Funnel: https://aquamarine-leopon-37.tail82bd22.ts.net"
