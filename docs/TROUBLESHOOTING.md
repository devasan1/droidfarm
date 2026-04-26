# Troubleshooting

Errors / symptoms indexed by what you see. If you don't find your problem
here, check the backend log (`%APPDATA%\DroidFarm\logs\` on Windows,
`~/.droidfarm/logs/` on Mac/Linux) and search GitHub issues.

## General

### The sidebar pill says "Driver: Mock" but I installed LDPlayer / Android SDK

- **Windows:** `ldconsole.exe` must be under `C:\`, `D:\`, or `E:\` in one
  of the standard install paths. If yours is elsewhere (e.g. a custom
  F-drive path), set `DROIDFARM_LDCONSOLE=F:\path\to\ldconsole.exe` before
  launching.
- **Mac:** the Android SDK must be at `~/Library/Android/sdk` with both
  `platform-tools/adb` **and** `cmdline-tools/latest/bin/avdmanager` and
  `emulator/emulator` present. Verify:

  ```bash
  ls ~/Library/Android/sdk/platform-tools/adb \
     ~/Library/Android/sdk/cmdline-tools/latest/bin/avdmanager \
     ~/Library/Android/sdk/emulator/emulator
  ```

  If any are missing, re-run `mac/setup.sh`. If all three exist but DroidFarm
  still uses mock, force the path: `DROIDFARM_ANDROID_SDK=$HOME/Library/Android/sdk mac/droidfarm.command`.
- **Linux:** same as Mac but under `~/Android/Sdk`.
- Check `/api/health` to see what DroidFarm detected:

  ```bash
  curl -s http://127.0.0.1:7870/api/health | python -m json.tool
  ```

### "Error: current driver does not surface adb" in the phone viewer

You're on the mock driver. This isn't a bug — the mock driver doesn't have
a real adb to surface. Install LDPlayer (Windows) or the Android SDK (Mac /
Linux) to get real phones. See the section above.

### Port 7870 already in use

```bash
DROIDFARM_PORT=8000 mac/droidfarm.command       # Mac
set DROIDFARM_PORT=8000 & DroidFarm.bat         # Windows
```

### First launch window is white

If you're running the Tauri MSI on Windows, the first-run venv provisioning
takes 30–60 seconds. The splash screen should show a spinner and status
text. If you see a plain white window instead, the frontend bundle is
missing — re-install from a fresh `.msi` built off the latest main.

### Add-phone returns 500 with `RuntimeError: ... failed`

Check the backend log for the exact tool invocation. Most common:

- **LDPlayer `add`/`copy` returns exit code 3** — this is actually success
  on some LDPlayer 9 builds. The current driver tolerates this (verifies
  via `list2`); if you're on an older build, pull latest.
- **`avdmanager create avd` fails with "Package path is not valid"** — the
  system image isn't installed. Run:

  ```bash
  sdkmanager "system-images;android-34;google_apis;arm64-v8a"
  ```

## Windows / LDPlayer

### `ldconsole.exe` returns nothing / fails silently

LDPlayer's Multi-Instance Manager has to be initialized at least once.
Open `dnplayer.exe` via the Start menu, let the main window load fully,
close it, then retry.

### Hyper-V conflicts

If LDPlayer fails to boot emulators with "VT-x not available":

1. Enable VT-x / SVM in BIOS.
2. `bcdedit /set hypervisorlaunchtype off` (disables Hyper-V; reboot).
3. Or: switch LDPlayer to "Compatible" engine mode (Settings → Engine).

Can't run LDPlayer alongside WSL2 in some configs — disable one.

### SmartScreen blocks the MSI

Click "More info → Run anyway". The MSI is unsigned (open-source project).
If your org policy blocks unsigned installers, build the MSI yourself:
`cd src-tauri && cargo tauri build`.

## macOS / Android Emulator

### `xcode-select --install` dialog doesn't appear

It may be hidden behind another window (Cmd+Tab to find it) or suppressed
by a previous install attempt. Force it:

```bash
sudo xcode-select --reset
xcode-select --install
```

If it says "already installed" but you don't actually have it, the
`/Library/Developer/CommandLineTools` directory may be partial — delete it
with `sudo rm -rf /Library/Developer/CommandLineTools` and re-install.

### Homebrew install asks for sudo and stalls

The first Homebrew install downloads ~500 MB. Let it finish. If it's truly
stalled (>10 min with no progress), cancel with Ctrl-C and re-run
`mac/setup.sh` — the Homebrew install step is idempotent.

### `sdkmanager` complains about Java

```
ERROR: JAVA_HOME is not set and no 'java' command could be found in your PATH.
```

Export JAVA_HOME before re-running:

```bash
export JAVA_HOME="$(/usr/libexec/java_home -v 17)"
export PATH="$JAVA_HOME/bin:$PATH"
bash mac/setup.sh
```

### Emulator fails with "PANIC: Cannot find AVD system path"

The system image wasn't downloaded. Run:

```bash
~/Library/Android/sdk/cmdline-tools/latest/bin/sdkmanager \
  "system-images;android-34;google_apis;arm64-v8a"
```

(Substitute `x86_64` on Intel Macs.)

### Emulator fails with "HVF error" or "KVM is not available"

On Apple Silicon, the emulator binary must be arm64. Check:

```bash
file ~/Library/Android/sdk/emulator/emulator
# Expected: Mach-O 64-bit executable arm64
```

If it's x86_64, your SDK install is wrong. Purge and re-install:

```bash
mac/uninstall.sh --all
mac/setup.sh
```

### Phone boots but is very slow

- Confirm HVF is actually being used — the emulator log (`~/.android/`)
  should say "HVF is supported". If it falls back to software, you either
  got the wrong arch system image or the machine is out of RAM.
- Check Activity Monitor for swap usage; at >5 GB swap, reduce concurrent
  phones.

### `npm install` fails with EACCES

Don't run with `sudo`. If your npm cache got root-owned at some point:

```bash
sudo chown -R $(id -u):$(id -g) ~/.npm
```

### Phone's proxy isn't picked up

macOS Google emulator supports `-http-proxy` but the backend starts the
emulator via a different path in some versions. Verify the phone config
persisted:

```bash
grep -E '^proxy' ~/.android/avd/<phone>.avd/config.ini
```

If absent, the proxy was assigned but not written — report a bug.

## Linux

### `/dev/kvm` doesn't exist

Your CPU doesn't have VT-x / AMD-V enabled, or you're on a host without
hardware virt. Cloud VMs usually fall in the latter category — see
[`docs/DEPLOYMENT.md`](DEPLOYMENT.md). On GCE specifically you need
`--enable-nested-virtualization` at create time; see
[`docs/gcp-setup.md`](gcp-setup.md).

### `/dev/kvm` permission denied / `PermissionError: [Errno 13] ... '/dev/kvm'`

Missing `kvm` group membership, **or** the backend process was started
in a shell that pre-dated the group add. New group memberships only
apply to new login sessions:

```bash
sudo usermod -aG kvm,libvirt $USER
# stop the backend, fully exit SSH, reconnect, restart the backend
pkill -f 'uvicorn droidfarm.main:app'
exit          # then SSH back in
# verify before restarting:
id -nG | tr ' ' '\n' | grep -E '^kvm$'   # must print 'kvm'
# verify the backend's view (after it's running):
cat /proc/$(pgrep -f 'uvicorn droidfarm.main:app')/status | grep -i Groups
```

The Groups line must contain `109` (Ubuntu `kvm` GID) and ideally `124`
(`libvirt`). A single-number line means the backend has zero
supplementary groups and can't open `/dev/kvm`.

### `sdkmanager` / `avdmanager` errors with `JAVA_HOME is not set`

The Android command-line tools are JDK applications. On a fresh Linux
VM (or after a minimal install), JDK 17 isn't there:

```bash
sudo apt-get install -y openjdk-17-jdk-headless
export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
export PATH="$JAVA_HOME/bin:$PATH"
```

`scripts/gcp-launch.sh` (latest) installs this for you. If you ran an
older version of the script, `git pull` and re-run.

### `avdmanager create avd` fails with `Package path is not valid. Valid system image paths are: ...`

The driver default and your installed system image disagree on which
Android version to use. Either install the image the driver wants
(default `system-images;android-34;google_apis;x86_64`) or pin the
driver to whatever you have installed:

```bash
# install the missing image (recommended)
sdkmanager --install "system-images;android-34;google_apis;x86_64"

# or pin the driver (no extra download, restart backend)
DROIDFARM_ANDROID_SYSTEM_IMAGE='system-images;android-33;google_apis;x86_64' \
  ./droidfarm.sh
```

### Emulator exits immediately with "Failed to open /dev/goldfish-pipe"

Kernel module missing. On most distros this is part of the `linux-image-*`
package — should be present on Ubuntu 22.04+, Debian 12+. On a minimal
kernel you may need to enable `CONFIG_ANDROID` flags; easier to use a
stock distro kernel.

### Emulator boots but the UI is laggy / `System UI isn't responding` ANR

Click **Wait** on the ANR. You're either on a nested-virt cloud VM
(expected; see [`docs/gcp-setup.md`](gcp-setup.md) section A2.6) or the
emulator silently fell back to TCG (no KVM acceleration). Confirm
with:

```bash
emulator -avd <any-avd> -no-window -no-audio -verbose 2>&1 | head -30 | grep -i -E 'kvm|tcg'
# want: 'KVM accelerator detected'
# bad:  'TCG enabled' or 'cpu: tcg'
```

If TCG, fix `/dev/kvm` group membership (above). If KVM is detected,
the lag is the screencap-polling baseline (~1–2 s) plus first-15-min
Android warmup; bump phone resources to 4 vCPU / 4096 MB RAM in the
**Add phone** dialog and wait for warmup.

## GCP / AWS / Cloud VMs

Full cloud-specific guide: [`docs/gcp-setup.md`](gcp-setup.md). Below
are quick pointers — the GCP doc has copy-pasteable fixes for each
symptom.

### `gcp-launch.sh` aborts with "nested virtualization is required"

The VM was created without `--enable-nested-virtualization` or with an
unsupported machine type. Delete and re-create with the script.
[Details](gcp-setup.md#a5-troubleshooting-linux--gce).

### `gcp-tunnel.sh` errors with `permission denied (publickey)`

`gcloud auth login` and verify your account has
`roles/iap.tunnelResourceAccessor` on the project.

### Phone-create succeeds but phone-start fails with `/dev/kvm` permission denied

Your `kvm` group membership didn't propagate to the backend process.
See [Linux → `/dev/kvm` permission denied](#devkvm-permission-denied--permissionerror-errno-13--devkvm) above.

### `git checkout devin/<branch>` returns `pathspec did not match any file(s) known to git`

The clone is shallow (older `gcp-launch.sh` used `--depth 1`). Either
fetch the specific branch:

```bash
git fetch origin <branch>:<branch>
git checkout <branch>
```

or un-shallow:

```bash
git fetch --unshallow
git checkout <branch>
```

### Phones boot but run at 2 fps

Likely TCG fallback (no KVM acceleration). Check
[Linux → emulator boots but UI is laggy](#emulator-boots-but-the-ui-is-laggy--system-ui-isnt-responding-anr).
If KVM *is* engaged and you still need more speed, the nested-virt
overhead floors you at ~30–50% of bare metal regardless of machine
type — see [`docs/gcp-setup.md`](gcp-setup.md#a6-when-to-leave-the-cloud-bare-metal).

### "This machine type does not support nested virtualization"

Use N1, N2, C2, C3 (Intel) or N2D / C2D (AMD with `--threads-per-core=1`)
on GCP. Not all zones support every family —
`gcloud compute machine-types list --zones=<zone>`. Same concept
applies to Azure (Dsv3+) and AWS (only `.metal`).

### Windows-on-GCP: VM console shows black screen

See [`docs/gcp-setup.md`](gcp-setup.md) Path B. Usual fixes:
Ctrl+Alt+End for lock screen, restart VM, re-set the Windows password
from the GCP console.

## Database / state

### "database is locked" in the logs

SQLite can't handle extreme concurrency. You probably have two DroidFarm
instances pointing at the same `DROIDFARM_DATA_DIR`. Close one. If it's a
crashed process holding a WAL lock, delete
`$DROIDFARM_DATA_DIR/droidfarm.sqlite-wal` and restart.

### I want to wipe everything and start over

**Mac / Linux:**
```bash
mac/uninstall.sh --all   # nukes DroidFarm + SDK + AVDs
```

**Windows:**
Uninstall via Add/Remove Programs, then delete `%APPDATA%\DroidFarm` and
optionally LDPlayer.

## Reporting bugs

When opening a GitHub issue, please include:

- Platform (Windows / Mac arch / Linux distro).
- Output of `curl -s http://127.0.0.1:7870/api/health | python -m json.tool`.
- The last ~100 lines of the backend log.
- What you did immediately before the failure.
- A minimal repro if possible.
