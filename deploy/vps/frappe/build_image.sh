#!/usr/bin/env bash
# Build visiontestai/frappe:clinic (erpnext + healthcare + smart_hospital).
# Safe: does not reboot, prune, or touch training workspaces.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
FRAPPE_DOCKER="${FRAPPE_DOCKER_DIR:-${SCRIPT_DIR}/.frappe_docker}"
APPS_JSON="${SCRIPT_DIR}/apps.json"
BASE_TAG="${BASE_TAG:-visiontestai/frappe:v16-hc}"
CLINIC_TAG="${CLINIC_TAG:-visiontestai/frappe:clinic}"
FRAPPE_BRANCH="${FRAPPE_BRANCH:-version-16}"

echo "==> ensure frappe_docker clone"
if [[ ! -d "${FRAPPE_DOCKER}/.git" ]]; then
  rm -rf "${FRAPPE_DOCKER}"
  git clone --depth 1 https://github.com/frappe/frappe_docker.git "${FRAPPE_DOCKER}"
fi

if [[ ! -f "${FRAPPE_DOCKER}/images/custom/Containerfile" ]]; then
  echo "ERROR: missing ${FRAPPE_DOCKER}/images/custom/Containerfile"
  exit 1
fi

echo "==> validate apps.json"
python3 -c "import json,sys; json.load(open('${APPS_JSON}')); print('ok')"

echo "==> build base image ${BASE_TAG} (frappe ${FRAPPE_BRANCH} + apps.json via BuildKit secret)"
export DOCKER_BUILDKIT=1
docker build \
  --build-arg="FRAPPE_PATH=https://github.com/frappe/frappe" \
  --build-arg="FRAPPE_BRANCH=${FRAPPE_BRANCH}" \
  --secret="id=apps_json,src=${APPS_JSON}" \
  --tag "${BASE_TAG}" \
  --file "${FRAPPE_DOCKER}/images/custom/Containerfile" \
  "${FRAPPE_DOCKER}"

echo "==> layer smart_hospital → ${CLINIC_TAG}"
CTX="$(mktemp -d)"
trap 'rm -rf "${CTX}"' EXIT
mkdir -p "${CTX}/services/hospital" "${CTX}/deploy/vps/frappe"
cp -a "${ROOT}/services/hospital/smart-hospital" "${CTX}/services/hospital/"
cp -a "${ROOT}/services/hospital/qy-vision-hospital" "${CTX}/services/hospital/"
cp -a "${ROOT}/services/hospital/tv-vision-hospital" "${CTX}/services/hospital/"
cp "${SCRIPT_DIR}/Dockerfile.smart" "${CTX}/deploy/vps/frappe/Dockerfile.smart"
cp "${SCRIPT_DIR}/provision_sites.sh" "${CTX}/deploy/vps/frappe/provision_sites.sh"
docker build \
  --build-arg="BASE_IMAGE=${BASE_TAG}" \
  --tag "${CLINIC_TAG}" \
  --file "${CTX}/deploy/vps/frappe/Dockerfile.smart" \
  "${CTX}"

echo "==> verify apps in image"
docker run --rm --entrypoint bash "${CLINIC_TAG}" -c \
  'ls apps; ./env/bin/python -c "import erpnext,healthcare,solvronix_desk,smart_hospital,qy_vision_hospital,tv_vision_hospital; print(\"imports_ok\")"'

echo "==> images ready"
docker images --format 'table {{.Repository}}:{{.Tag}}\t{{.Size}}\t{{.ID}}' | grep -E 'visiontestai/frappe|REPOSITORY' || true
