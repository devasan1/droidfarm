#!/usr/bin/env bash
# DroidFarm — Mac launcher.
#
# Double-click this file in Finder to start DroidFarm. It will:
#
#   1. Re-run mac/setup.sh if anything is missing (idempotent — fast on subsequent runs).
#   2. Activate the venv at ~/.droidfarm/venv.
#   3. Export DROIDFARM_STATIC_DIR so the backend serves the React UI from frontend/dist.
#   4. Start the FastAPI backend (uvicorn) on 127.0.0.1:7870.
#   5. Open http://127.0.0.1:7870 in the default browser.
#
# Mac equivalent of the Windows DroidFarm.bat. Logs to ~/.droidfarm/logs/launcher.log.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DROIDFARM_HOME="${HOME}/.droidfarm"
VENV_DIR="${DROIDFARM_HOME}/venv"
LOG_DIR="${DROIDFARM_HOME}/logs"
LOG_FILE="${LOG_DIR}/launcher.log"
mkdir -p "${LOG_DIR}"

if [[ -t 1 ]]; then
  C_GREEN=$'\e[32m'; C_RED=$'\e[31m'; C_BOLD=$'\e[1m'; C_RESET=$'\e[0m'
else
  C_GREEN=""; C_RED=""; C_BOLD=""; C_RESET=""
fi

log()  { printf "%s[droidfarm]%s %s\n" "${C_BOLD}" "${C_RESET}" "$*" | tee -a "${LOG_FILE}"; }
fail() { printf "%s[droidfarm] %s%s\n" "${C_RED}${C_BOLD}" "$*" "${C_RESET}" | tee -a "${LOG_FILE}" >&2; exit 1; }

# Run setup if anything is missing.
if [[ ! -x "${VENV_DIR}/bin/python" || ! -d "${REPO_ROOT}/frontend/dist" ]]; then
  log "first-run / incomplete install — running setup.sh"
  bash "${REPO_ROOT}/mac/setup.sh"
fi

# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"

# Export Android SDK location so the driver can find emulator/avdmanager/adb.
export ANDROID_SDK_ROOT="${ANDROID_SDK_ROOT:-${HOME}/Library/Android/sdk}"
export ANDROID_HOME="${ANDROID_SDK_ROOT}"
export ANDROID_AVD_HOME="${ANDROID_AVD_HOME:-${HOME}/.android/avd}"

# Bundle the prebuilt React app from the repo's frontend/dist.
export DROIDFARM_STATIC_DIR="${REPO_ROOT}/frontend/dist"

DROIDFARM_HOST="${DROIDFARM_HOST:-127.0.0.1}"
DROIDFARM_PORT="${DROIDFARM_PORT:-7870}"

log "launching backend on http://${DROIDFARM_HOST}:${DROIDFARM_PORT}"
log "  python:      $(python --version 2>&1)"
log "  android sdk: ${ANDROID_SDK_ROOT}"
log "  static:      ${DROIDFARM_STATIC_DIR}"
log "  log file:    ${LOG_FILE}"

# Start the backend in the background, tee its output to the log.
python -m droidfarm >> "${LOG_FILE}" 2>&1 &
BACKEND_PID=$!

cleanup() {
  log "shutting down (pid=${BACKEND_PID})"
  kill "${BACKEND_PID}" 2>/dev/null || true
  wait "${BACKEND_PID}" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# Wait for backend to be ready, then open the browser.
URL="http://${DROIDFARM_HOST}:${DROIDFARM_PORT}"
for _ in {1..60}; do
  if curl -fsS "${URL}/api/health" >/dev/null 2>&1; then
    log "backend ready — opening ${URL}"
    open "${URL}"
    break
  fi
  sleep 1
done

# Wait on backend forever (or until the user kills the launcher).
wait "${BACKEND_PID}"
