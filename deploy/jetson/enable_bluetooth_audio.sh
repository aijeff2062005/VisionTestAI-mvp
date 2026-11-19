#!/usr/bin/env bash
# Enable Bluetooth A2DP/AVRCP audio on NVIDIA Jetson (disabled by default).
# Official docs:
#   https://docs.nvidia.com/jetson/archives/r36.5.2/DeveloperGuide/SD/Communications/EnablingBluetoothAudio.html
# Forum (Orin Nano speaker, same fix):
#   https://forums.developer.nvidia.com/t/jetson-orin-nano-bluetooth-speaker-connectivity-issue-solved/328260
#
# NVIDIA ships bluetoothd with --noplugin=audio,a2dp,avrcp. This drop-in in /etc
# overrides that without editing the nvidia-l4t-firmware file (survives apt upgrades).
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Need root. Re-run with sudo, or: docker run --rm --privileged --pid=host alpine nsenter -t 1 -m -u -n -i bash $0"
  exit 1
fi

CLINIC_USER="${SUDO_USER:-ivision}"
OVERRIDE_DIR="/etc/systemd/system/bluetooth.service.d"
# Must sort AFTER nv-bluetooth-service.conf or NVIDIA's --noplugin wins.
OVERRIDE_FILE="${OVERRIDE_DIR}/zz-enable-audio.conf"

echo "==> writing ${OVERRIDE_FILE}"
mkdir -p "${OVERRIDE_DIR}"
rm -f "${OVERRIDE_DIR}/enable-audio.conf"
cat > "${OVERRIDE_FILE}" <<'EOF'
[Service]
# Clear NVIDIA --noplugin=audio,a2dp,avrcp then start a full bluetoothd.
ExecStart=
ExecStart=/usr/lib/bluetooth/bluetoothd -d
EOF

echo "==> patch NVIDIA drop-in (official Jetson Linux steps)"
for f in /lib/systemd/system/bluetooth.service.d/nv-bluetooth-service.conf \
         /usr/lib/systemd/system/bluetooth.service.d/nv-bluetooth-service.conf; do
  if [[ -f "${f}" ]]; then
    sed -i 's#ExecStart=/usr/lib/bluetooth/bluetoothd -d --noplugin=audio,a2dp,avrcp#ExecStart=/usr/lib/bluetooth/bluetoothd -d#' "${f}"
    echo "    patched ${f}"
  fi
done

echo "==> unblock bluetooth radio"
rfkill unblock bluetooth || true

echo "==> add ${CLINIC_USER} to bluetooth group"
if id "${CLINIC_USER}" >/dev/null 2>&1; then
  usermod -aG bluetooth "${CLINIC_USER}"
fi

echo "==> install pulseaudio-module-bluetooth"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y pulseaudio-module-bluetooth

echo "==> reload bluetooth.service"
systemctl daemon-reload
systemctl enable bluetooth
systemctl restart bluetooth
sleep 2

echo "==> power on adapter"
hciconfig hci0 up || true
rfkill unblock bluetooth || true

echo
echo "==== verify ===="
systemctl is-active bluetooth
tr '\0' ' ' < /proc/"$(pidof bluetoothd | awk '{print $1}')"/cmdline; echo
rfkill list bluetooth || true
hciconfig -a | head -20
echo
echo "Next (as ${CLINIC_USER}):"
echo "  pulseaudio -k; pulseaudio --start"
echo "  bluetoothctl power on"
echo "  bluetoothctl scan on"
echo "  bluetoothctl pair <MAC>; bluetoothctl trust <MAC>; bluetoothctl connect <MAC>"
echo "  pactl list short sinks   # look for bluez_sink.*"
