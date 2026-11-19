#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
[[ $(uname -m) == aarch64 ]] || exit 1
mkdir -p out/docker-debs
# Resolve a complete dependency closure against Jammy, not the CI host's Noble.
docker run --rm --platform linux/arm64 -v "$PWD/out/docker-debs:/output" ubuntu:22.04 bash -euc '
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends ca-certificates curl gnupg
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
printf "%s\n" "deb [arch=arm64 signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu jammy stable" > /etc/apt/sources.list.d/docker.list
apt-get update
apt-get -o Dir::State::status=/dev/null -o Dir::Cache::archives=/output --download-only --no-install-recommends -y install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin curl python3 ca-certificates iproute2
cd /output
for package in *.deb; do dpkg-deb --show "$package"; done > PACKAGES.lock
sha256sum ./*.deb > SHA256SUMS
chmod -R a+rX /output
'
