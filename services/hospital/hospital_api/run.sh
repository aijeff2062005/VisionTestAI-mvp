#!/usr/bin/env bash
# Run lean hospital API on Mac (MVP without full Frappe).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q -r requirements.txt
exec uvicorn main:app --host 0.0.0.0 --port 8000
