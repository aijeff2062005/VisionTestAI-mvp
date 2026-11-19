#!/usr/bin/env bash
# Start Jetson clinic stack without Docker (preferred if camera/GUI is flaky).
# Requires: python3 venv with AC deps; AiFace panel Server IP = this Jetson.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
AC="${ROOT}/services/assistant_controller"
BS="${ROOT}/services/hospital/hospital_api"
ENV_FILE="${ROOT}/deploy/env/lab.env"
if [[ ! -f "${ENV_FILE}" ]]; then
  ENV_FILE="${ROOT}/deploy/env/lab.env.example"
fi
# shellcheck disable=SC1090
set -a; source "${ENV_FILE}"; set +a

# Prefer Tailscale VPS (VPS_TAILNET_HOST / VPS_HOST). Fall back to Mac LAN bridge only
# when VPS_HOST is empty or the old unreachable public IP.
if [[ -n "${VPS_TAILNET_HOST:-}" ]]; then
  VPS_HOST="${VPS_TAILNET_HOST}"
elif [[ -z "${VPS_HOST:-}" || "${VPS_HOST}" == "103.249.117.203" ]]; then
  VPS_HOST="${MAC_LAN_IP:-192.168.1.78}"
fi
export VPS_HOST
export MQTT_HOST="${MQTT_HOST:-${VPS_HOST}}"
export MQTT_PORT="${MQTT_PORT:-1883}"
export MQTT_USER="${MQTT_USERNAME:-vision}"
export MQTT_PASS="${MQTT_PASSWORD:-mqtt-dev-pass}"
# Preserve lab.env overrides (Funnel HTTPS hospital URL, etc.)
export HOSPITAL_BASE_URL="${HOSPITAL_BASE_URL:-https://${TRUNG_VUONG_SITE_HOST:-trungvuong.vision.primetek.ai}}"
export MEDIA_BASE_URL="${MEDIA_BASE_URL:-http://${VPS_HOST}:9010}"
export FACE_HOST="${AIFACE_PANEL_IP:-192.168.1.18}"
export FACE_PORT="${AIFACE_PANEL_PORT:-80}"
export FACE_VECTORDB_BASE_URL="${FACE_VECTORDB_BASE_URL:-http://${VPS_HOST}:8100}"
export FACE_VECTORDB_API_KEY="${FACE_VDB_API_KEY:-dev-face-vdb-key}"
# Local USB headset (Yealink) is the clinic mic. Do not pull Mac :8092.
unset SLOAN_AUDIO_URL || true

