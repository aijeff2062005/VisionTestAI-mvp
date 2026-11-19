#!/usr/bin/env bash
# Bridge Frappe Docker → Jetson AC when VPS Tailscale is userspace-only.
#   ./start_jetson_proxy.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
PY="${ROOT}/jetson_socks_proxy.py"
LOG="/tmp/visiontestai-jetson-proxy.log"
PORT="${LISTEN_PORT:-18088}"

pkill -f "jetson_socks_proxy.py" 2>/dev/null || true
sleep 0.3
nohup python3 "${PY}" >>"${LOG}" 2>&1 &
echo $! > /tmp/visiontestai-jetson-proxy.pid
sleep 0.4
echo "==> proxy pid=$(cat /tmp/visiontestai-jetson-proxy.pid)  listen=:${PORT}"
curl -sf --connect-timeout 4 "http://127.0.0.1:${PORT}/api/face/health" && echo && echo "==> jetson AC via proxy OK"
