#!/usr/bin/env bash
# Sync face gallery from VPS face_vectordb onto AiFace panel (on-device verify).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
AC="${ROOT}/services/assistant_controller"
ENV_FILE="${ROOT}/deploy/env/lab.env"
if [[ ! -f "${ENV_FILE}" ]]; then
  ENV_FILE="${ROOT}/deploy/env/lab.env.example"
fi
set -a; source "${ENV_FILE}"; set +a

if [[ -z "${VPS_HOST:-}" || "${VPS_HOST}" == "103.249.117.203" ]]; then
  VPS_HOST="${MAC_LAN_IP:-192.168.1.78}"
fi
export VPS_HOST
export FACE_VECTORDB_ENABLED=1
export FACE_VECTORDB_MODE=http
export FACE_VECTORDB_BASE_URL="${FACE_VECTORDB_BASE_URL:-http://${VPS_HOST}:8100}"
export FACE_VECTORDB_API_KEY="${FACE_VDB_API_KEY:-dev-face-vdb-key}"
export FACE_MODE=aiface
export FACE_HOST="${AIFACE_PANEL_IP:-192.168.1.18}"
export PYTHONPATH="${AC}/src${PYTHONPATH:+:$PYTHONPATH}"

PY="${AC}/.venv/bin/python"
if [[ ! -x "${PY}" ]]; then
  echo "ERROR: missing ${AC}/.venv — create once (see QUICKSTART 4b)"
  exit 1
fi

cd "${AC}"
echo "==> sync faces from ${FACE_VECTORDB_BASE_URL} → panel ${FACE_HOST}"
exec "${PY}" scripts/sync_faces_to_device.py --force-enable --config configs/default.yaml "$@"
