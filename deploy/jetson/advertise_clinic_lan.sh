#!/usr/bin/env bash
# Advertise clinic LAN (192.168.1.0/24) over Tailscale from this Jetson.
# After approving the route in Tailscale Admin, any device on your tailnet
# (home Mac/phone) can open AiFace at http://192.168.1.18/ as if at the office.
#
# Run ON Jetson (needs sudo):
#   bash ~/ImesPro/VisionTestAI/mvp_platform/deploy/jetson/advertise_clinic_lan.sh
#
# Then in https://login.tailscale.com/admin/machines → jetson-clinic →
#   approve route 192.168.1.0/24
#
# Alternative (no admin approval): from home Mac run
#   ./deploy/mac/bridge_clinic_lan_via_jetson.sh
#   → http://127.0.0.1:18080/  (AiFace web UI)
#
set -euo pipefail

LAN_CIDR="${CLINIC_LAN_CIDR:-192.168.1.0/24}"
AIFACE_IP="${AIFACE_PANEL_IP:-192.168.1.18}"

if ! command -v tailscale >/dev/null 2>&1; then
  echo "ERROR: tailscale not installed. Run: deploy/jetson/join_tailscale.sh"
  exit 1
fi

echo "==> Enabling IP forwarding (needed for subnet router)"
echo 1 | sudo -S sysctl -w net.ipv4.ip_forward=1 >/dev/null
# Persist across reboot
if [[ ! -f /etc/sysctl.d/99-tailscale-forward.conf ]]; then
  echo 1 | sudo -S tee /etc/sysctl.d/99-tailscale-forward.conf >/dev/null <<'EOF'
net.ipv4.ip_forward = 1
EOF
fi

echo "==> Advertising ${LAN_CIDR} via Tailscale"
echo 1 | sudo -S tailscale set --advertise-routes="${LAN_CIDR}" --accept-routes

TS_IP="$(echo 1 | sudo -S tailscale ip -4 | head -1)"
echo
echo "==> Jetson Tailscale IP: ${TS_IP}"
echo "    AiFace on LAN:      http://${AIFACE_IP}/"
echo
echo "NEXT (required once):"
echo "  1. Open https://login.tailscale.com/admin/machines"
echo "  2. Select jetson-clinic → Edit route settings"
echo "  3. Enable / approve ${LAN_CIDR}"
echo "  4. From home (Tailscale on): open http://${AIFACE_IP}/"
echo
echo "Smoke from this Jetson:"
curl -sf --connect-timeout 2 -o /dev/null -w "  AiFace HTTP %{http_code}\n" "http://${AIFACE_IP}/" || echo "  AiFace HTTP FAIL"
echo 1 | sudo -S tailscale status | head -15
