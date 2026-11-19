#!/usr/bin/env bash
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$DIR/../../.." && pwd)"
source "$DIR/versions.env"
# Image build needs no runtime passwords.
MARIADB_IMAGE="${MARIADB_IMAGE:-mariadb:10.6.25}"
REDIS_IMAGE="${REDIS_IMAGE:-redis:6.2.17-alpine}"
MOSQUITTO_IMAGE="${MOSQUITTO_IMAGE:-eclipse-mosquitto:2.0.22}"
if [[ -f "$DIR/.env" ]]; then source "$DIR/.env"; fi
command -v docker >/dev/null || { echo 'Cần cài Docker Engine và Buildx trên máy build.' >&2; exit 1; }
docker buildx version >/dev/null
docker info >/dev/null
# Release builds run on a native ARM64 host using the local Docker daemon.
[[ "$(uname -m)" == aarch64 && "$(docker info --format '{{.Architecture}}')" =~ ^(aarch64|arm64)$ ]] || { echo 'Release build requires native ARM64 host and Docker daemon; QEMU disabled.' >&2; exit 1; }
BUILDX_BUILDER="${BUILDX_BUILDER:-default}"
[[ "$BUILDX_BUILDER" == default ]] || { echo 'Use local default builder for native release builds.' >&2; exit 1; }
: "${FRAPPE_REF:?Set immutable Frappe v16 release tag}" "${ERPNEXT_REF:?Set immutable ERPNext v16 release tag}" "${HEALTHCARE_REF:?Set immutable Healthcare v16 release tag}" "${DESK_REF:?Set Solvronix Desk release tag}"
IMAGE="${CUSTOM_IMAGE:-visiontestai/frappe:qy-arm64-native1}"
[[ "$IMAGE" == *:* && "$IMAGE" != *:latest ]] || exit 2
mkdir -p "$DIR/out"
CTX="$(mktemp -d)"
trap 'rm -rf "$CTX"' EXIT
# Freeze the upstream container recipe to a recorded commit.
git clone https://github.com/frappe/frappe_docker.git "$CTX/upstream"
if [[ -n "${FRAPPE_DOCKER_COMMIT:-}" ]]; then git -C "$CTX/upstream" checkout --detach "$FRAPPE_DOCKER_COMMIT"; fi
git -C "$CTX/upstream" rev-parse HEAD > "$DIR/out/frappe-docker.commit"
export FRAPPE_REF ERPNEXT_REF HEALTHCARE_REF DESK_REF
python3 - "$CTX/upstream/apps.lock.json" "$DIR/out/source-lock.json" "$DIR/sources.lock.json" <<'PY'
import json, os, subprocess, sys
specs = [('frappe','https://github.com/frappe/frappe','FRAPPE_REF'), ('erpnext','https://github.com/frappe/erpnext','ERPNEXT_REF'), ('healthcare','https://github.com/frappe/healthcare','HEALTHCARE_REF'), ('solvronix_desk','https://github.com/Solvronix/Solvronix-Desk.git','DESK_REF')]
apps, locks = [], {}
expected = json.load(open(sys.argv[3]))
for name,url,key in specs:
    ref=os.environ[key]
    out=subprocess.check_output(['git','ls-remote','--tags',url,'refs/tags/'+ref,'refs/tags/'+ref+'^{}'],text=True).splitlines()
    if not out: raise SystemExit(f'{name}: immutable release tag required: {ref}')
    commit = out[-1].split()[0]
    pinned = expected.get(name, {})
    if pinned.get('tag') == ref and pinned.get('commit') != commit:
        raise SystemExit(f'{name}: upstream tag moved; refusing build')
    locks[name]={'url':url,'tag':ref,'commit':commit}
    if name != 'frappe': apps.append({'url':url,'branch':ref})
json.dump(apps,open(sys.argv[1],'w'),indent=2)
json.dump(locks,open(sys.argv[2],'w'),indent=2)
PY
mkdir -p "$CTX/upstream/services/hospital" "$CTX/upstream/deploy/jetson/qy-test"
for app in smart-hospital qy-vision-hospital; do
  mkdir -p "$CTX/upstream/services/hospital/$app"
  tar -C "$ROOT/services/hospital/$app" --exclude=.git --exclude=__pycache__ --exclude=.venv --exclude=node_modules --exclude=.env -cf - . | tar -C "$CTX/upstream/services/hospital/$app" -xf -
