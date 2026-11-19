#!/usr/bin/env bash
# Enable clinic station on Jetson boot (systemd --user + linger).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
UNIT_SRC="$(dirname "$0")/clinic-station.service"
UNIT_DIR="${HOME}/.config/systemd/user"
UNIT_DST="${UNIT_DIR}/clinic-station.service"

mkdir -p "${UNIT_DIR}"
cp "${UNIT_SRC}" "${UNIT_DST}"
systemctl --user daemon-reload
systemctl --user enable clinic-station.service

if loginctl show-user "${USER}" -p Linger 2>/dev/null | grep -q "Linger=yes"; then
  echo "==> linger already enabled for ${USER}"
else
  if sudo -n loginctl enable-linger "${USER}" 2>/dev/null; then
    echo "==> linger enabled — clinic starts at boot without login"
  else
    echo "WARN: could not enable linger (need: sudo loginctl enable-linger ${USER})"
    echo "      without linger, the service starts only after this user logs in."
  fi
fi

systemctl --user restart clinic-station.service
sleep 2
systemctl --user --no-pager --full status clinic-station.service | head -25

# Boot without login: systemd --user needs linger (sudo). Fall back to cron @reboot.
AC_LOG="${ROOT}/services/assistant_controller/data/logs/station.boot.log"
mkdir -p "$(dirname "${AC_LOG}")"
CRON_LINE="@reboot sleep 20 && /bin/bash ${ROOT}/deploy/jetson/start_station.sh >> ${AC_LOG} 2>&1"
existing="$(crontab -l 2>/dev/null || true)"
if echo "${existing}" | grep -q "deploy/jetson/start_station.sh"; then
  echo "==> crontab @reboot already installed"
else
  printf "%s\n%s\n" "${existing}" "${CRON_LINE}" | grep -v '^$' | crontab -
  echo "==> crontab @reboot installed (starts clinic 20s after boot)"
fi

echo
echo "Chart: http://$(hostname -I 2>/dev/null | awk '{print $1}'):8088/"
echo "Logs:  journalctl --user -u clinic-station -f"
echo "Boot:  sudo loginctl enable-linger ${USER}   # optional; cron @reboot already covers power-on"

