#!/usr/bin/env bash
# =============================================================
#  DroidFarm  -  GCP nested-virt launcher
#
#  Provisions a GCE VM with nested virtualization enabled, installs
#  Linux + KVM + Android SDK + DroidFarm, runs the backend bound to
#  127.0.0.1 (no public exposure), and prints the SSH local-port-
#  forward command you paste on your laptop to access the UI at
#  http://localhost:7870.
#
#  Usage (from your laptop, with gcloud already authenticated):
#      ./scripts/gcp-launch.sh
#      INSTANCE_NAME=my-farm MACHINE_TYPE=n2-standard-16 ./scripts/gcp-launch.sh
#
#  Defaults:
#      INSTANCE_NAME = droidfarm
#      ZONE          = us-central1-a
#      MACHINE_TYPE  = n2-standard-8 (Intel Cascade Lake, 8 vCPU / 32 GB)
#      DISK_SIZE_GB  = 200
#      IMAGE_FAMILY  = ubuntu-2204-lts
#
#  Notes:
#    * --enable-nested-virtualization requires Intel CPUs (N1/N2/C2/C3),
#      not E2/N2D/T2D/T2A. The default n2-standard-8 satisfies this.
#    * Performance with nested virt is ~30–50% of bare metal — fine for
#      1–8 phones, painful past that. For heavy farms, use a bare-metal
#      host (Hetzner AX line, AWS .metal, Equinix Metal).
#    * The script binds DroidFarm to 127.0.0.1 on the VM. Use the printed
#      `gcloud compute ssh ... -- -L` command from your laptop to reach
#      it at http://localhost:7870. No firewall rules required.
# =============================================================
set -euo pipefail

INSTANCE_NAME="${INSTANCE_NAME:-droidfarm}"
ZONE="${ZONE:-us-central1-a}"
MACHINE_TYPE="${MACHINE_TYPE:-n2-standard-8}"
DISK_SIZE_GB="${DISK_SIZE_GB:-200}"
IMAGE_FAMILY="${IMAGE_FAMILY:-ubuntu-2204-lts}"
IMAGE_PROJECT="${IMAGE_PROJECT:-ubuntu-os-cloud}"
DROIDFARM_PORT="${DROIDFARM_PORT:-7870}"
DROIDFARM_REPO="${DROIDFARM_REPO:-https://github.com/devasan1/droidfarm.git}"
DROIDFARM_REF="${DROIDFARM_REF:-main}"

say()  { printf '\033[1;36m[gcp-launch]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[gcp-launch]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m[gcp-launch]\033[0m %s\n' "$*" >&2; exit 1; }

command -v gcloud >/dev/null 2>&1 \
  || die "gcloud CLI not found. Install: https://cloud.google.com/sdk/docs/install"

# Sanity-check that the requested machine type is on the nested-virt allowlist.
case "$MACHINE_TYPE" in
  n1-*|n2-*|c2-*|c3-*) ;;  # Intel families that support nested virt
  *)
    warn "MACHINE_TYPE=$MACHINE_TYPE is NOT on GCP's nested-virt allowlist."
    warn "Supported families (Intel only): n1-*, n2-*, c2-*, c3-*."
    warn "Unsupported: e2-* (no nested virt), n2d-* / t2d-* (AMD), t2a-* (Arm)."
    die  "Pick a supported machine type or set MACHINE_TYPE explicitly."
    ;;
esac

PROJECT="$(gcloud config get-value project 2>/dev/null || true)"
[[ -n "$PROJECT" ]] || die "gcloud project is not set. Run: gcloud config set project YOUR_PROJECT"

say "project       = $PROJECT"
say "instance      = $INSTANCE_NAME"
say "zone          = $ZONE"
say "machine type  = $MACHINE_TYPE  (Intel, nested-virt-capable)"
say "boot disk     = ${DISK_SIZE_GB} GB pd-ssd, $IMAGE_FAMILY"
say "droidfarm ref = $DROIDFARM_REF"

# --------------------------------------------------------------
# 1. create the VM (idempotent — skips if it already exists)
# --------------------------------------------------------------

if gcloud compute instances describe "$INSTANCE_NAME" --zone="$ZONE" >/dev/null 2>&1; then
  say "instance already exists — skipping create."
