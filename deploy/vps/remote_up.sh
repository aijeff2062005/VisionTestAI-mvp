#!/usr/bin/env bash
# Deploy / update visiontestai on the Coder VPS.
# Safe: does not reboot, prune, or touch training workspaces.
#
# Default: mqtt + media + face_vectordb + qr_decode
# FRAPPE=1: also build/start Frappe on :8000 (stops FastAPI hospital)
# LEGACY_HOSPITAL=1: keep FastAPI hospital on :8000 (no Frappe)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SSH_HOST="${VPS_SSH:-main.aquamarine-leopon-37.vupham.coder}"
REMOTE_DIR="${REMOTE_DIR:-/home/coder/workspace/VisionTestAI-mvp}"
FRAPPE="${FRAPPE:-1}"
LEGACY_HOSPITAL="${LEGACY_HOSPITAL:-0}"

echo "==> sync mvp_platform → ${SSH_HOST}:${REMOTE_DIR} (tar over ssh)"
ssh "${SSH_HOST}" "mkdir -p '${REMOTE_DIR}'"
COPYFILE_DISABLE=1 tar --no-xattrs --no-mac-metadata -C "${ROOT}" -czf - \
  --exclude '.venv' \
  --exclude '__pycache__' \
  --exclude '.pytest_cache' \
  --exclude 'data' \
  --exclude '*.pyc' \
  --exclude 'deploy/vps/frappe/.frappe_docker' \
  . | ssh "${SSH_HOST}" "mkdir -p '${REMOTE_DIR}/mvp_platform' && tar --warning=no-unknown-keyword -C '${REMOTE_DIR}/mvp_platform' -xzf -"

echo "==> docker compose on VPS (FRAPPE=${FRAPPE} LEGACY_HOSPITAL=${LEGACY_HOSPITAL})"
ssh "${SSH_HOST}" bash -s <<EOF
set -euo pipefail
cd "${REMOTE_DIR}/mvp_platform/deploy/vps"
chmod 640 mosquitto_passwd 2>/dev/null || true
chown 1883:1883 mosquitto_passwd 2>/dev/null || true
chmod +x frappe/build_image.sh frappe/up_frappe.sh 2>/dev/null || true

# Core sidecar services
docker compose -p visiontestai --env-file ../env/lab.env.example up -d --build \
  mqtt media face_vectordb qr_decode

if [[ "${LEGACY_HOSPITAL}" == "1" ]]; then
  echo "==> legacy FastAPI hospital on :8000"
  docker compose -p visiontestai --env-file ../env/lab.env.example \
    --profile legacy-hospital up -d --build hospital
elif [[ "${FRAPPE}" == "1" ]]; then
  echo "==> Frappe clinic on :8000"
  ./frappe/up_frappe.sh
else
  echo "==> leaving :8000 alone (set FRAPPE=1 or LEGACY_HOSPITAL=1)"
fi

echo "==> containers"
docker ps --filter name=visiontestai --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
echo "==> training dirs still present"
ls -d /home/coder/workspace/SALAD /home/coder/workspace/Ops-SALAD /home/coder/workspace/IAD-R1 /home/coder/workspace/VID-AD 2>/dev/null || true
EOF

echo "==> done. Health (from VPS):"
ssh "${SSH_HOST}" 'curl -sf -H "Host: trungvuong.vision.primetek.ai" http://127.0.0.1:8000/api/method/frappe.ping || curl -sf http://127.0.0.1:8000/health; echo; curl -sf http://127.0.0.1:9010/health; echo; curl -sf http://127.0.0.1:9020/health; echo; curl -sf -H "X-Api-Key: dev-face-vdb-key" http://127.0.0.1:8100/health; echo'
