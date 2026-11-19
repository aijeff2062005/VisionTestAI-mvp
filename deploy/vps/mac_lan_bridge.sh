#!/usr/bin/env bash
# Bridge private Coder VPS hospital ports onto this Mac's LAN IP so Jetson can reach them.
# VPS is not publicly reachable; Mac is on clinic LAN (e.g. 192.168.1.78).
#
# Keep this running while the clinic is active. Ctrl+C to stop.
#
#   ./mac_lan_bridge.sh
#
set -euo pipefail

WORKSPACE="${CODER_WORKSPACE:-vupham/aquamarine-leopon-37}"
TV_SITE_HOST="${TRUNG_VUONG_SITE_HOST:-trungvuong.vision.primetek.ai}"
LAN_IP="${MAC_LAN_IP:-}"
if [[ -z "${LAN_IP}" ]]; then
  LAN_IP="$(ipconfig getifaddr en0 2>/dev/null || true)"
fi
if [[ -z "${LAN_IP}" ]]; then
  LAN_IP="$(ipconfig getifaddr en1 2>/dev/null || true)"
fi
if [[ -z "${LAN_IP}" ]]; then
  echo "ERROR: set MAC_LAN_IP (could not detect en0/en1)"
  exit 1
fi

PORTS=(1883 8000 9010 8100 9020)

# Already bridged? (e.g. previous terminal / agent session)
# Frappe exposes /api/method/frappe.ping; legacy FastAPI uses /health.
if curl -sf --connect-timeout 1 -H "Host: ${TV_SITE_HOST}" "http://${LAN_IP}:8000/api/method/frappe.ping" >/dev/null 2>&1 \
  || curl -sf --connect-timeout 1 "http://${LAN_IP}:8000/health" >/dev/null 2>&1; then
  echo "==> Bridge already up on ${LAN_IP} (hospital :8000 OK)."
  echo "    Jetson VPS_HOST=${LAN_IP} — nothing to do."
  echo "    To restart: kill the existing 'coder port-forward' then re-run this script."
  pgrep -lf "coder port-forward ${WORKSPACE}" || pgrep -lf 'coder port-forward' || true
  exit 0
fi

ARGS=()
for p in "${PORTS[@]}"; do
  if lsof -nP -iTCP:"${p}" -sTCP:LISTEN 2>/dev/null | grep -q "${LAN_IP}:${p}"; then
    echo "ERROR: ${LAN_IP}:${p} already in use but hospital health failed."
    echo "       Free it: lsof -nP -iTCP:${p} -sTCP:LISTEN"
    exit 1
  fi
  ARGS+=(--tcp "${LAN_IP}:${p}:${p}")
done

echo "==> Bridging ${WORKSPACE} → ${LAN_IP}:{${PORTS[*]}}"
echo "    Jetson should use VPS_HOST=${LAN_IP}"
echo "    Leave this terminal open. Ctrl+C stops the bridge."
echo

exec coder port-forward "${WORKSPACE}" "${ARGS[@]}"
