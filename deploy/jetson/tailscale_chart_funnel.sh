#!/usr/bin/env bash
# Public HTTPS Funnel for Jetson VA chart (:8088).
#
#   bash mvp_platform/deploy/jetson/tailscale_chart_funnel.sh
#
# Home / off-LAN:  https://jetson-clinic.tail82bd22.ts.net/
# Tailnet HTTP:    http://jetson-clinic.tail82bd22.ts.net:8088/
#                  http://100.97.186.106:8088/
#
set -euo pipefail

if ! command -v tailscale >/dev/null 2>&1; then
  echo "ERROR: tailscale not installed"
  exit 1
fi

if ! curl -sf --connect-timeout 2 -o /dev/null "http://127.0.0.1:8088/"; then
  echo "ERROR: chart not listening on 127.0.0.1:8088 — start clinic-station first"
  exit 1
fi

echo "==> Funnel https://jetson-clinic… → http://127.0.0.1:8088"
if ! tailscale funnel --bg --https=443 "http://127.0.0.1:8088" 2>/dev/null; then
  echo 1 | sudo -S tailscale funnel --bg --https=443 "http://127.0.0.1:8088"
fi

echo
tailscale funnel status
echo
echo "Chart (Funnel HTTPS): https://jetson-clinic.tail82bd22.ts.net/"
