# DroidFarm on Linux

The primary target is Windows + LDPlayer 9, but DroidFarm's backend +
frontend + scheduler all run natively on Linux and macOS. You can use it
two ways:

1. **Native bash launcher** — `./droidfarm.sh` (Ubuntu / Debian / Fedora /
   Arch / macOS with Homebrew). Same idea as the Windows `.bat`: auto-
   installs Python 3.11+, Node 20+, and (best-effort) adb, then boots the
   backend and opens http://localhost:7870.
2. **Docker / docker-compose** — `docker compose up`. A single image that
   bundles the backend and the pre-built React frontend. Data is
   persisted in a named volume.

## 1. Native bash launcher

```bash
git clone https://github.com/devasan1/droidfarm.git
cd droidfarm
./droidfarm.sh
```

First run takes 1–3 minutes (installs Python / Node / adb if missing,
creates the venv, builds the frontend). Subsequent runs boot in ~3 s.

Environment variables:

| Variable | Default | Effect |
|---|---|---|
| `DROIDFARM_PORT` | `7870` | HTTP port |
| `DROIDFARM_HOST` | `127.0.0.1` | Bind address (use `0.0.0.0` to expose on LAN) |
| `DROIDFARM_DATA_DIR` | `~/.droidfarm` | Where the SQLite DB + APKs + templates live |
| `DROIDFARM_ANDROID_SYSTEM_IMAGE` | `system-images;android-34;google_apis;x86_64` | Pin the system image used by the AndroidEmulatorDriver. Set this if you can't or don't want to install android-34. |
| `DROIDFARM_MOCK` | auto | Force mock driver (`1` / `0`) |

### Bare-Linux requirements for the AndroidEmulatorDriver

`droidfarm.sh` itself doesn't install KVM, the JDK, or the Android SDK
— it expects a working host. On a fresh Linux box (Ubuntu 22.04+ /
Debian 12+) the minimum is:

```bash
# 1. virtualization
sudo apt-get install -y qemu-kvm libvirt-daemon-system cpu-checker
sudo usermod -aG kvm,libvirt "$USER"
# !! log out and log back in for the group change to apply !!

# 2. JDK 17 (sdkmanager / avdmanager are JDK apps)
sudo apt-get install -y openjdk-17-jdk-headless
export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
export PATH="$JAVA_HOME/bin:$PATH"

# 3. Android SDK (cmdline-tools + platform-tools + emulator + a system image)
mkdir -p ~/Android/Sdk/cmdline-tools
cd /tmp
curl -fsSL https://dl.google.com/android/repository/commandlinetools-linux-11076708_latest.zip -o cmd.zip
unzip -q cmd.zip
mv cmdline-tools ~/Android/Sdk/cmdline-tools/latest

export ANDROID_SDK_ROOT="$HOME/Android/Sdk"
export ANDROID_HOME="$ANDROID_SDK_ROOT"
export PATH="$ANDROID_SDK_ROOT/cmdline-tools/latest/bin:$ANDROID_SDK_ROOT/platform-tools:$ANDROID_SDK_ROOT/emulator:$PATH"

yes | sdkmanager --licenses >/dev/null
sdkmanager --install \
  "platform-tools" \
  "emulator" \
  "platforms;android-34" \
  "system-images;android-34;google_apis;x86_64"
```

Then `./droidfarm.sh` should detect a real driver (not mock). Verify:

```bash
curl -s http://127.0.0.1:7870/api/health | python3 -m json.tool
# look for: "driver": {"name": "android-emulator", ...}
```

> If the sidebar pill in the UI says **Driver: Mock** despite the SDK
> being installed, one of the three binaries is missing or not on
> `PATH` for the backend process. The detector looks for
> `cmdline-tools/latest/bin/avdmanager`, `platform-tools/adb`, and
> `emulator/emulator` under `$ANDROID_SDK_ROOT`. Check
> [`docs/TROUBLESHOOTING.md`](TROUBLESHOOTING.md#the-sidebar-pill-says-driver-mock-but-i-installed-ldplayer--android-sdk).

For the GCP-specific one-shot version of all of this (plus nested-virt
VM creation and the SSH tunnel), see
[`docs/gcp-setup.md`](gcp-setup.md). For other cloud / bare-metal
hosts, see [`docs/DEPLOYMENT.md`](DEPLOYMENT.md).

## 2. Docker

```bash
docker compose up --build
```

Then open http://localhost:7870. Stop with `Ctrl+C`.

By default the host port is bound to `127.0.0.1` only — DroidFarm has
no auth yet and exposes adb-shell + scheduling, so it isn't safe to
publish publicly. To deliberately expose it on your LAN:

```bash
DROIDFARM_BIND_HOST=0.0.0.0 docker compose up --build
# on the host:  open http://<your-ip>:7870 from another machine
```

For cloud setups, see [docs/gcp-setup.md](gcp-setup.md) — the
recommended pattern is to keep DroidFarm bound to `127.0.0.1` on the
cloud VM and reach it from your laptop via an SSH local-port-forward
(no public exposure, no firewall rules, no auth needed yet).

## Driving real Android instances from Linux

LDPlayer is Windows-only, so on Linux you have three options:

### a) Run DroidFarm on Linux but aim it at a remote Windows LDPlayer

Point DroidFarm's adb / ldconsole envs at a Windows box over the network.
Not officially supported yet — let us know if you want this and we can
add a `DROIDFARM_LDCONSOLE_REMOTE` mode.

### b) Run DroidFarm in mock-driver mode (default)

All UI flows work — adding phones, assigning proxies, the proxy importer,
geoIP lookups, the Trash / restore flow, etc. Phones are simulated: each
"phone" returns a tinted flat PNG as its screenshot. Good for development
and demos, obviously not useful for actual app farming.

### c) **redroid** (Docker Android containers) — Linux-only, x86/ARM64

[redroid](https://github.com/remote-android/redroid-doc) runs stock
Android in a container, using the host kernel's binder + ashmem. It
scales to many instances (each ~800 MB RAM) and exposes adb on a chosen
port, which means DroidFarm can manage it the same way it manages
LDPlayer.

Quick start with the bundled compose profile:

```bash
# prerequisites (ubuntu)
sudo apt install linux-modules-extra-$(uname -r)
sudo modprobe binder_linux
sudo modprobe ashmem_linux

# boot droidfarm + one redroid phone
docker compose --profile redroid up
```

The redroid driver is not yet wired up (tracked separately). Once it
lands, the DroidFarm UI will show the redroid phones just like LDPlayer
phones — same proxy pool, same geo-spoof, same APK drag-drop.

## Caveats on Linux

- **Nested virtualization**: redroid doesn't need it; it uses containers.
  LDPlayer (Windows) does. If you're on a cloud VM, pick a machine type
  that supports it.
- **Hardware fingerprint apply**: on redroid (rooted), the same setprop
  path as LDPlayer works. On stock AOSP / Waydroid, read-only sysprops
  silently reject the setprop call and the IMEI / Android ID / MAC
  overrides won't apply. The fingerprint is still stored in the DB for
  future driver upgrades.