done
cp "$DIR/provision.sh" "$DIR/healthcheck.py" "$CTX/upstream/deploy/jetson/qy-test/"
mkdir -p "$CTX/upstream/qy-build-tools"
cp "$DIR/patch_portal.py" "$DIR/verify_sources.py" "$CTX/upstream/qy-build-tools/"
cp "$DIR/out/source-lock.json" "$CTX/upstream/qy-build-tools/source-lock.json"
# A single build graph lets BuildKit share the ARM64 base without a registry.
cp "$CTX/upstream/images/custom/Containerfile" "$CTX/upstream/Containerfile.qy"
mkdir -p "$CTX/upstream/dependency-cache"
if [[ -n "${QY_DEPENDENCY_CACHE_DIR:-}" && -d "$QY_DEPENDENCY_CACHE_DIR/uv" ]]; then
  cp -a "$QY_DEPENDENCY_CACHE_DIR/uv" "$CTX/upstream/dependency-cache/uv"
fi
chmod -R a+rX "$CTX/upstream/dependency-cache"
python3 "$DIR/prepare_recipe.py" "$CTX/upstream/Containerfile.qy"
sed '1,2d' "$DIR/Dockerfile" >> "$CTX/upstream/Containerfile.qy"
APPS_HASH="$(sha256sum "$CTX/upstream/apps.lock.json")"
APPS_HASH="${APPS_HASH%% *}"
docker buildx build --builder "${BUILDX_BUILDER:-default}" --progress plain --platform linux/arm64 --load \
  --build-arg "FRAPPE_BRANCH=$FRAPPE_REF" \
  --build-arg "PYTHON_VERSION=3.14.10" --build-arg "NODE_VERSION=24.22.3" --build-arg "DEBIAN_BASE=trixie" \
  --build-arg "CACHE_BUST=$APPS_HASH" \
  --secret "id=apps_json,src=$CTX/upstream/apps.lock.json" \
  --metadata-file "$DIR/out/build-metadata.json" \
  --tag "$IMAGE" -f "$CTX/upstream/Containerfile.qy" "$CTX/upstream"
[[ "$(docker image inspect --format '{{.Architecture}}' "$IMAGE")" == arm64 ]]
docker image inspect "$IMAGE" > "$DIR/out/image-inspect.json"
docker run --rm --entrypoint sh "$IMAGE" -c 'dpkg-query -W' > "$DIR/out/system-packages.lock"
docker run --rm --entrypoint ./env/bin/python "$IMAGE" -m pip check > "$DIR/out/dependency-verification.txt"
docker run --rm --platform linux/arm64 --entrypoint bash "$IMAGE" -ec \
  './env/bin/python -c "import erpnext,healthcare,solvronix_desk,smart_hospital,qy_vision_hospital,paho.mqtt.publish"; bench version' > "$DIR/out/versions.txt"
docker run --rm -i --entrypoint ./env/bin/python "$IMAGE" < "$DIR/verify_image.py" > "$DIR/out/image-verification.json"
date -u +%FT%TZ > "$DIR/out/build-date.txt"
git -C "$ROOT" rev-parse HEAD > "$DIR/out/local-repo.commit"
git -C "$ROOT" diff -- services/hospital/smart-hospital services/hospital/qy-vision-hospital > "$DIR/out/local-apps.patch"
tar -C "$CTX/upstream" -czf "$DIR/out/local-apps.tar.gz" services/hospital deploy/jetson/qy-test/provision.sh
# Include infrastructure images so Jetson can load the complete stack offline.
for image in "$MARIADB_IMAGE" "$REDIS_IMAGE" "$MOSQUITTO_IMAGE"; do docker pull --platform linux/arm64 "$image"; done
# Only ephemeral GitHub runners: reclaim obsolete build layers, never operator data.
if [[ "${GITHUB_ACTIONS:-}" == true ]]; then docker builder prune -af; fi
docker save "$IMAGE" "$MARIADB_IMAGE" "$REDIS_IMAGE" "$MOSQUITTO_IMAGE" | gzip > "$DIR/out/qy-arm64-images.tar.gz"
python3 "$DIR/verify_archive.py" "$DIR/out/qy-arm64-images.tar.gz" > "$DIR/out/archive-verification.json"
(cd "$DIR/out" && sha256sum qy-arm64-images.tar.gz > SHA256SUMS)
echo "Ready: $DIR/out/qy-arm64-images.tar.gz"