else
  say "creating instance with --enable-nested-virtualization ..."
  gcloud compute instances create "$INSTANCE_NAME" \
    --zone="$ZONE" \
    --machine-type="$MACHINE_TYPE" \
    --image-family="$IMAGE_FAMILY" \
    --image-project="$IMAGE_PROJECT" \
    --boot-disk-size="${DISK_SIZE_GB}GB" \
    --boot-disk-type=pd-ssd \
    --enable-nested-virtualization \
    --min-cpu-platform="Intel Cascade Lake" \
    --tags=droidfarm \
    --metadata=enable-oslogin=TRUE
fi

# --------------------------------------------------------------
# 2. wait for SSH to come up
# --------------------------------------------------------------

say "waiting for SSH ..."
for _ in $(seq 1 60); do
  if gcloud compute ssh "$INSTANCE_NAME" --zone="$ZONE" --tunnel-through-iap \
        --command="echo ready" >/dev/null 2>&1; then
    break
  fi
  sleep 5
done

# --------------------------------------------------------------
# 3. provision: KVM, Android SDK, DroidFarm
# --------------------------------------------------------------

say "provisioning KVM + Android SDK + DroidFarm on the VM ..."

# Remote bootstrap script. Runs as the SSH user (gcloud injects sudo via
# OS Login). Idempotent — safe to re-run.
REMOTE_SCRIPT=$(cat <<'REMOTE'
set -euo pipefail

say()  { printf '\033[1;36m[remote]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[remote]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m[remote]\033[0m %s\n' "$*" >&2; exit 1; }

# /dev/kvm preflight — if this fails, --enable-nested-virtualization
# wasn't actually applied (or you picked a non-Intel machine type).
if [[ ! -e /dev/kvm ]]; then
  warn "/dev/kvm is missing. The VM was launched without nested virt."
  warn "Stop the instance, recreate with --enable-nested-virtualization on"
  warn "an Intel machine type (n1/n2/c2/c3), and re-run this script."
  die  "Aborting: nested virtualization is required."
fi
say "/dev/kvm exists — nested virt is active."

# System packages
sudo apt-get update -qq
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
  qemu-kvm libvirt-daemon-system cpu-checker \
  python3.11 python3.11-venv python3-pip \
  openjdk-17-jdk-headless \
  curl git unzip ca-certificates \
  android-tools-adb \
  >/dev/null

# Node 20 (DroidFarm's frontend builder needs >= 20)
if ! command -v node >/dev/null 2>&1 || [[ "$(node -v | sed 's/v//;s/\..*//')" -lt 20 ]]; then
  curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash - >/dev/null
  sudo apt-get install -y -qq nodejs >/dev/null
fi

# Add the user to kvm/libvirt so they can talk to /dev/kvm without sudo.
sudo usermod -aG kvm,libvirt "$USER" || true

# Android command-line tools (required by AndroidEmulatorDriver)
SDK_ROOT="$HOME/Android/Sdk"
if [[ ! -d "$SDK_ROOT/cmdline-tools/latest" ]]; then
  say "installing Android command-line tools ..."
  mkdir -p "$SDK_ROOT/cmdline-tools"
  cd /tmp
  curl -fsSL https://dl.google.com/android/repository/commandlinetools-linux-11076708_latest.zip -o cmdtools.zip
  unzip -q cmdtools.zip
  rm -rf "$SDK_ROOT/cmdline-tools/latest"
  mv cmdline-tools "$SDK_ROOT/cmdline-tools/latest"
  rm -f cmdtools.zip
fi

export ANDROID_SDK_ROOT="$SDK_ROOT"
export ANDROID_HOME="$SDK_ROOT"
export PATH="$SDK_ROOT/cmdline-tools/latest/bin:$SDK_ROOT/platform-tools:$SDK_ROOT/emulator:$PATH"

# JAVA_HOME — sdkmanager / avdmanager are JDK tools and refuse to start otherwise.
export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
export PATH="$JAVA_HOME/bin:$PATH"

if [[ ! -x "$SDK_ROOT/emulator/emulator" ]]; then
  say "installing platform-tools + emulator + system-image (Android 14, x86_64) ..."
  yes | sdkmanager --licenses >/dev/null
  sdkmanager --install \
    "platform-tools" \
    "emulator" \
    "platforms;android-34" \
    "system-images;android-34;google_apis;x86_64" >/dev/null
fi

# Persist SDK + JDK env for future logins (so manual SSH sessions can run
# avdmanager / emulator without re-exporting these every time).
SHELL_RC="$HOME/.bashrc"
grep -q ANDROID_SDK_ROOT "$SHELL_RC" 2>/dev/null || cat >> "$SHELL_RC" <<EOF

# DroidFarm — Java + Android SDK
export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
export ANDROID_SDK_ROOT="$SDK_ROOT"
export ANDROID_HOME="$SDK_ROOT"
export PATH="\$JAVA_HOME/bin:\$ANDROID_SDK_ROOT/cmdline-tools/latest/bin:\$ANDROID_SDK_ROOT/platform-tools:\$ANDROID_SDK_ROOT/emulator:\$PATH"
EOF

# DroidFarm checkout. Use a non-shallow clone so the user can `git fetch`
# arbitrary fix branches later without needing `--unshallow` first.
DROIDFARM_DIR="$HOME/droidfarm"
if [[ ! -d "$DROIDFARM_DIR/.git" ]]; then
  say "cloning DroidFarm ..."
  git clone --branch "${DROIDFARM_REF:-main}" \
    "${DROIDFARM_REPO:-https://github.com/devasan1/droidfarm.git}" "$DROIDFARM_DIR"
else
  ( cd "$DROIDFARM_DIR" && git fetch origin "${DROIDFARM_REF:-main}" && git reset --hard FETCH_HEAD ) >/dev/null
fi

# Run the launcher in the background. Bind 127.0.0.1 — the SSH tunnel
# from the user's laptop is the only way in.
mkdir -p "$HOME/.droidfarm"
cd "$DROIDFARM_DIR"

# If the launcher is already up, bounce it so we pick up new code.
if pgrep -f "uvicorn droidfarm.main:app" >/dev/null 2>&1; then
  say "stopping existing droidfarm process ..."
  pkill -f "uvicorn droidfarm.main:app" || true
  sleep 2
fi

# Sanity-check kvm group membership before starting. groups added via
# `usermod -aG kvm` only take effect on a new login session — if the
# bootstrap user's shell pre-dates the group add, the backend it spawns
# will inherit the old group set and fail with EACCES on /dev/kvm.
if ! id -nG | tr ' ' '\n' | grep -qx kvm; then
  warn "current shell is NOT in the 'kvm' group yet (sudo usermod -aG kvm just ran)."
  warn "the backend started below will inherit the old group set and won't be"
  warn "able to spawn emulators. Log out, SSH back in, and re-run this script"
  warn "to pick up the group. Or restart the backend manually after re-login."
fi

say "starting DroidFarm (bind 127.0.0.1:${DROIDFARM_PORT:-7870}) ..."
DROIDFARM_HOST=127.0.0.1 \
DROIDFARM_PORT="${DROIDFARM_PORT:-7870}" \
JAVA_HOME="$JAVA_HOME" \
ANDROID_SDK_ROOT="$SDK_ROOT" \
ANDROID_HOME="$SDK_ROOT" \
PATH="$JAVA_HOME/bin:$SDK_ROOT/cmdline-tools/latest/bin:$SDK_ROOT/platform-tools:$SDK_ROOT/emulator:$PATH" \
nohup ./droidfarm.sh >> "$HOME/.droidfarm/bootstrap.log" 2>&1 &

say "DroidFarm launching in the background. Tail logs with:"
say "  tail -f ~/.droidfarm/bootstrap.log"
REMOTE
)

# Push the env knobs into the remote shell.
gcloud compute ssh "$INSTANCE_NAME" --zone="$ZONE" --tunnel-through-iap \
  --command="DROIDFARM_PORT='$DROIDFARM_PORT' \
             DROIDFARM_REPO='$DROIDFARM_REPO' \
             DROIDFARM_REF='$DROIDFARM_REF' \
             bash -s" <<<"$REMOTE_SCRIPT"

# --------------------------------------------------------------
# 4. print the SSH tunnel command the user runs on their laptop
# --------------------------------------------------------------

cat <<EOF

================================================================
DroidFarm is running on $INSTANCE_NAME ($ZONE), bound to 127.0.0.1.

To open it in your local browser, open a new terminal on your
laptop and run:

  ./scripts/gcp-tunnel.sh

…or the equivalent gcloud one-liner:

  gcloud compute ssh $INSTANCE_NAME --zone=$ZONE --tunnel-through-iap -- \\
    -N -L $DROIDFARM_PORT:127.0.0.1:$DROIDFARM_PORT

Then visit:  http://localhost:$DROIDFARM_PORT

To tear down (you stop being billed for the VM):
  gcloud compute instances delete $INSTANCE_NAME --zone=$ZONE

================================================================
EOF
