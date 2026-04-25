# DroidFarm on macOS

A-Z guide for running **DroidFarm** on a brand-new Mac. Targets Apple Silicon
(M1 / M2 / M3 / M4) but works on Intel Macs too.

This folder is **self-contained** for the Mac platform — `setup.sh` installs
everything you need from scratch, `droidfarm.command` launches the app,
`uninstall.sh` cleans up. The shared Python / TypeScript code lives in
`../backend` and `../frontend`; you don't need to touch them.

**See also:**

- [`../docs/PLATFORMS.md`](../docs/PLATFORMS.md) — feature parity matrix
  for the Mac driver vs. Windows / Linux.
- [`../docs/DEPLOYMENT.md`](../docs/DEPLOYMENT.md) — how Mac compares to
  Hetzner / cloud hosts.
- [`../docs/TROUBLESHOOTING.md`](../docs/TROUBLESHOOTING.md) — more Mac
  troubleshooting beyond what's in this file.
- [`../docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md) §6 — how
  `AndroidEmulatorDriver` fits in.

---

## What you get

| Component            | macOS                                                      |
| -------------------- | ---------------------------------------------------------- |
| Driver               | `AndroidEmulatorDriver` — Google's stock emulator          |
| System image         | `system-images;android-34;google_apis;arm64-v8a` (M-series) |
| Hardware accel       | HVF (Hypervisor Framework, native, no extra config)        |
| Per-phone speed      | ~60 fps on Apple Silicon, comparable to a real phone       |
| Recommended phones   | 4 phones on 16GB RAM, 8 phones on 32GB                     |
| Per-AVD disk         | ~6 GB                                                      |

Geo-spoof, locale, timezone, IMEI, Android ID, per-phone HTTP proxy and
GPS fix all work the same way as the LDPlayer driver does on Windows.
Build-prop spoofing (manufacturer / model strings) requires `-writable-system`
and is best-effort — see [Limitations](#limitations) below.

---

## TL;DR

```bash
# 1. Clone the repo
git clone https://github.com/devasan1/droidfarm.git
cd droidfarm

# 2. Run the one-shot installer
bash mac/setup.sh

# 3. Launch DroidFarm
mac/droidfarm.command       # or double-click in Finder
```

The browser opens at `http://127.0.0.1:7870`. Add a phone, watch it boot.

---

## Prerequisites

Just a Mac running macOS 13 (Ventura) or newer.

You do **not** need to install anything yourself before running `setup.sh` —
the script bootstraps Xcode CLT, Homebrew, Java, Python, Node, and the Android
SDK in that order. If any of those are already installed it skips them.

What you **do** need:

- **Admin password.** Homebrew install and the Java symlink step both prompt
  for sudo. The script will pause and let you type your password.
- **~15 GB free disk.** Android SDK + cmdline-tools + system image + factory
  AVD + venv + node_modules add up.
- **Stable network for ~10 minutes.** Homebrew + 1.4 GB Android system image
  + ~50 MB of pip wheels + ~30 MB of npm.

---

## Step-by-step (what `setup.sh` does)

If you'd rather do this manually, here's the same thing broken out. The
script just automates and idempotents all of these.

### 1. Xcode Command Line Tools

```bash
xcode-select --install
```

A system dialog pops up. Click **Install** (not "Get Xcode"). Wait ~5 min.

Verify:

```bash
xcode-select -p
# /Library/Developer/CommandLineTools
```

### 2. Homebrew

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# After install, add to PATH:
echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile
eval "$(/opt/homebrew/bin/brew shellenv)"
```

Verify: `brew --version`.

### 3. OpenJDK 17

`avdmanager` and `sdkmanager` are Java programs and need a JDK on PATH.

```bash
brew install openjdk@17
sudo ln -sfn /opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk \
             /Library/Java/JavaVirtualMachines/openjdk-17.jdk
```

Verify: `/usr/libexec/java_home -v 17`.

### 4. Python 3.11

```bash
brew install python@3.11
```

Verify: `python3.11 --version` → `Python 3.11.x`.

### 5. Node.js 20

The frontend build needs Node 18+; we pin Node 20 LTS.

```bash
brew install node@20
brew link --overwrite --force node@20
```

Verify: `node -v` → `v20.x.x`, `npm -v`.

### 6. Android SDK

We download the **command-line tools only** (no Android Studio IDE — you don't
need it). The cmdline-tools then download `platform-tools`, `emulator`, and
the Android 34 system image.

```bash
mkdir -p ~/Library/Android/sdk/cmdline-tools
cd /tmp
curl -O https://dl.google.com/android/repository/commandlinetools-mac-11076708_latest.zip
unzip commandlinetools-mac-11076708_latest.zip
mv cmdline-tools ~/Library/Android/sdk/cmdline-tools/latest

export ANDROID_SDK_ROOT="$HOME/Library/Android/sdk"
export PATH="$ANDROID_SDK_ROOT/cmdline-tools/latest/bin:$ANDROID_SDK_ROOT/platform-tools:$ANDROID_SDK_ROOT/emulator:$PATH"

# Accept all licenses non-interactively
yes | sdkmanager --licenses

# Install runtime + system image
sdkmanager \
  "platform-tools" \
  "emulator" \
  "platforms;android-34" \
  "system-images;android-34;google_apis;arm64-v8a"  # use x86_64 on Intel
```

Verify:

```bash
which adb emulator avdmanager
adb --version
emulator -list-avds
```

### 7. Factory template AVD

DroidFarm clones every new phone from a hidden template called
`_droidfarm_template_factory`. We create it once.

```bash
echo "no" | avdmanager --silent create avd \
  -n _droidfarm_template_factory \
  -k "system-images;android-34;google_apis;arm64-v8a" \
  --abi arm64-v8a \
  --device "pixel_6" \
  --force
```

Verify: `avdmanager list avd | grep _droidfarm`.

### 8. DroidFarm Python venv

```bash
python3.11 -m venv ~/.droidfarm/venv
source ~/.droidfarm/venv/bin/activate
pip install --upgrade pip
pip install -e ./backend
```

### 9. Frontend build

```bash
cd frontend
npm install
npm run build
```

That's it. The repo is now ready to run.

---

## Launch

```bash
mac/droidfarm.command
```

Or double-click `droidfarm.command` in Finder.

The launcher will:

1. Re-run `setup.sh` if anything is missing (idempotent).
2. Activate the venv at `~/.droidfarm/venv`.
3. Start FastAPI on `http://127.0.0.1:7870`.
4. Open that URL in your default browser.

The browser shows the DroidFarm UI. Click **Add phone**, give it a name, and
watch it boot in the running emulator. The emulator runs **headless** — you
don't see a separate window, only the live screen tiles in the DroidFarm UI.

---

## Adding more phones

Each phone takes ~2GB of RAM at runtime + ~6GB of disk on creation.

| RAM   | Phones (light apps) | Phones (heavy / Chrome) |
| ----- | ------------------- | ----------------------- |
| 8 GB  | 2                   | 1                       |
| 16 GB | 4                   | 3                       |
| 24 GB | 6                   | 4                       |
| 32 GB | 8                   | 6                       |
| 64 GB | 16+                 | 10+                     |

Your **M4 Mac Mini 16GB** comfortably runs 4 phones. Bumping past that risks
swap thrashing — watch the swap usage in Activity Monitor.

---

## Geo-spoofing

Set per-phone country / timezone / GPS in the DroidFarm UI under each phone's
**Geo** tab. The driver applies them to the running emulator via:

| Setting    | Mechanism                                                       |
| ---------- | --------------------------------------------------------------- |
| GPS fix    | `adb -s emulator-NNNN emu geo fix <lon> <lat>`                  |
| Locale     | `adb shell setprop persist.sys.locale en-US`                    |
| Timezone   | `adb shell setprop persist.sys.timezone America/New_York`       |
| IMEI       | `~/.android/avd/<name>.avd/config.ini` `hw.gsmModem.imei=`      |
| Android ID | `adb shell settings put secure android_id <hex>`                |
| HTTP proxy | `emulator -http-proxy <host>:<port>` at boot                    |

Apps consuming Fused Location / Google Play Services pick up the GPS fix
without needing a separate mock-location app.

For traffic-routing through SOCKS proxies (not just system HTTP), DroidFarm
uses the same tun2socks sidecar pattern as on Windows — install via
`brew install go-tun2socks` if you need it.

---

## Updating

```bash
cd ~/path/to/droidfarm
git pull
mac/setup.sh         # idempotent — re-installs only what changed
```

If `mac/setup.sh` says everything is already up to date, just relaunch via
`mac/droidfarm.command`.

---

## Uninstall

```bash
mac/uninstall.sh           # remove DroidFarm venv + factory AVD only
mac/uninstall.sh --all     # also delete the entire Android SDK + every AVD
```

What this **does not** remove (because you may want them for other things):

- Homebrew itself
- Java / Python / Node installed via brew
- Xcode Command Line Tools

To remove those too, follow the standard uninstall procedure for each — e.g.
`brew uninstall openjdk@17 python@3.11 node@20`.

---

## Troubleshooting

### `bash setup.sh` fails on `xcode-select --install`

The system dialog might be stuck behind another window. Bring it forward
manually (Cmd+Tab) and click Install. Then re-run `setup.sh`.

### `sdkmanager` complains about Java

```
ERROR: JAVA_HOME is not set and no 'java' command could be found in your PATH.
```

Fix:

```bash
export JAVA_HOME="$(/usr/libexec/java_home -v 17)"
export PATH="$JAVA_HOME/bin:$PATH"
```

Then re-run `setup.sh`.

### Emulator fails to start with "PANIC: Cannot find AVD system path"

The system image hasn't been downloaded.

```bash
sdkmanager "system-images;android-34;google_apis;arm64-v8a"
```

### Port 7870 already in use

Set a different port before launching:

```bash
DROIDFARM_PORT=8000 mac/droidfarm.command
```

### Phone boots but the UI shows "current driver does not surface adb"

That means DroidFarm is using the mock driver — meaning the Android SDK
auto-detection failed. Check:

```bash
ls ~/Library/Android/sdk/platform-tools/adb
ls ~/Library/Android/sdk/cmdline-tools/latest/bin/avdmanager
ls ~/Library/Android/sdk/emulator/emulator
```

All three must exist. If any are missing, re-run `setup.sh`. If they exist
but DroidFarm still uses mock, force the path:

```bash
DROIDFARM_ANDROID_SDK="$HOME/Library/Android/sdk" mac/droidfarm.command
```

### `npm install` fails with EACCES

Don't run with `sudo`. If your npm cache got root-owned at some point:

```bash
sudo chown -R $(id -u):$(id -g) ~/.npm
```

### Emulator says `KVM is not available` (Linux-only message — should never appear on Mac)

Means the binary is x86 but you're on M-series. Confirm:

```bash
file ~/Library/Android/sdk/emulator/emulator
# Should say "Mach-O 64-bit executable arm64" on Apple Silicon
```

If it says `x86_64`, your SDK install picked up the wrong arch. Re-run
`mac/uninstall.sh && mac/setup.sh`.

### Browser opens but UI is blank / shows JSON

Means `frontend/dist` wasn't built. Run:

```bash
cd frontend && npm install && npm run build
```

### "First launch is taking forever"

The first emulator boot can take 60–90 seconds (Android cold-boots, sets up
storage, runs the setup wizard). Subsequent launches use snapshots and are
~10 seconds.

---

## Limitations

| Capability                              | Status on Mac driver                                                   |
| --------------------------------------- | ---------------------------------------------------------------------- |
| GPS fix                                 | Full                                                                   |
| Locale / timezone                       | Full                                                                   |
| IMEI                                    | Full (via `config.ini`)                                                |
| Android ID                              | Full (via `adb`)                                                       |
| HTTP proxy per phone                    | Full (via `emulator -http-proxy`)                                      |
| SOCKS proxy / tun2socks routing         | Works with `go-tun2socks` sidecar, same as Windows                     |
| Manufacturer / model spoof              | Best-effort (requires `-writable-system` + remount, slower boot)       |
| `.ldbk` import / export                 | N/A — Mac driver doesn't speak LDPlayer's backup format                |
| ARM64 apps (native, fast)               | Full                                                                   |
| x86-only apps                           | Run on `x86_64` system image; ~5x slower than arm64 on M-series        |
| Apps with strong root/Hyper-V detection | Same level as LDPlayer (Google emulator is also a hypervisor; detected by SafetyNet) |

---

## Files in this folder

| File              | Purpose                                                       |
| ----------------- | ------------------------------------------------------------- |
| `README.md`       | This file                                                     |
| `setup.sh`        | One-shot installer (idempotent)                               |
| `droidfarm.command` | Double-clickable launcher (Mac equivalent of `DroidFarm.bat`) |
| `uninstall.sh`    | Cleanup script                                                |

---

## Why no Tauri / .app bundle?

We could ship DroidFarm as a signed `.app` bundle via `cargo tauri build`,
but that requires an Apple Developer account ($99/yr) for code signing or
users have to right-click → Open every time. The launcher approach (clone +
script) avoids that, runs the same code as the Windows MSI build, and is
auditable end-to-end.

If you want the .app build later, the `src-tauri/` config already targets
macOS — `cargo tauri build --bundles dmg` will produce one. You'll just need
to handle Gatekeeper / notarization yourself.
