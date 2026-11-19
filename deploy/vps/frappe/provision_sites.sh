#!/usr/bin/env bash
# Provision both hospital tenants in one Frappe bench. Keep the legacy
# `frontend` site/database as Trưng Vương and expose it through its hostname.
set -euo pipefail

TV_HOST="${TRUNG_VUONG_SITE_HOST:-trungvuong.vision.primetek.ai}"
QY_HOST="${QUAN_Y_SITE_HOST:-qdymd.vision.primetek.ai}"
FRAPPE_ADMIN_PASSWORD="${FRAPPE_ADMIN_PASSWORD:-admin}"
FRAPPE_DB_ROOT_PASSWORD="${FRAPPE_DB_ROOT_PASSWORD:-admin}"

valid_host() {
  [[ "$1" =~ ^[A-Za-z0-9.-]+$ && "$1" != .* && "$1" != *..* && "$1" != *. ]]
}

if ! valid_host "$TV_HOST" || ! valid_host "$QY_HOST"; then
  echo "Hospital site hosts must be DNS hostnames (no scheme, path, or port)." >&2
  exit 2
fi
if [[ "$TV_HOST" == "$QY_HOST" ]]; then
  echo "Trung Vuong and Quan Y must use different hostnames." >&2
  exit 2
fi

for i in $(seq 1 60); do
  if grep -q db_host sites/common_site_config.json 2>/dev/null; then break; fi
  echo "waiting for common_site_config…"
  sleep 3
done
if ! grep -q db_host sites/common_site_config.json 2>/dev/null; then
  echo "Frappe common site config was not initialized." >&2
  exit 2
fi

new_site() {
  local site="$1" app="$2"
  bench new-site "$site" \
    --mariadb-user-host-login-scope='%' \
    --admin-password="$FRAPPE_ADMIN_PASSWORD" \
    --db-root-username=root \
    --db-root-password="$FRAPPE_DB_ROOT_PASSWORD" \
    --install-app erpnext \
    --install-app healthcare \
    --install-app solvronix_desk \
    --install-app smart_hospital \
    --install-app "$app"
}

installed_apps() {
  bench --site "$1" execute frappe.get_installed_apps
}

has_app() {
  local apps="$1" app="$2"
  [[ "$apps" == *"\"$app\""* || "$apps" == *"'$app'"* ]]
}

ensure_apps() {
  local site="$1" expected="$2" other="$3" apps
  apps="$(installed_apps "$site")"
  if has_app "$apps" frappe_theme; then
    bench --site "$site" remove-from-installed-apps frappe_theme
    apps="$(installed_apps "$site")"
  fi
  if has_app "$apps" "$other"; then
    echo "Site $site has the other hospital workflow ($other); refusing to mix workflows." >&2
    exit 3
  fi
  if has_app "$apps" quan_y_demo || has_app "$apps" trung_vuong_visioncare; then
    echo "Site $site still has a legacy hospital app ID; migrate the installed app before provisioning renamed app IDs." >&2
    exit 3
  fi
  if ! has_app "$apps" solvronix_desk; then bench --site "$site" install-app solvronix_desk; fi
  if ! has_app "$apps" smart_hospital; then bench --site "$site" install-app smart_hospital; fi
  if ! has_app "$apps" "$expected"; then bench --site "$site" install-app "$expected"; fi
}

if [[ ! -d sites/frontend ]]; then
  new_site frontend tv_vision_hospital
fi
ensure_apps frontend tv_vision_hospital qy_vision_hospital

if [[ "$TV_HOST" != frontend ]]; then
  if [[ -e "sites/$TV_HOST" && ! -L "sites/$TV_HOST" ]]; then
    echo "Cannot create hostname alias: sites/$TV_HOST already exists and is not a symlink." >&2
    exit 4
  fi
  if [[ -L "sites/$TV_HOST" ]] && [[ "$(readlink "sites/$TV_HOST")" != frontend ]]; then
    echo "Hostname alias sites/$TV_HOST already points elsewhere." >&2
    exit 4
  fi
  ln -sfn frontend "sites/$TV_HOST"
fi

if [[ ! -d "sites/$QY_HOST" ]]; then
  new_site "$QY_HOST" qy_vision_hospital
fi
ensure_apps "$QY_HOST" qy_vision_hospital tv_vision_hospital

configure_site() {
  local site="$1" host="$2" station_id="$3"
  bench --site "$site" set-config --parse developer_mode 0
  bench --site "$site" migrate
  bench --site "$site" set-config --parse developer_mode 0
  bench --site "$site" set-config host_name "https://$host"
  bench --site "$site" set-config visiontestai_mqtt_host mqtt
  bench --site "$site" set-config visiontestai_mqtt_port 1883
  bench --site "$site" set-config visiontestai_mqtt_user "${MQTT_USERNAME:-vision}"
  bench --site "$site" set-config visiontestai_mqtt_password "${MQTT_PASSWORD:-mqtt-dev-pass}"
  bench --site "$site" set-config visiontestai_station_id "$station_id"
  bench --site "$site" set-config visiontestai_qr_decode_url http://qr_decode:9020
  bench --site "$site" set-config visiontestai_media_base http://media:9010
  bench --site "$site" set-config visiontestai_media_token "${MEDIA_TOKEN:-dev-media-token}"
  if [[ -n "${AIFACE_STATION_URL:-}" ]]; then
    bench --site "$site" set-config visiontestai_aiface_station_url "$AIFACE_STATION_URL"
  fi
  bench --site "$site" clear-cache
}

configure_site frontend "$TV_HOST" "${TRUNG_VUONG_STATION_ID:-${STATION_ID:-station-01}}"
configure_site "$QY_HOST" "$QY_HOST" "${QUAN_Y_STATION_ID:-${STATION_ID:-station-01}}"
bench set-config -g default_site frontend
echo "Provisioned Trưng Vương (frontend → $TV_HOST) and Quân y ($QY_HOST)."
