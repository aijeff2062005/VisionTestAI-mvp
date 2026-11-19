#!/usr/bin/env bash
# Push clinic Tailscale / mic settings into Frappe site config (run on VPS).
#
#   VPS_FUNNEL_HOST=https://your-vps.ts.net \
#   CLINIC_MIC_URL=http://192.168.1.78:8092/audio.raw \
#   VPS_TAILNET_HOST=100.x.x.x \
#   ./set_site_clinic_config.sh
#
set -euo pipefail

FUNNEL="${VPS_FUNNEL_HOST:-}"
TS_IP="${VPS_TAILNET_HOST:-$(tailscale ip -4 2>/dev/null | head -1 || true)}"
MIC_URL="${CLINIC_MIC_URL:-http://192.168.1.78:8092/audio.raw}"
STATION_URL="${AIFACE_STATION_URL:-https://ubuntu.tailf560d4.ts.net}"

if [[ -z "${FUNNEL}" ]]; then
  FUNNEL="$(tailscale funnel status 2>/dev/null | grep -Eo 'https://[^ ]+' | head -1 | sed 's|/$||' || true)"
fi

CONTAINER="${FRAPPE_CONTAINER:-visiontestai-frappe-backend}"
QY_SITE="${QUAN_Y_SITE_HOST:-qdymd.vision.primetek.ai}"
SITES=(frontend "${QY_SITE}")

set_cfg() {
  local site="$1" key="$2" val="$3"
  docker exec "${CONTAINER}" bench --site "${site}" set-config "${key}" "${val}"
}

echo "==> Frappe site config (container=${CONTAINER})"
for site in "${SITES[@]}"; do
  docker exec "${CONTAINER}" test -d "/home/frappe/frappe-bench/sites/${site}" || continue
  echo "==> configuring ${site}"
  [[ "${site}" == frontend && -n "${FUNNEL}" ]] && set_cfg "${site}" visiontestai_vps_funnel_host "${FUNNEL}"
  [[ -n "${TS_IP}" ]] && set_cfg "${site}" visiontestai_vps_tailnet_host "${TS_IP}"
  set_cfg "${site}" visiontestai_mic_url "${MIC_URL}"
  set_cfg "${site}" visiontestai_aiface_station_url "${STATION_URL}"
  set_cfg "${site}" visiontestai_media_base "${MEDIA_BASE_URL:-http://media:9010}"
  set_cfg "${site}" visiontestai_face_vectordb_url "${FACE_VECTORDB_URL:-http://face_vectordb:8100}"
  docker exec "${CONTAINER}" bench --site "${site}" set-config -g home_page login 2>/dev/null || true
  docker exec -e SITE="${site}" "${CONTAINER}" bash -lc "cd /home/frappe/frappe-bench && ./env/bin/python - <<'PY'
import frappe
import os
frappe.init(site=os.environ['SITE'], sites_path='/home/frappe/frappe-bench/sites')
frappe.connect()
frappe.db.set_single_value('Website Settings', 'home_page', 'login')
frappe.db.commit()
frappe.clear_cache()
print('Website Settings home_page=login (guest /)')
PY" || true
  docker exec "${CONTAINER}" bench --site "${site}" clear-cache
done
echo "==> done"
