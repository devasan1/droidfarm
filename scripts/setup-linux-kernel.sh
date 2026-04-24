#!/usr/bin/env bash
# Set up a Linux host to run real Android via redroid (the Android-on-Docker
# project). Does phases A + B + C from docs/linux-kernel-setup.md end-to-end.
#
# Safe to re-run: every step is idempotent.
#
# Tested on: Ubuntu 22.04 + 5.15.0-generic kernel, Ubuntu 24.04 + 6.8.0-generic.
# Will NOT work on: stripped container kernels (CI runners, GKE nodes, Fly.io),
# kernels < 5.12 without DKMS (see docs/linux-kernel-setup.md Option 1).

set -e

info() { printf "\n\033[1;36m==> %s\033[0m\n" "$*"; }
warn() { printf "\033[1;33m!!  %s\033[0m\n" "$*" >&2; }
die()  { printf "\033[1;31m!!  %s\033[0m\n" "$*" >&2; exit 1; }

require_root() {
  [[ $EUID -eq 0 ]] || die "This script needs sudo. Re-run: sudo $0"
}

require_ubuntu() {
  if [[ ! -f /etc/os-release ]] || ! grep -q '^ID=ubuntu' /etc/os-release; then
    warn "This script is tested on Ubuntu. Other distros may need manual tweaks."
  fi
}

# -------- Phase A: binder kernel support -----------------------------------

phase_a_check_binder() {
  info "Phase A — checking kernel binder support"
  if grep -q '^nodev[[:space:]]*binder$' /proc/filesystems; then
    echo "  OK  kernel has binderfs built in"
    return 0
  fi
  warn "Kernel $(uname -r) does not expose 'binder' in /proc/filesystems."
  warn "You probably need to either:"
  warn "  (a) boot a -generic Ubuntu kernel (5.12+) that has CONFIG_ANDROID_BINDERFS=y, OR"
  warn "  (b) DKMS-install anbox-modules (see docs/linux-kernel-setup.md §A2)."
  warn ""
  warn "If this is a container (Docker, LXC, GKE node, etc.) you cannot load"
  warn "kernel modules from inside — use a real VM with full kernel access."
  die  "Aborting: kernel does not support binder."
}

phase_a_mount_binderfs() {
  info "Phase A — mounting binderfs"
  mkdir -p /dev/binderfs
  if mountpoint -q /dev/binderfs; then
    echo "  OK  /dev/binderfs already mounted"
  else
    mount -t binder none /dev/binderfs
    echo "  OK  /dev/binderfs mounted"
  fi

  # persist to fstab
  if ! grep -q '^binder /dev/binderfs binder' /etc/fstab; then
    echo "binder /dev/binderfs binder defaults 0 0" >> /etc/fstab
    echo "  OK  /etc/fstab updated"
  else
    echo "  OK  /etc/fstab already has binderfs entry"
  fi

  [[ -e /dev/binderfs/binder-control ]] \
    || die "Phase A failed: /dev/binderfs/binder-control missing after mount"
}

# -------- Phase B: KVM -----------------------------------------------------

phase_b_kvm() {
  info "Phase B — KVM"
  if [[ ! -e /dev/kvm ]]; then
    warn "/dev/kvm not found. Your VM doesn't expose hardware virtualization."
    warn "On cloud VMs this is a VM-creation-time flag:"
    warn "  GCP:  --enable-nested-virtualization --min-cpu-platform='Intel Cascade Lake'"
    warn "  AWS:  use a .metal instance (c5n.metal, etc.)"
    warn "  Azure: most D-series v3+ have it by default"
    warn "redroid will still work, just ~3-5x slower (software emulation)."
    echo
    return 0
  fi
  echo "  OK  /dev/kvm exists"

  apt-get install -y qemu-kvm libvirt-daemon-system cpu-checker >/dev/null
  echo "  OK  qemu-kvm + libvirt installed"

  if kvm-ok >/dev/null 2>&1; then
    echo "  OK  kvm-ok: KVM acceleration available"
  else
    warn "kvm-ok reports KVM is not usable — check 'sudo kvm-ok' output"
  fi

  # Add the actual user (not root) to the kvm/libvirt groups.
  # SUDO_USER is the user who ran sudo; fall back to the owner of $HOME.
  target_user="${SUDO_USER:-}"
  [[ -z "$target_user" ]] && target_user="$(stat -c '%U' "$HOME" 2>/dev/null || echo '')"
  if [[ -n "$target_user" && "$target_user" != "root" ]]; then
    usermod -aG kvm,libvirt "$target_user"
    echo "  OK  added $target_user to kvm,libvirt groups (log out + in to pick up)"
  fi
}

