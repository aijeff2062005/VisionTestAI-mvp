#!/usr/bin/env bash
# Tailscale clinic: public HTTPS Funnel for Frappe desk + tailnet IP for Jetson/MQTT.
#
# Run ON the Coder VPS (after: curl -fsSL https://tailscale.com/install.sh | sh && sudo tailscale up)
#
#   cd VisionTestAI/mvp_platform/deploy/vps
#   ./tailscale_clinic_up.sh
#
# Desk browser → https://<your-machine>.ts.net  (camera + mic work over HTTPS)
# Jetson       → VPS_TAILNET_IP:1883 / :9010 / :8100 / :9020  (no Mac bridge)
# Mac mic      → still http://<Mac-LAN-or-tailnet-IP>:8092/audio.raw
#
set -euo pipefail

if ! command -v tailscale >/dev/null 2>&1; then
  echo "ERROR: tailscale not installed. See https://tailscale.com/download"
  exit 1
fi

TS_IP="$(tailscale ip -4 2>/dev/null | head -1 || true)"
if [[ -z "${TS_IP}" ]]; then
  echo "ERROR: tailscale not connected — run: sudo tailscale up"
  exit 1
fi

echo "==> Tailnet IPv4: ${TS_IP}"
echo "    Jetson lab.env:  VPS_TAILNET_HOST=${TS_IP}"

# Public HTTPS for Frappe (desk camera/mic). Requires Tailscale funnel ACL approval.
# Funnel only allows public ports 443 / 8443 / 10000 — not arbitrary :8101.
echo "==> Enabling Tailscale Funnel → local :8000 (Frappe)"
tailscale funnel --bg --https=443 "http://127.0.0.1:8000" 2>/dev/null || \
  tailscale funnel --bg 443 "http://127.0.0.1:8000"

# POLAR-AD (or other web on :8101). Public URL uses :8443, not :8101.
if curl -sf --connect-timeout 2 -o /dev/null "http://127.0.0.1:8101/"; then
  echo "==> Enabling Tailscale Funnel :8443 → local :8101 (POLAR-AD)"
  tailscale funnel --bg --https=8443 "http://127.0.0.1:8101" 2>/dev/null || \
    tailscale funnel --bg 8443 "http://127.0.0.1:8101"
else
  echo "==> skip Funnel :8443 (nothing listening on 127.0.0.1:8101)"
fi

FUNNEL_HOST=""
if command -v jq >/dev/null 2>&1; then
  FUNNEL_HOST="$(tailscale funnel status --json 2>/dev/null | jq -r '.AllowFunnel[""][0].HostName // empty' | head -1)"
fi
if [[ -z "${FUNNEL_HOST}" ]]; then
  FUNNEL_HOST="$(tailscale funnel status 2>/dev/null | grep -Eo 'https://[^ ]+' | head -1 | sed 's|/$||; s|:8443$||')"
fi
if [[ -n "${FUNNEL_HOST}" ]]; then
  echo "==> Funnel URL: ${FUNNEL_HOST}"
  echo "    Desk: open ${FUNNEL_HOST}"
  echo "    POLAR-AD (public): ${FUNNEL_HOST}:8443/"
  echo "    Jetson: HOSPITAL_BASE_URL=${FUNNEL_HOST}"
else
  echo "==> Funnel status (copy HTTPS hostname for desk):"
  tailscale funnel status || true
fi

echo
echo "==> Smoke (on VPS):"
TV_SITE_HOST="${TRUNG_VUONG_SITE_HOST:-trungvuong.vision.primetek.ai}"
curl -sf --connect-timeout 3 -H "Host: ${TV_SITE_HOST}" "http://127.0.0.1:8000/api/method/frappe.ping" && echo "  frappe :8000 OK" || echo "  frappe :8000 FAIL"
curl -sf --connect-timeout 3 -o /dev/null "http://127.0.0.1:8101/" && echo "  polarad :8101 OK" || echo "  polarad :8101 skip/FAIL"
echo
echo "Next:"
echo "  1. ./set_site_clinic_config.sh   # bench site config (funnel + mic URL)"
echo "  2. On Jetson: VPS_TAILNET_HOST=${TS_IP} HOSPITAL_BASE_URL=${FUNNEL_HOST:-https://YOUR.ts.net} ./start_station.sh"
echo "  3. On Mac: ./deploy/mac/start_clinic_mic.sh  (mic stays on MacBook)"
