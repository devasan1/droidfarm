#!/usr/bin/env bash
# DroidFarm — Mac setup script (one-shot, idempotent).
#
# Installs everything needed to run DroidFarm with the Google Android Emulator
# driver on a fresh macOS machine (M-series or Intel):
#
#   1. Xcode Command Line Tools (compiler + git)
#   2. Homebrew                  (https://brew.sh)
#   3. OpenJDK 17                (required by avdmanager / sdkmanager)
#   4. Python 3.11               (backend runtime)
#   5. Node.js 20 + npm          (frontend build)
#   6. Google Android SDK        (cmdline-tools + platform-tools + emulator)
#   7. Android system image      (arm64-v8a on Apple Silicon, x86_64 on Intel)
#   8. _droidfarm_template_factory AVD (cloned by every new phone)
#   9. DroidFarm Python venv     (under ~/.droidfarm/venv) with the backend
#      pip-installed in editable mode
#
# Re-run any time — every step skips if already done. Safe to interrupt with
# Ctrl-C and resume by re-running.

set -euo pipefail

# ----- color/log helpers ------------------------------------------------------
if [[ -t 1 ]]; then
  C_RESET=$'\e[0m'; C_BOLD=$'\e[1m'; C_DIM=$'\e[2m'
  C_GREEN=$'\e[32m'; C_YELLOW=$'\e[33m'; C_RED=$'\e[31m'; C_BLUE=$'\e[34m'
else
  C_RESET=""; C_BOLD=""; C_DIM=""; C_GREEN=""; C_YELLOW=""; C_RED=""; C_BLUE=""
fi
log()    { printf "%s==>%s %s\n" "${C_BLUE}${C_BOLD}" "${C_RESET}" "$*"; }
ok()     { printf "%s ✓%s %s\n" "${C_GREEN}" "${C_RESET}" "$*"; }
warn()   { printf "%s ! %s %s\n" "${C_YELLOW}" "${C_RESET}" "$*" >&2; }
die()    { printf "%s ✗%s %s\n" "${C_RED}" "${C_RESET}" "$*" >&2; exit 1; }
section(){ printf "\n%s%s%s\n" "${C_BOLD}" "$*" "${C_RESET}"; }

# ----- preflight --------------------------------------------------------------
section "DroidFarm — Mac setup"
[[ "$(uname)" == "Darwin" ]] || die "This script is for macOS. Use the Windows .bat or run on Linux."

ARCH="$(uname -m)"
if [[ "$ARCH" == "arm64" ]]; then
  log "Apple Silicon detected ($ARCH) — using arm64 system images (native, fast)"
  ANDROID_ABI="arm64-v8a"
else
  log "Intel Mac detected ($ARCH) — using x86_64 system images (HAXM-accelerated)"
  ANDROID_ABI="x86_64"
fi
ANDROID_SYSTEM_IMAGE="system-images;android-34;google_apis;${ANDROID_ABI}"
log "system image: ${ANDROID_SYSTEM_IMAGE}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DROIDFARM_HOME="${HOME}/.droidfarm"
ANDROID_SDK_ROOT="${ANDROID_SDK_ROOT:-${HOME}/Library/Android/sdk}"
ANDROID_AVD_HOME="${ANDROID_AVD_HOME:-${HOME}/.android/avd}"
TEMPLATE_NAME="_droidfarm_template_factory"

mkdir -p "${DROIDFARM_HOME}" "${ANDROID_SDK_ROOT}" "${ANDROID_AVD_HOME}"

# ----- 1. Xcode Command Line Tools --------------------------------------------
section "[1/9] Xcode Command Line Tools"
if xcode-select -p >/dev/null 2>&1; then
  ok "already installed: $(xcode-select -p)"
else
  log "installing — a system dialog will pop up; click Install. This downloads ~1GB."
  xcode-select --install || true
  log "waiting for installation to complete (poll every 15s)…"
  while ! xcode-select -p >/dev/null 2>&1; do
    sleep 15
    printf "."
  done
  echo
  ok "installed"
