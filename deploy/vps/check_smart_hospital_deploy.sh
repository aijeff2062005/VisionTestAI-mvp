#!/usr/bin/env bash
# Verify smart_hospital files Desk/UI depend on exist locally and/or on the VPS.
#
#   ./check_smart_hospital_deploy.sh              # local repo only
#   ./check_smart_hospital_deploy.sh --remote     # SSH + docker exec on Coder VPS
#   ./check_smart_hospital_deploy.sh --both       # local then remote
#
# Required paths are derived from hooks.py (app_include_js, boot_session,
# after_migrate, scheduler, overrides) plus clinic Python imports and page JS.
# Exits non-zero if anything is missing.
set -euo pipefail

# Script lives in mvp_platform/deploy/vps/ → app is under mvp_platform/services/...
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
APP_LOCAL="${ROOT}/services/hospital/smart-hospital/smart_hospital"
SSH_HOST="${VPS_SSH:-main.aquamarine-leopon-37.vupham.coder}"
WORKER="${FRAPPE_WORKER:-visiontestai-frappe-queue-short}"
FRONTEND="${FRAPPE_FRONTEND:-visiontestai-frappe-frontend}"
BENCH_APP="/home/frappe/frappe-bench/apps/smart_hospital/smart_hospital"
FRONTEND_ASSETS="/home/frappe/frappe-bench/sites/assets/smart_hospital"

MODE="local"
case "${1:-}" in
  --remote|remote) MODE="remote" ;;
  --both|both) MODE="both" ;;
  --local|local|"") MODE="local" ;;
  -h|--help)
    sed -n '2,12p' "$0"
    exit 0
    ;;
  *)
    echo "Unknown argument: $1" >&2
    exit 2
    ;;
esac

# App-relative paths that must exist for Desk boot + clinic UI.
# Keep in sync with hooks.py and clinic_* imports.
REQUIRED_PY=(
  hooks.py
  api/__init__.py
  api/clinic_shell.py
  api/clinic_constants.py
  api/clinic_workspaces.py
  api/clinic_desk.py
  api/clinic_roles.py
  api/patient_wipe.py
  api/face_identity.py
  api/face_service_api.py
  api/createpatient.py
  api/patient.py
  api/vision.py
  api/receive_visual_acuity.py
  api/send_vision_measurement.py
  overrides/__init__.py
  overrides/patient.py
  overrides/sales_oder.py
)

REQUIRED_APP_JS=(
  public/js/clinic_shell.js
  public/js/patient_list.js
  public/js/face_landmarker.js
  public/js/face_enroll.js
  public/js/patient_cccd.js
  smart_hospital/page/patient_registration/patient_registration.js
  smart_hospital/page/nurse_station/nurse_station.js
  smart_hospital/page/doctor_review/doctor_review.js
  smart_hospital/page/patient_vision_booking/patient_vision_booking.js
  smart_hospital/page/face_service_test/face_service_test.js
)

# hooks.py app_include_js → frontend nginx assets (basename under js/).
REQUIRED_FRONTEND_JS=(
  js/clinic_shell.js
  js/patient_list.js
  js/face_landmarker.js
  js/face_enroll.js
  js/patient_cccd.js
)

missing=0
checked=0

ok() { printf "  OK   %s\n" "$1"; }
fail() { printf "  MISS %s\n" "$1"; missing=$((missing + 1)); }

check_local() {
  echo "==> local ${APP_LOCAL}"
  if [[ ! -d "${APP_LOCAL}" ]]; then
    echo "ERROR: missing app tree ${APP_LOCAL}" >&2
    exit 1
  fi
  local rel
  for rel in "${REQUIRED_PY[@]}" "${REQUIRED_APP_JS[@]}"; do
    checked=$((checked + 1))
    if [[ -f "${APP_LOCAL}/${rel}" ]]; then
      ok "${rel}"
    else
      fail "${rel}"
    fi
  done
}

check_remote() {
  echo "==> remote ${SSH_HOST} worker=${WORKER} app=${BENCH_APP}"
  local worker_list frontend_list report
  worker_list="$(printf '%s\n' "${REQUIRED_PY[@]}" "${REQUIRED_APP_JS[@]}")"
  frontend_list="$(printf '%s\n' "${REQUIRED_FRONTEND_JS[@]}")"
  report="$(
    ssh -o ConnectTimeout=15 -o BatchMode=yes "${SSH_HOST}" \
      "WORKER='${WORKER}' FRONTEND='${FRONTEND}' BENCH_APP='${BENCH_APP}' FRONTEND_ASSETS='${FRONTEND_ASSETS}' bash -s" <<EOS
set -euo pipefail
WORKER_FILES=\$(cat <<'LIST'
${worker_list}
LIST
)
FRONTEND_FILES=\$(cat <<'LIST'
${frontend_list}
LIST
)
while IFS= read -r line; do
  [[ -z "\${line}" ]] && continue
  if docker exec "\${WORKER}" test -f "\${BENCH_APP}/\${line}"; then
    printf "OK\t%s:%s\n" "\${WORKER}" "\${line}"
  else
    printf "MISS\t%s:%s\n" "\${WORKER}" "\${line}"
  fi
done <<< "\${WORKER_FILES}"
while IFS= read -r line; do
  [[ -z "\${line}" ]] && continue
  if docker exec "\${FRONTEND}" test -f "\${FRONTEND_ASSETS}/\${line}"; then
    printf "OK\t%s:%s\n" "\${FRONTEND}" "\${line}"
  else
    printf "MISS\t%s:%s\n" "\${FRONTEND}" "\${line}"
  fi
done <<< "\${FRONTEND_FILES}"
EOS
  )"

  local status path
  while IFS=$'\t' read -r status path; do
    [[ -z "${status}" ]] && continue
    checked=$((checked + 1))
    if [[ "${status}" == "OK" ]]; then
      ok "${path}"
    else
      fail "${path}"
    fi
  done <<< "${report}"
}

case "${MODE}" in
  local) check_local ;;
  remote) check_remote ;;
  both) check_local; check_remote ;;
esac

echo "==> checked ${checked}, missing ${missing}"
if [[ "${missing}" -gt 0 ]]; then
  echo "FAIL: ${missing} required file(s) missing" >&2
  exit 1
fi
echo "PASS"
exit 0
