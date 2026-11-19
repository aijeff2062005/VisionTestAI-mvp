#!/usr/bin/env bash
# Bring up Frappe clinic stack on VPS (same project visiontestai).
# Stops FastAPI hospital_api so :8000 is free for Frappe frontend.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VPS_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${ENV_FILE:-${VPS_DIR}/../env/lab.env.example}"
CUSTOM_IMAGE="${CUSTOM_IMAGE:-visiontestai/frappe:clinic}"

cd "${VPS_DIR}"

if ! docker image inspect "${CUSTOM_IMAGE}" >/dev/null 2>&1; then
  echo "==> ${CUSTOM_IMAGE} missing — building (long)"
  bash "${SCRIPT_DIR}/build_image.sh"
fi

echo "==> stop FastAPI hospital on :8000 (if running)"
docker compose -p visiontestai --env-file "${ENV_FILE}" stop hospital 2>/dev/null || true
docker compose -p visiontestai --env-file "${ENV_FILE}" rm -f hospital 2>/dev/null || true

echo "==> up mqtt/media/face_vectordb/qr_decode + frappe"
export CUSTOM_IMAGE
docker compose -p visiontestai --env-file "${ENV_FILE}" \
  -f docker-compose.yml \
  -f frappe/compose.yml \
  up -d --build mqtt media face_vectordb qr_decode \
  frappe-db frappe-redis-cache frappe-redis-queue \
  frappe-configurator frappe-create-site \
  frappe-backend frappe-websocket frappe-queue-short frappe-queue-long \
  frappe-scheduler frappe-frontend

echo "==> containers"
docker ps --filter name=visiontestai --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'

echo "==> smoke (Frappe ping + media + mqtt ports)"
sleep 5
TV_SITE_HOST="${TRUNG_VUONG_SITE_HOST:-$(awk -F= '$1 == "TRUNG_VUONG_SITE_HOST" { value=$2 } END { print value }' "${ENV_FILE}" 2>/dev/null)}"
TV_SITE_HOST="${TV_SITE_HOST:-trungvuong.vision.primetek.ai}"
curl -sf -H "Host: ${TV_SITE_HOST}" "http://127.0.0.1:8000/api/method/frappe.ping" && echo || echo "WARN: frappe ping not ready yet"
curl -sf "http://127.0.0.1:9010/health" && echo
curl -sf "http://127.0.0.1:9020/health" && echo || echo "WARN: qr_decode not ready"
curl -sf -H "X-Api-Key: ${FACE_VDB_API_KEY:-dev-face-vdb-key}" "http://127.0.0.1:8100/health" && echo
