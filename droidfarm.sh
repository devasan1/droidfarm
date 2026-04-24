#!/usr/bin/env bash
# =============================================================
#  DroidFarm  -  single-command launcher (Linux / macOS)
#
#  Usage:
#      ./droidfarm.sh
#
#  First run:
#    - checks for Python 3.11+, Node 20+, adb
#      (installs via apt / dnf / pacman / brew where possible)
#    - creates the Python venv and installs the backend
#    - builds the React frontend (production) or runs Vite dev
#    - opens http://localhost:7870 in your browser
#
#  Subsequent runs skip the install phase and launch in ~3 s.
#
#  Note: LDPlayer only exists on Windows. On Linux, DroidFarm
#  defaults to the mock driver (so the full UI works for
#  development + demos). To drive real phones from Linux, set
#  DROIDFARM_DRIVER=redroid and run ./docker-compose.yml (see
#  docs/linux-setup.md for details).
#
#  Anything we do is appended to ~/.droidfarm/bootstrap.log.
# =============================================================
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
DATA_DIR="${DROIDFARM_DATA_DIR:-$HOME/.droidfarm}"
mkdir -p "$DATA_DIR"
LOG="$DATA_DIR/bootstrap.log"

# ----------------------------------------------------------
# tiny logger
# ----------------------------------------------------------
say() { printf '\033[1;36m[droidfarm]\033[0m %s\n' "$*" | tee -a "$LOG" >&2; }
warn() { printf '\033[1;33m[droidfarm]\033[0m %s\n' "$*" | tee -a "$LOG" >&2; }
die() { printf '\033[1;31m[droidfarm]\033[0m %s\n' "$*" | tee -a "$LOG" >&2; exit 1; }

# ----------------------------------------------------------
# package-manager detection
# ----------------------------------------------------------
detect_pm() {
    if   command -v apt-get >/dev/null 2>&1; then echo apt
    elif command -v dnf     >/dev/null 2>&1; then echo dnf
    elif command -v pacman  >/dev/null 2>&1; then echo pacman
    elif command -v brew    >/dev/null 2>&1; then echo brew
    else echo unknown; fi
}

install_pkg() {
    local pm="$1" ; shift
    case "$pm" in
        apt)    sudo apt-get update -qq && sudo apt-get install -y "$@" ;;
        dnf)    sudo dnf install -y "$@" ;;
        pacman) sudo pacman -S --noconfirm "$@" ;;
        brew)   brew install "$@" ;;
        *)      warn "unknown package manager; please install manually: $*" ; return 1 ;;
    esac
}

# ----------------------------------------------------------
# prerequisites
# ----------------------------------------------------------
PM="$(detect_pm)"

# Python 3.11+
if ! command -v python3 >/dev/null 2>&1 || \
   ! python3 -c 'import sys; sys.exit(0 if sys.version_info>=(3,11) else 1)' 2>/dev/null; then
    say "installing python3.11"
    case "$PM" in
        apt) install_pkg apt python3.11 python3.11-venv python3-pip || install_pkg apt python3 python3-venv python3-pip ;;
        dnf) install_pkg dnf python3.11 python3-pip ;;
        pacman) install_pkg pacman python python-pip ;;
        brew) install_pkg brew python@3.11 ;;
        *) die "no Python 3.11+ found and cannot auto-install. install it manually." ;;
    esac
fi
PY=python3
if command -v python3.11 >/dev/null 2>&1; then PY=python3.11; fi

# Node 20+
if ! command -v node >/dev/null 2>&1 || \
   [ "$(node -v | sed 's/v//;s/\..*//')" -lt 20 ]; then
    say "installing node 20+"
    case "$PM" in
        apt)
            curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
            install_pkg apt nodejs
            ;;
        dnf)    install_pkg dnf nodejs ;;
        pacman) install_pkg pacman nodejs npm ;;
        brew)   install_pkg brew node@20 ;;
        *) die "no Node 20+ found and cannot auto-install." ;;
    esac
fi

# adb (optional on Linux — only needed for redroid driver mode)
if ! command -v adb >/dev/null 2>&1; then
    say "installing adb (platform-tools)"
    case "$PM" in
        apt)    install_pkg apt android-tools-adb || warn "adb install failed; continuing" ;;
        dnf)    install_pkg dnf android-tools     || warn "adb install failed; continuing" ;;
        pacman) install_pkg pacman android-tools  || warn "adb install failed; continuing" ;;
        brew)   install_pkg brew android-platform-tools || warn "adb install failed; continuing" ;;
        *) warn "skipping adb install — install manually if you want redroid driver mode" ;;
    esac
fi

# ----------------------------------------------------------
# backend
# ----------------------------------------------------------
cd "$ROOT/backend"
if [ ! -d .venv ]; then
    say "creating python venv"
    "$PY" -m venv .venv
fi
# shellcheck source=/dev/null
. .venv/bin/activate
if [ ! -f .venv/.installed ] || [ pyproject.toml -nt .venv/.installed ]; then
    say "installing backend deps"
    pip install -q --upgrade pip
    pip install -q -e .
    touch .venv/.installed
fi

# ----------------------------------------------------------
# frontend
# ----------------------------------------------------------
cd "$ROOT/frontend"
if [ ! -d node_modules ] || [ package.json -nt node_modules/.installed ]; then
    say "installing frontend deps"
    npm install --silent --no-audit --no-fund
    touch node_modules/.installed
fi

say "building frontend"
npm run build --silent

# ----------------------------------------------------------
# launch
# ----------------------------------------------------------
cd "$ROOT/backend"
PORT="${DROIDFARM_PORT:-7870}"
HOST="${DROIDFARM_HOST:-127.0.0.1}"

say "starting DroidFarm on http://$HOST:$PORT"
# open browser (xdg-open on Linux, open on macOS). Fire-and-forget.
if command -v xdg-open >/dev/null 2>&1; then
    ( sleep 2 && xdg-open "http://$HOST:$PORT" >/dev/null 2>&1 ) &
elif command -v open >/dev/null 2>&1; then
    ( sleep 2 && open "http://$HOST:$PORT" >/dev/null 2>&1 ) &
fi

# Serve the built SPA from the backend so one process = whole app.
# DROIDFARM_STATIC_DIR tells the FastAPI app where to find dist/.
export DROIDFARM_STATIC_DIR="$ROOT/frontend/dist"
export DROIDFARM_DATA_DIR="$DATA_DIR"
exec uvicorn droidfarm.main:app --host "$HOST" --port "$PORT"
