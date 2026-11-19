#!/usr/bin/env bash
# Run patient media gateway on Mac (HTTP :9010 + MQTT announce).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q -r requirements.txt
export MEDIA_ROOT="${MEDIA_ROOT:-$ROOT/data}"
export MEDIA_PUBLIC_BASE="${MEDIA_PUBLIC_BASE:-http://192.168.1.78:9010}"
export MQTT_HOST="${MQTT_HOST:-127.0.0.1}"
export MQTT_PORT="${MQTT_PORT:-1883}"
export MEDIA_TOKEN="${MEDIA_TOKEN:-dev-media-token}"
mkdir -p "$MEDIA_ROOT"
exec uvicorn app.main:app --host "${MEDIA_HOST:-0.0.0.0}" --port "${MEDIA_PORT:-9010}"
