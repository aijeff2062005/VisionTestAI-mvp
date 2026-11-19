#!/usr/bin/env bash
# One-shot Tailscale install + join for Jetson (run ON the Jetson with sudo).
#   ssh ivision@192.168.1.125
#   bash ~/ImesPro/VisionTestAI/mvp_platform/deploy/jetson/join_tailscale.sh
set -euo pipefail

if ! command -v tailscale >/dev/null 2>&1; then
  curl -fsSL https://tailscale.com/install.sh | sh
fi

sudo tailscale up --hostname=jetson-clinic --accept-routes
echo
echo "==> Jetson Tailscale IP: $(sudo tailscale ip -4 | head -1)"
echo "    Then: REPLACE_AC=1 ~/ImesPro/VisionTestAI/mvp_platform/deploy/jetson/start_station.sh"
echo "    Smoke MQTT: nc -vz 100.84.47.73 1883"
echo "    Smoke Frappe: curl -sf https://aquamarine-leopon-37.tail82bd22.ts.net/api/method/frappe.ping"
