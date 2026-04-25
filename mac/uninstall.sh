#!/usr/bin/env bash
# DroidFarm — Mac uninstaller.
#
# Removes everything DroidFarm-specific (venv, logs, factory AVD, AVDs the
# user created) WITHOUT removing shared tools (Homebrew, Java, Python, Node,
# the Android SDK itself). Re-run setup.sh after this to start fresh.
#
# Use --all to also delete the Android SDK + AVDs (NUKE option).

set -euo pipefail

PURGE_SDK=false
for arg in "$@"; do
  case "$arg" in
    --all|--purge-sdk) PURGE_SDK=true ;;
    -h|--help)
      cat <<EOF
Usage: $0 [--all]

  (default)  Remove ~/.droidfarm and DroidFarm-specific AVDs.
             Keep Android SDK + system images so re-install is fast.
  --all      Also remove the entire Android SDK and every AVD.
EOF
      exit 0 ;;
  esac
done

if [[ -t 1 ]]; then
  C_YELLOW=$'\e[33m'; C_RED=$'\e[31m'; C_BOLD=$'\e[1m'; C_RESET=$'\e[0m'
else
  C_YELLOW=""; C_RED=""; C_BOLD=""; C_RESET=""
fi
log()  { printf "%s==>%s %s\n" "${C_YELLOW}${C_BOLD}" "${C_RESET}" "$*"; }

DROIDFARM_HOME="${HOME}/.droidfarm"
ANDROID_AVD_HOME="${ANDROID_AVD_HOME:-${HOME}/.android/avd}"
ANDROID_SDK_ROOT="${ANDROID_SDK_ROOT:-${HOME}/Library/Android/sdk}"

log "removing ~/.droidfarm (venv + logs + cached state)"
rm -rf "${DROIDFARM_HOME}"

log "removing factory template AVD"
rm -rf "${ANDROID_AVD_HOME}/_droidfarm_template_factory.avd" \
       "${ANDROID_AVD_HOME}/_droidfarm_template_factory.ini"

if $PURGE_SDK; then
  printf "%s%sThis will delete the entire Android SDK at %s — type YES to continue: %s" \
    "${C_RED}" "${C_BOLD}" "${ANDROID_SDK_ROOT}" "${C_RESET}"
  read -r confirm
  if [[ "$confirm" == "YES" ]]; then
    log "removing Android SDK + all AVDs"
    rm -rf "${ANDROID_SDK_ROOT}" "${ANDROID_AVD_HOME}"
  else
    log "skipped SDK removal"
  fi
fi

log "done"
