#!/usr/bin/env bash
set -euo pipefail
# Generated self-extracting release: bash qy-jetson-install.run [--extract-only DIR]
payload=$(awk '/^__QY_PAYLOAD__$/ {print NR+1; exit}' "$0")
[[ -n "$payload" ]] || { echo 'Missing release payload'; exit 1; }
if [[ ${1:-} == --extract-only ]]; then
  destination="${2:?Extraction directory required}"
  mkdir -p "$destination"
  tail -n +"$payload" "$0" | tar -x --no-same-owner -C "$destination"
  (cd "$destination" && sha256sum -c SHA256SUMS)
  exit 0
fi
[[ $EUID == 0 ]] || { echo 'Run: sudo bash qy-jetson-install.run'; exit 1; }
[[ $(uname -m) == aarch64 ]] || { echo "Installation requires native ARM64; use --extract-only to inspect on this machine."; exit 1; }
export QY_BUNDLE_STARTED_AT=$(date +%s)
target="${QY_INSTALL_DIR:-/opt/visiontestai-qy}"
[[ "$target" == /* && "$target" != / ]] || exit 1
mkdir -p "$target"
stage=$(mktemp -d "$target/.bundle.XXXXXX")
trap 'rm -rf "$stage"' EXIT
tail -n +"$payload" "$0" | tar -x --no-same-owner -C "$stage"
(cd "$stage" && sha256sum -c SHA256SUMS)
# The configuration archive contains no .env or generated MQTT credentials.
tar -xzf "$stage/qy-jetson-config.tar.gz" --no-same-owner -C "$target"
mkdir -p "$target/out"
mv "$stage/qy-arm64-images.tar.gz" "$stage/qy-jetson-config.tar.gz" "$stage/SHA256SUMS" "$target/out/"
BUNDLE_DIR="$target/out" bash "$target/install.sh"
exit 0
__QY_PAYLOAD__
