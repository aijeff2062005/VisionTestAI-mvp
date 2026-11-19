#!/usr/bin/env bash
set -euo pipefail
: "${QY_SITE:?}" "${QY_BASE_URL:?}" "${FRAPPE_ADMIN_PASSWORD:?}" "${FRAPPE_DB_ROOT_PASSWORD:?}" "${MQTT_USERNAME:?}" "${MQTT_PASSWORD:?}" "${STATION_ID:?}"
[[ "$QY_SITE" =~ ^[a-zA-Z0-9][a-zA-Z0-9.-]+$ && "$QY_SITE" != frontend && "$QY_SITE" != *..* ]] || exit 2
# Refuse a volume containing another tenant, including an interrupted creation.
for config in sites/*/site_config.json; do
  [[ ! -f "$config" || "$config" == "sites/$QY_SITE/site_config.json" ]] || { echo 'Foreign site detected'; exit 2; }
done
if [[ ! -f "sites/$QY_SITE/site_config.json" ]]; then
  bench new-site "$QY_SITE" --mariadb-user-host-login-scope='%' \
    --admin-password "$FRAPPE_ADMIN_PASSWORD" --db-root-username root \
    --db-root-password "$FRAPPE_DB_ROOT_PASSWORD"
fi
apps="$(bench --site "$QY_SITE" execute frappe.get_installed_apps)"
[[ "$apps" != *tv_vision_hospital* ]] || exit 2
for app in erpnext healthcare solvronix_desk smart_hospital qy_vision_hospital; do
  if [[ "$apps" != *\"$app\"* && "$apps" != *\'$app\'* ]]; then
    bench --site "$QY_SITE" install-app "$app"
  fi
done
bench --site "$QY_SITE" set-config host_name "$QY_BASE_URL"
bench --site "$QY_SITE" set-config visiontestai_mqtt_host mqtt
bench --site "$QY_SITE" set-config --parse visiontestai_mqtt_port 1883
bench --site "$QY_SITE" set-config visiontestai_mqtt_user "$MQTT_USERNAME"
bench --site "$QY_SITE" set-config visiontestai_mqtt_password "$MQTT_PASSWORD"
bench --site "$QY_SITE" set-config visiontestai_station_id "$STATION_ID"
bench --site "$QY_SITE" set-config --parse developer_mode 0
bench --site "$QY_SITE" migrate
bench --site "$QY_SITE" enable-scheduler
bench --site "$QY_SITE" clear-cache
