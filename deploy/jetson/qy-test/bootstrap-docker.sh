#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
[[ $EUID == 0 && $(uname -m) == aarch64 ]] || { echo 'Requires root on ARM64'; exit 1; }
if command -v docker >/dev/null; then
  systemctl start docker
  docker info >/dev/null
  if docker compose version >/dev/null 2>&1; then exit 0; fi
  # Preserve an existing JetPack/NVIDIA Docker engine; install only the static CLI plugin.
  (cd docker-debs && sha256sum -c SHA256SUMS)
  stage=$(mktemp -d)
  trap 'rm -rf "$stage"' EXIT
  shopt -s nullglob
  packages=(docker-debs/docker-compose-plugin_*_arm64.deb)
  [[ ${#packages[@]} == 1 ]] || { echo 'Missing pinned ARM64 Compose plugin'; exit 1; }
  dpkg-deb -x "${packages[0]}" "$stage"
  plugin=$(find "$stage" -type f -name docker-compose -print -quit)
  [[ -n "$plugin" ]]
  install -Dm755 "$plugin" /usr/local/lib/docker/cli-plugins/docker-compose
  docker compose version
  exit 0
fi
source /etc/os-release
[[ "$ID" == ubuntu && "$VERSION_ID" == 22.04 ]] || { echo 'Offline packages target Ubuntu 22.04 ARM64 only'; exit 1; }
# Refuse replacement of an existing Docker installation or conflicting runtime.
if command -v docker >/dev/null || dpkg-query -W -f='${Status}' containerd 2>/dev/null | grep -q 'install ok installed'; then
  echo 'Existing Docker/containerd needs operator-managed setup; not replacing it.' >&2; exit 1
fi
[[ -d docker-debs ]] || { echo 'Offline Docker packages missing from bundle'; exit 1; }
(cd docker-debs && sha256sum -c SHA256SUMS)
# No network fallback: every required .deb must already be present.
apt-get --no-download --no-install-recommends -y install "$PWD"/docker-debs/*.deb
systemctl enable --now docker
systemctl is-active --quiet docker
docker compose version