# -------- Phase C: Docker + redroid ----------------------------------------

phase_c_docker() {
  info "Phase C — Docker"
  if command -v docker >/dev/null 2>&1; then
    echo "  OK  docker already installed: $(docker --version)"
  else
    echo "  installing docker via get.docker.com ..."
    curl -fsSL https://get.docker.com | sh
    systemctl enable --now docker
    echo "  OK  docker installed"
  fi

  target_user="${SUDO_USER:-}"
  if [[ -n "$target_user" && "$target_user" != "root" ]]; then
    usermod -aG docker "$target_user"
    echo "  OK  added $target_user to docker group"
  fi
}

phase_c_redroid() {
  info "Phase C — redroid image + smoke boot"
  REDROID_IMAGE="${REDROID_IMAGE:-redroid/redroid:13.0.0_64only-latest}"

  if ! docker image inspect "$REDROID_IMAGE" >/dev/null 2>&1; then
    echo "  pulling $REDROID_IMAGE ..."
    docker pull "$REDROID_IMAGE"
  else
    echo "  OK  image $REDROID_IMAGE already present"
  fi

  # Install adb if missing (needed for the smoke test).
  if ! command -v adb >/dev/null 2>&1; then
    apt-get install -y adb >/dev/null
    echo "  OK  adb installed"
  fi

  info "Smoke-booting one redroid container for 60s ..."
  # Clean up any previous smoke container.
  docker rm -f redroid-smoke >/dev/null 2>&1 || true
  docker run -d --privileged \
    -p 5555:5555 \
    --name redroid-smoke \
    "$REDROID_IMAGE" \
    >/dev/null

  for i in {1..12}; do
    sleep 5
    adb connect localhost:5555 >/dev/null 2>&1 || true
    if adb -s localhost:5555 shell getprop sys.boot_completed 2>/dev/null | grep -q '^1'; then
      release=$(adb -s localhost:5555 shell getprop ro.build.version.release 2>/dev/null | tr -d '\r\n')
      echo "  OK  redroid booted: Android $release"
      docker stop redroid-smoke >/dev/null
      docker rm redroid-smoke >/dev/null
      return 0
    fi
    echo "     waiting for boot ($((i*5))s) ..."
  done

  warn "redroid did not report boot_completed=1 after 60s."
  warn "Inspect with:  docker logs redroid-smoke"
  warn "When you're done:  docker rm -f redroid-smoke"
  return 1
}

# -------- Main -------------------------------------------------------------

main() {
  require_root
  require_ubuntu

  phase_a_check_binder
  phase_a_mount_binderfs
  phase_b_kvm
  phase_c_docker
  phase_c_redroid || warn "Phase C smoke boot did not pass."

  info "Done."
  cat <<'EOF'

Next steps:
  1. Log out + back in (or `newgrp docker; newgrp kvm`) so group membership
     takes effect for your user.
  2. Verify by hand:
        grep binder /proc/filesystems
        ls /dev/binderfs
        ls /dev/kvm
        docker run --rm -itd --privileged -p 5555:5555 --name r1 \
          redroid/redroid:13.0.0_64only-latest
        sleep 45
        adb connect localhost:5555
        adb shell getprop ro.build.version.release
        docker stop r1
  3. Wire redroid into DroidFarm: see docs/linux-kernel-setup.md §D.
EOF
}

main "$@"
