#!/usr/bin/env bash
# Run webcam demo inside the smarteyes conda env.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

if ! command -v conda >/dev/null 2>&1; then
  echo "conda not found. Install Miniconda, then: conda env create -f environment.yml"
  exit 1
fi

# shellcheck disable=SC1091
source "$(conda info --base)/etc/profile.d/conda.sh"

if ! conda env list | grep -qE '^smarteyes\s'; then
  echo "Creating conda env smarteyes..."
  conda env create -f environment.yml -y
fi

conda activate smarteyes
exec python scripts/run_webcam_demo.py "$@"