fi

# ----- 2. Homebrew ------------------------------------------------------------
section "[2/9] Homebrew"
if command -v brew >/dev/null 2>&1; then
  ok "already installed: $(brew --prefix)"
else
  log "installing Homebrew (will prompt for sudo password)…"
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  # Add to PATH for this script and for the user's shell.
  if [[ -d /opt/homebrew/bin ]]; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
    BREW_SHELLENV="/opt/homebrew/bin/brew shellenv"
  elif [[ -d /usr/local/bin ]]; then
    eval "$(/usr/local/bin/brew shellenv)"
    BREW_SHELLENV="/usr/local/bin/brew shellenv"
  else
    die "Homebrew installed but no bin dir found — please re-run this script in a new terminal."
  fi
  for rc in "${HOME}/.zprofile" "${HOME}/.bash_profile"; do
    if ! grep -q "brew shellenv" "$rc" 2>/dev/null; then
      printf '\neval "$(%s)"\n' "$BREW_SHELLENV" >> "$rc"
    fi
  done
  ok "installed"
fi

# ----- 3. OpenJDK 17 ----------------------------------------------------------
section "[3/9] OpenJDK 17"
if /usr/libexec/java_home -v 17 >/dev/null 2>&1; then
  ok "Java 17 found: $(/usr/libexec/java_home -v 17)"
else
  brew install --quiet openjdk@17
  # Symlink so /usr/libexec/java_home picks it up.
  if [[ -d /opt/homebrew/opt/openjdk@17 ]]; then
    sudo ln -sfn /opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk \
                 /Library/Java/JavaVirtualMachines/openjdk-17.jdk
  elif [[ -d /usr/local/opt/openjdk@17 ]]; then
    sudo ln -sfn /usr/local/opt/openjdk@17/libexec/openjdk.jdk \
                 /Library/Java/JavaVirtualMachines/openjdk-17.jdk
  fi
  ok "installed"
fi
JAVA_HOME="$(/usr/libexec/java_home -v 17)"
export JAVA_HOME
log "JAVA_HOME=${JAVA_HOME}"

# ----- 4. Python 3.11 ---------------------------------------------------------
section "[4/9] Python 3.11"
if command -v python3.11 >/dev/null 2>&1; then
  ok "already installed: $(python3.11 --version)"
else
  brew install --quiet python@3.11
  ok "installed"
fi
PYTHON_BIN="$(command -v python3.11)"

# ----- 5. Node.js 20 ----------------------------------------------------------
section "[5/9] Node.js 20 + npm"
if command -v node >/dev/null 2>&1; then
  NODE_MAJOR=$(node -v | sed 's/^v\([0-9]*\).*/\1/')
  if (( NODE_MAJOR >= 18 )); then
    ok "already installed: $(node -v)"
  else
    warn "old Node ($(node -v)) detected — upgrading to node@20"
    brew install --quiet node@20
    brew link --overwrite --force node@20
  fi
else
  brew install --quiet node@20
  brew link --overwrite --force node@20
  ok "installed"
fi

# ----- 6. Android SDK (cmdline-tools, platform-tools, emulator) ---------------
section "[6/9] Android SDK"
SDKMANAGER="${ANDROID_SDK_ROOT}/cmdline-tools/latest/bin/sdkmanager"
if [[ -x "$SDKMANAGER" ]]; then
  ok "cmdline-tools already installed under ${ANDROID_SDK_ROOT}"
else
  log "downloading Android cmdline-tools…"
  CMDLINE_ZIP="$(mktemp -t android-cmdline-XXXXXX.zip)"
  # Latest stable: 11076708 (2024-04). Replaces only the cmdline-tools/.
  curl -fSL -o "${CMDLINE_ZIP}" \
    "https://dl.google.com/android/repository/commandlinetools-mac-11076708_latest.zip"
  TMP_DIR="$(mktemp -d -t android-cmdline-XXXXXX)"
  unzip -q "${CMDLINE_ZIP}" -d "${TMP_DIR}"
  mkdir -p "${ANDROID_SDK_ROOT}/cmdline-tools"
  rm -rf "${ANDROID_SDK_ROOT}/cmdline-tools/latest"
  mv "${TMP_DIR}/cmdline-tools" "${ANDROID_SDK_ROOT}/cmdline-tools/latest"
  rm -rf "${TMP_DIR}" "${CMDLINE_ZIP}"
  ok "cmdline-tools installed"