# Prefer a USB headset/dongle mic over Logitech C270 webcam mic for chart STT.
# Override with USB_MIC_SOURCE / WEBCAM_MIC_SOURCE if names change.
if command -v pactl >/dev/null 2>&1; then
  export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
  WEBCAM_MIC_SOURCE="${WEBCAM_MIC_SOURCE:-alsa_input.usb-046d_C270_HD_WEBCAM_55423390-02.mono-fallback}"
  SOURCES="$(pactl list short sources 2>/dev/null || true)"
  pick_usb_mic() {
    if [[ -n "${USB_MIC_SOURCE:-}" ]] && echo "${SOURCES}" | grep -qF "${USB_MIC_SOURCE}"; then
      echo "${USB_MIC_SOURCE}"
      return
    fi
    local cand
    for cand in \
      alsa_input.usb-Yealink_Yealink_BT51_3HB1001304-00.mono-fallback \
      alsa_input.usb-C-Media_Electronics_Inc._USB_Microphone-00.mono-fallback
    do
      if echo "${SOURCES}" | grep -qF "${cand}"; then
        echo "${cand}"
        return
      fi
    done
    echo "${SOURCES}" | awk '/alsa_input\.usb-/ && $2 !~ /C270|WEBCAM|046d_C270/ {print $2; exit}'
  }
  USB_MIC_SOURCE="$(pick_usb_mic || true)"
  if [[ -n "${USB_MIC_SOURCE}" ]]; then
    pactl set-card-profile alsa_card.usb-Yealink_Yealink_BT51_3HB1001304-00 \
      output:analog-stereo+input:mono-fallback 2>/dev/null || true
    YEALINK_SINK="${YEALINK_SINK:-alsa_output.usb-Yealink_Yealink_BT51_3HB1001304-00.analog-stereo}"
    pactl set-default-source "${USB_MIC_SOURCE}" 2>/dev/null || true
    pactl set-source-mute "${USB_MIC_SOURCE}" 0 2>/dev/null || true
    pactl set-source-volume "${USB_MIC_SOURCE}" 100% 2>/dev/null || true
    pactl set-source-mute "${WEBCAM_MIC_SOURCE}" 1 2>/dev/null || true
    pactl set-default-sink "${YEALINK_SINK}" 2>/dev/null || true
    pactl set-sink-mute "${YEALINK_SINK}" 0 2>/dev/null || true
    pactl set-sink-volume "${YEALINK_SINK}" 100% 2>/dev/null || true
    export PULSE_SINK="${YEALINK_SINK}"
    export PULSE_SOURCE="${USB_MIC_SOURCE}"
    # HDMI/APE "new device" must not steal the clinic headset after Pulse restarts.
    pactl unload-module module-switch-on-connect 2>/dev/null || true
    PULSE_CFG="${HOME}/.config/pulse"
    if [[ -d "${PULSE_CFG}" ]]; then
      shopt -s nullglob
      for f in "${PULSE_CFG}"/*-default-source; do printf '%s' "${USB_MIC_SOURCE}" > "${f}"; done
      for f in "${PULSE_CFG}"/*-default-sink; do printf '%s' "${YEALINK_SINK}" > "${f}"; done
      shopt -u nullglob
    fi
    echo "==> Yealink mic+speaker connected: source=${USB_MIC_SOURCE} sink=${YEALINK_SINK} volume=100%"
  else
    echo "==> USB mic source not found yet — check: pactl list short sources"
  fi
fi

echo "==> endpoints via VPS_HOST=${VPS_HOST} MQTT=${MQTT_HOST}:${MQTT_PORT} hospital=${HOSPITAL_BASE_URL}"

PY="${AC}/.venv/bin/python"
if [[ ! -x "${PY}" ]]; then
  echo "ERROR: missing ${AC}/.venv — create once:"
  echo "  python3 -m venv ${AC}/.venv"
  echo "  ${AC}/.venv/bin/pip install -r ${AC}/requirements.txt"
  exit 1
fi

port_in_use() {
  local p="$1"
  ss -lnt "sport = :${p}" 2>/dev/null | grep -q ":${p}" \
    || (command -v lsof >/dev/null && lsof -iTCP:"${p}" -sTCP:LISTEN >/dev/null 2>&1)
}

BS_PID=""
if port_in_use 7788; then
  echo "==> :7788 already in use — reusing existing AiFace BS (e.g. systemctl --user status aiface-bs)"
else
  echo "==> starting aiface_bs on :7788 / :7790"
  "${PY}" "${BS}/aiface_bs.py" &
  BS_PID=$!
  trap '[[ -n "${BS_PID}" ]] && kill "${BS_PID}" 2>/dev/null || true' EXIT
fi

if port_in_use 8088; then
  if [[ "${REPLACE_AC:-0}" == "1" ]]; then
    echo "==> REPLACE_AC=1 — stopping existing AC on :8088"
    pkill -f "ac.main --config" 2>/dev/null || true
    sleep 2
    if port_in_use 8088; then
      pkill -9 -f "ac.main --config" 2>/dev/null || true
      sleep 1
    fi
    if port_in_use 8088; then
      echo "ERROR: :8088 still busy after REPLACE_AC. Find PID: ss -lntp | grep 8088"
      exit 1
    fi
  else
    echo "ERROR: chart :8088 already in use — AC is already running."
    echo "  Open:  http://$(hostname -I 2>/dev/null | awk '{print $1}'):8088/"
    echo "  Or stop it:  pkill -f 'ac.main --config'"
    echo "  Or replace:  REPLACE_AC=1 ./start_station.sh"
    exit 1
  fi
fi

echo "==> starting assistant_controller (clinic chart :8088)"
cd "${AC}"
export PYTHONPATH="${AC}/src${PYTHONPATH:+:$PYTHONPATH}"
CFG="${AC_CONFIG:-${AC}/configs/clinic.yaml}"
if [[ ! -f "${CFG}" ]]; then
  CFG="${AC}/configs/default.yaml"
fi
exec "${PY}" -m ac.main --config "${CFG}" --mqtt-optional "$@"
