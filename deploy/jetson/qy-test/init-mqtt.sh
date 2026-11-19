#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
set -a
source .env
set +a
: "${MQTT_USERNAME:?}" "${MQTT_PASSWORD:?}" "${STATION_ID:?}" "${MOSQUITTO_IMAGE:?}"
[[ "$MQTT_USERNAME" =~ ^[A-Za-z0-9_-]+$ && "$STATION_ID" =~ ^[A-Za-z0-9_-]+$ ]] || exit 2
# Feed the password through stdin, keeping it out of command arguments.
rm -f mosquitto/passwd mosquitto/acl
printf '%s\n' "$MQTT_PASSWORD" | docker run --rm --platform linux/arm64 -i --user "$(id -u):$(id -g)" \
  -e MQTT_USERNAME -v "$PWD/mosquitto:/config" --entrypoint sh "$MOSQUITTO_IMAGE" \
  -ec 'IFS= read -r password; mosquitto_passwd -b -c /config/passwd "$MQTT_USERNAME" "$password"'
printf 'user %s\ntopic readwrite qlbn/station/%s/session/+\n' "$MQTT_USERNAME" "$STATION_ID" > mosquitto/acl
docker run --rm --platform linux/arm64 --user 0 -v "$PWD/mosquitto:/config" \
  --entrypoint sh "$MOSQUITTO_IMAGE" -ec 'chown 1883:1883 /config/passwd /config/acl; chmod 600 /config/passwd /config/acl' 
