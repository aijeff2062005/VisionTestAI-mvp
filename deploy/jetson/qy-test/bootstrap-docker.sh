#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
[[ $EUID == 0 && $(uname -m) == aarch64 ]] || { echo 'Requires root on ARM64'; exit 1; }
if docker info >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then exit 0; fi
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
