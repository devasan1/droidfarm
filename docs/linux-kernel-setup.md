# Linux kernel setup for real Android (redroid)

This guide gets a Linux host ready to run **real Android** instances via
[redroid](https://github.com/remote-android/redroid-doc). Once complete, you
can replace DroidFarm's mock driver with the (forthcoming) `RedroidDriver` and
run actual Android phones the same way LDPlayer does on Windows.

If you only want to run the DroidFarm UI + backend on Linux (with mock
phones), none of this is required — just run `./droidfarm.sh`.

---

## Requirements at a glance

| Piece                | Why it's needed                                | Check command                |
|----------------------|------------------------------------------------|------------------------------|
| `binder` kernel FS   | Android IPC backbone                           | `grep binder /proc/filesystems` |
| `ashmem_linux` (opt) | Legacy shared memory (kernel ≤ 5.17 only)      | `lsmod \| grep ashmem`       |
| `/dev/kvm`           | Hardware accel (10× speedup)                   | `ls /dev/kvm`                |
| Docker               | Container runtime for redroid image            | `docker --version`           |

---

## Phase A — Kernel support for `binder`

On **stock Ubuntu 22.04 / 24.04** with the `-generic` kernel, Android binder
is built in as `CONFIG_ANDROID_BINDERFS=y` — you don't need DKMS, you just
need to mount binderfs. This is the preferred path.

### Step 1: Check what you have

```bash
uname -r
# Expect: 5.15.0-XX-generic  or  6.8.0-XX-generic  (any -generic ≥ 5.12 is fine)

grep binder /proc/filesystems
# Expect:   nodev   binder
# (If blank → your kernel doesn't have binder built in; see "Custom kernels" below)

ls /lib/modules/$(uname -r)/build
# Expect: a directory full of Makefile, include/, scripts/, etc.
# (If "No such file or directory" → install linux-headers, see below)
```

### Step 2: Mount binderfs

```bash
sudo mkdir -p /dev/binderfs
sudo mount -t binder none /dev/binderfs

# Verify
ls /dev/binderfs
# Expect: binder-control
```

### Step 3: Persist the mount across reboots

```bash
echo "binder /dev/binderfs binder defaults 0 0" | sudo tee -a /etc/fstab
sudo systemctl daemon-reload
```

That's it — binder is ready. Skip phase A2 and go to phase B.

### Phase A2 — If your kernel does NOT have binder built in

You'll know this if `grep binder /proc/filesystems` is empty. Options:

**Option 1 — Install the DKMS modules (old kernels, 5.4–5.10)**

```bash
# Dependencies
sudo apt-get update
sudo apt-get install -y git kmod make gcc dkms linux-headers-$(uname -r)

# Build + install
cd /usr/src
sudo git clone https://github.com/choff/anbox-modules.git
cd anbox-modules
sudo cp anbox.conf /etc/modules-load.d/anbox.conf
sudo cp 99-anbox.rules /lib/udev/rules.d/
sudo cp -rT ashmem /usr/src/anbox-ashmem-1
sudo cp -rT binder /usr/src/anbox-binder-1
sudo dkms install anbox-ashmem/1
sudo dkms install anbox-binder/1
sudo modprobe ashmem_linux
sudo modprobe binder_linux

ls /dev/ashmem /dev/binder*
```

**Option 2 — Compile a new kernel with binder built in (hardcore)**

```bash
# Get kernel source
cd /usr/src
sudo apt-get source linux-image-unsigned-$(uname -r)
cd linux-*

# Enable binder
sudo scripts/config --enable CONFIG_ANDROID_BINDER_IPC
sudo scripts/config --enable CONFIG_ANDROID_BINDERFS
sudo scripts/config --enable CONFIG_ANDROID_BINDER_DEVICES="binder,hwbinder,vndbinder"

# Build (takes ~30 min on 8 cores)
sudo make -j$(nproc) deb-pkg
sudo dpkg -i ../linux-image-*.deb ../linux-headers-*.deb
sudo update-initramfs -u
sudo reboot
```

After reboot: `grep binder /proc/filesystems` should show `nodev binder`.

**Option 3 — Use a cloud VM with a newer kernel** (simplest workaround)

- GCP: switch image family to `ubuntu-2404-lts` (kernel 6.8) or `ubuntu-minimal-2204-lts`.
- AWS: use the latest AL2023 AMI or Ubuntu 24.04.
- Azure: Ubuntu 24.04 LTS Gen2 images.

All of the above ship with binder built in.

---

## Phase B — KVM (hardware acceleration)

Without KVM, redroid runs in software emulation — it'll boot but usable for
~2 phones max. With KVM you get 10–20 phones on a decent host.

### Step 1: Check `/dev/kvm`

```bash
ls /dev/kvm
# Expect: /dev/kvm

# If "No such file or directory" → your VM doesn't have virt accel exposed
# → see "Enabling nested virt on cloud VMs" below.
```

### Step 2: Install tools + group membership

```bash
sudo apt-get install -y qemu-kvm libvirt-daemon-system cpu-checker
sudo kvm-ok
# Expect: "KVM acceleration can be used"

sudo usermod -aG kvm,libvirt $USER
# Log out + back in, OR use `newgrp kvm` to refresh your current shell

ls -l /dev/kvm
# Expect: crw-rw---- 1 root kvm ...
```

### Enabling nested virt on cloud VMs

You have to do this **at VM creation time** — you cannot retrofit it.

**GCP:**
```bash
gcloud compute instances create droidfarm-linux \
  --zone=us-central1-a \
  --machine-type=n2-standard-8 \
  --enable-nested-virtualization \
  --min-cpu-platform="Intel Cascade Lake" \
  --image-family=ubuntu-2404-lts-amd64 \
  --image-project=ubuntu-os-cloud \
  --boot-disk-size=200GB
```

**AWS:** nested-KVM isn't supported on standard EC2 virtualized instances.
Use a `.metal` or `c5n.metal` instance type if you need it.

**Azure:** most D-series v3 and newer SKUs have nested virt enabled by
default. No flag needed, but confirm with `cat /proc/cpuinfo | grep vmx` on
the VM.

---

## Phase C — Docker + redroid

### Install Docker

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
newgrp docker
docker --version
```

### Pull and boot a redroid container

```bash
# Pull the image (Android 13 64-bit only — stable, smallest)
docker pull redroid/redroid:13.0.0_64only-latest

# Data dir for persistence across restarts
mkdir -p ~/redroid-data

# Boot one phone
docker run -itd --rm --privileged \
  -v ~/redroid-data:/data \
  -p 5555:5555 \
  --name redroid-01 \
  redroid/redroid:13.0.0_64only-latest

# Wait ~30s for first boot, then:
sudo apt-get install -y adb
adb connect localhost:5555
adb devices
# Expect: localhost:5555    device

adb shell getprop ro.build.version.release
# Expect: 13
```

If `adb devices` shows the device as `offline` or the container exits
immediately, run `docker logs redroid-01` — 99% of the time it'll point at:

- **Binder missing** → back to phase A.
- **KVM missing** → it'll still boot but take ~3min and be slow; fix in phase B.
- **Permission denied on /dev/kvm** → `sudo usermod -aG kvm $USER && newgrp kvm`.

---

## Phase D — Wire redroid into DroidFarm

The DroidFarm code already has the driver abstraction and a docker-compose
`redroid` profile stub. To actually use it:

1. Implement `backend/droidfarm/core/drivers_redroid.py` subclassing `Driver`
   (see [ARCHITECTURE.md §6](ARCHITECTURE.md#6-the-driver-layer-backenddroidfarmcoredriverpy)).
2. Register it in `backend/droidfarm/config.py`'s `get_driver()` factory so
   it auto-selects when `/dev/binderfs/binder-control` exists.
3. `docker compose --profile redroid up` will bring up DroidFarm + an initial
   redroid container; the driver then launches more containers per phone via
   `docker run` calls matching the LDPlayer lifecycle.

At time of writing this guide, steps 1 and 2 are **not yet shipped** — the
repo has a scaffold but not a working driver. Ask the maintainer (or file an
issue) when you want it wired up; the abstraction is already in place, so it's
~1 day of implementation + testing.

---

## Automated bootstrap

For a fresh Ubuntu 22.04/24.04 VM with the `-generic` kernel, the script at
[`scripts/setup-linux-kernel.sh`](../scripts/setup-linux-kernel.sh) runs
phases A + B + C end-to-end. Usage:

```bash
sudo ./scripts/setup-linux-kernel.sh
```

It's idempotent — running it twice is safe. It will:

1. Verify the kernel has binderfs built in (aborts with instructions if not).
2. Mount binderfs + persist to `/etc/fstab`.
3. Install qemu-kvm, verify `/dev/kvm`, add `$USER` to `kvm` group.
4. Install Docker if missing, add `$USER` to `docker` group.
5. Pull the redroid image and do a quick smoke-boot to confirm everything
   works, then tear it down.

---

## Verification checklist

After setup is done, these should all pass:

```bash
# Phase A
grep binder /proc/filesystems                       # nodev   binder
ls /dev/binderfs                                    # binder-control

# Phase B
ls /dev/kvm                                         # /dev/kvm
sudo kvm-ok                                         # "KVM acceleration can be used"

# Phase C
docker --version                                    # Docker version 27.x
docker pull redroid/redroid:13.0.0_64only-latest    # image pulled

# Smoke boot
docker run --rm -itd --privileged -p 5555:5555 --name smoke \
  redroid/redroid:13.0.0_64only-latest
sleep 45
adb connect localhost:5555
adb shell getprop ro.build.version.release          # 13
docker stop smoke
```

If all four pass you're ready for DroidFarm with real Android.

---

## Troubleshooting

| Symptom                                              | Cause                                                  | Fix                                         |
|------------------------------------------------------|--------------------------------------------------------|---------------------------------------------|
| `grep binder /proc/filesystems` is empty             | Kernel has no binder support                           | Phase A2 (DKMS or newer kernel)             |
| `mount: unknown filesystem type 'binder'`            | Same as above                                          | Same as above                               |
| `make: /lib/modules/.../build: No such file`         | Missing kernel headers                                 | `sudo apt install linux-headers-$(uname -r)` |
| `modpost: kallsyms_lookup_name undefined`            | Building old redroid-modules against kernel ≥ 5.7      | Use anbox-modules instead (phase A2, opt 1) |
| `ls /dev/kvm` → no such file                         | Nested virt off at VM-creation                         | Recreate VM with `--enable-nested-virtualization` |
| adb says `device offline`                            | redroid still booting                                  | `sleep 30 && adb reconnect offline`         |
| redroid container exits immediately                  | See `docker logs <name>`                               | Usually points at binder or privileged flag |
| redroid slow (~3 min boot, lag after)                | Running without KVM                                    | Phase B                                     |
| `adb: command not found`                             | Not installed                                          | `sudo apt install adb`                      |

---

*Tested paths: Ubuntu 22.04 + 5.15.0-generic, Ubuntu 24.04 + 6.8.0-generic,
both with GCP `--enable-nested-virtualization`. Custom/stripped kernels (CI
containers, GKE nodes, Fly.io VMs) will NOT work — binder is a kernel
primitive and has no userspace equivalent.*