fi

export ANDROID_SDK_ROOT ANDROID_HOME="${ANDROID_SDK_ROOT}"
export PATH="${ANDROID_SDK_ROOT}/cmdline-tools/latest/bin:${ANDROID_SDK_ROOT}/platform-tools:${ANDROID_SDK_ROOT}/emulator:${PATH}"

# Accept all Android SDK licenses non-interactively.
log "accepting Android SDK licenses…"
yes | "${SDKMANAGER}" --licenses >/dev/null 2>&1 || true

# Install the packages we need.
log "installing platform-tools, emulator, system image (this may take a few minutes)…"
"${SDKMANAGER}" --install \
  "platform-tools" \
  "emulator" \
  "platforms;android-34" \
  "${ANDROID_SYSTEM_IMAGE}" >/dev/null
ok "Android SDK ready"

# ----- 7. _droidfarm_template_factory AVD -------------------------------------
section "[7/9] Factory template AVD"
AVDMANAGER="${ANDROID_SDK_ROOT}/cmdline-tools/latest/bin/avdmanager"
if [[ -d "${ANDROID_AVD_HOME}/${TEMPLATE_NAME}.avd" ]]; then
  ok "${TEMPLATE_NAME} already exists"
else
  log "creating ${TEMPLATE_NAME}…"
  echo "no" | "${AVDMANAGER}" --silent create avd \
    -n "${TEMPLATE_NAME}" \
    -k "${ANDROID_SYSTEM_IMAGE}" \
    --abi "${ANDROID_ABI}" \
    --device "pixel_6" \
    --force
  ok "created"
fi

# ----- 8. DroidFarm Python venv -----------------------------------------------
section "[8/9] DroidFarm Python venv"
VENV_DIR="${DROIDFARM_HOME}/venv"
if [[ -x "${VENV_DIR}/bin/python" ]]; then
  ok "venv already exists at ${VENV_DIR}"
else
  log "creating venv at ${VENV_DIR}…"
  "${PYTHON_BIN}" -m venv "${VENV_DIR}"
fi
"${VENV_DIR}/bin/python" -m pip install --quiet --upgrade pip
log "installing backend into venv (editable)…"
"${VENV_DIR}/bin/python" -m pip install --quiet -e "${REPO_ROOT}/backend"
ok "backend installed"

# ----- 9. Build the React frontend --------------------------------------------
section "[9/9] Frontend build"
log "npm install…"
( cd "${REPO_ROOT}/frontend" && npm install --silent )
log "npm run build…"
( cd "${REPO_ROOT}/frontend" && npm run build --silent )
ok "frontend built (${REPO_ROOT}/frontend/dist)"

# ----- done -------------------------------------------------------------------
section "Done"
cat <<EOF

DroidFarm is ready.

  Repo:           ${REPO_ROOT}
  Android SDK:    ${ANDROID_SDK_ROOT}
  AVDs:           ${ANDROID_AVD_HOME}
  Python venv:    ${VENV_DIR}
  Factory AVD:    ${TEMPLATE_NAME} (${ANDROID_ABI})

Next:

  1. Launch DroidFarm:
       $(printf "${C_BOLD}%s/mac/droidfarm.command${C_RESET}" "${REPO_ROOT}")

     (or double-click that file in Finder)

  2. Browser opens at http://127.0.0.1:7870

  3. Add a phone — it will clone the factory template and boot.

To uninstall everything DroidFarm-specific (keeps the SDK), run:
  ${REPO_ROOT}/mac/uninstall.sh

EOF
