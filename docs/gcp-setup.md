# Running DroidFarm on GCP

DroidFarm runs Android emulators on top of Intel VT-x / AMD-V. Because GCE
VMs sit *inside* the GCE hypervisor, the VM must be created with **nested
virtualization explicitly enabled**, on an Intel-family machine type
(N1 / N2 / C2 / C3). Without that, every phone boot fails with "VT-x is
not available" / "Unable to start VM".

There are two supported paths:

- **Linux + Google Android Emulator (recommended for cloud)** — a one-shot
  script provisions an Ubuntu 22.04 VM with nested virt enabled, installs
  KVM + the Android SDK + DroidFarm, and prints the SSH tunnel command you
  paste on your laptop to access the UI at `http://localhost:7870`. The
  backend stays bound to `127.0.0.1` on the VM so nothing is exposed
  publicly. Jump to [Path A](#path-a--linux--ssh-tunnel-recommended).
- **Windows + LDPlayer** — RDP-based, slower to set up, and you need to
  open port 7870 (or use RDP) to reach the UI. Jump to
  [Path B](#path-b--windows--ldplayer).

---

## Path A — Linux + SSH tunnel (recommended)

> The whole flow takes ~5 minutes if you have `gcloud` already
> authenticated. The DroidFarm backend never opens a port on the public
> internet — your laptop reaches it through an SSH local-port-forward
> over IAP.

### A0. Prereqs on your laptop

```bash
# gcloud CLI authenticated against the project that will host the VM.
gcloud auth login
gcloud config set project YOUR_PROJECT_ID

# Enable IAP (one-time, lets the SSH tunnel reach VMs without public IPs).
gcloud services enable iap.googleapis.com
```

### A1. One-shot launch

From a clone of DroidFarm on your laptop:

```bash
git clone https://github.com/devasan1/droidfarm.git
cd droidfarm
./scripts/gcp-launch.sh
```

The script:
1. Creates `droidfarm` (configurable via `INSTANCE_NAME=`) in
   `us-central1-a` (configurable via `ZONE=`) on `n2-standard-8`
   (configurable via `MACHINE_TYPE=`) with `--enable-nested-virtualization`
   and `--min-cpu-platform="Intel Cascade Lake"`.
2. SSHes in over IAP and verifies `/dev/kvm` exists. If it doesn't, the
   script aborts loudly — that means you picked an unsupported machine
   type (E2 / N2D / T2D / T2A) or nested virt didn't apply.
3. Installs `qemu-kvm`, OpenJDK 17 (required by `sdkmanager` /
   `avdmanager`), Python 3.11, Node 20, the Android command-line tools,
   `platform-tools`, `emulator`, and a system image
   (`system-images;android-34;google_apis;x86_64` — matches the driver
   default; install once, ~1 GB).
4. Clones DroidFarm into `~/droidfarm` and starts it via `./droidfarm.sh`
   bound to `127.0.0.1:7870`.
5. Prints the SSH tunnel command you run from your laptop.

Common knobs:

```bash
# Bigger VM for 8+ phones
MACHINE_TYPE=n2-standard-16 ./scripts/gcp-launch.sh

# Different zone / region
ZONE=us-east1-b ./scripts/gcp-launch.sh

# Multiple farms in the same project
INSTANCE_NAME=droidfarm-eu  ZONE=europe-west1-b  ./scripts/gcp-launch.sh

# Pin a specific git ref of DroidFarm (default: main)
DROIDFARM_REF=devin/some-fix-branch ./scripts/gcp-launch.sh
```

> **One-time gotcha on first run.** The script adds your user to the
> `kvm` and `libvirt` groups via `usermod -aG`, but Linux only applies
> new group memberships on **new login sessions**. The first time the
> script runs on a brand-new VM, it will print:
>
> ```
> [remote] current shell is NOT in the 'kvm' group yet ...
> ```
>
> When you see that, **log out, SSH back in, and re-run
> `./scripts/gcp-launch.sh`** — the second run is idempotent and the
> backend it starts will inherit the `kvm` group correctly. If you skip
> this step, phone-create succeeds but phone-start fails with
> `PermissionError: /dev/kvm`.

### A2. Open it in your local browser

In a second terminal on your laptop:

```bash
./scripts/gcp-tunnel.sh
```

That's a thin wrapper around:

```bash
gcloud compute ssh droidfarm --zone=us-central1-a --tunnel-through-iap -- \
  -N -L 7870:127.0.0.1:7870
```

Then open **http://localhost:7870** in any browser on your laptop. The UI
behaves exactly like a local install — the SSH tunnel forwards the HTTP
traffic, and DroidFarm has no idea it isn't being driven from the same
machine.

`Ctrl-C` in the tunnel terminal disconnects. Re-run `gcp-tunnel.sh` any
time. Re-running `gcp-launch.sh` is idempotent — it skips the VM create
step if the instance already exists and just refreshes the install.

### A2.5. First-time sanity checks

Before adding phones, confirm the VM is wired up correctly. SSH in via
`gcloud compute ssh droidfarm --zone=us-central1-a --tunnel-through-iap`
and run:

```bash
# 1. backend is up
curl -s -o /dev/null -w "health: %{http_code}\n" http://127.0.0.1:7870/api/health
# expect: health: 200

# 2. the *running backend process* is in the kvm group, not just your shell
cat /proc/$(pgrep -f 'uvicorn droidfarm.main:app')/status | grep -i Groups
# expect a line containing 109 (kvm) and 124 (libvirt) — not just one number

# 3. KVM works at all under your user (this is what hangs if nested virt
# silently fell back to TCG software emulation)
emulator -avd $(avdmanager list avd -c | head -1 || echo nope) \
  -no-window -no-audio -no-snapshot -no-boot-anim \
  -gpu swiftshader_indirect -verbose 2>&1 | head -20 | grep -i -E 'kvm|hvf|tcg'
# expect: a line confirming KVM acceleration. If you see 'TCG enabled' or
# 'cpu: tcg', nested virt is broken — see Troubleshooting.
```

If the Groups line is missing `109 124`, the backend was started in a
shell that pre-dated `usermod -aG kvm,libvirt`. Stop the backend
(`pkill -f 'uvicorn droidfarm.main:app'`), exit your SSH session
**fully**, reconnect, then re-run `./scripts/gcp-launch.sh`.

### A2.6. Performance expectations under nested virt

This is the part nobody mentions until you hit it. **Nested
virtualization on GCP is fine for automation, painful for interactive
use.** A handful of behaviors are inherent to the setup, not bugs:

- **First phone takes ~2 minutes to add.** DroidFarm pre-builds two
  hidden "template" AVDs before cloning your phone:
  `_droidfarm_template_factory` (never booted, raw Android) and
  `_droidfarm_template_configured` (booted once, setup wizard
  dismissed via adb, then shut down). The configured template is built
  lazily on the first phone-create with "Skip setup wizard". Subsequent
  adds clone from the configured template directly and start in
  ~30–45s.
- **`System UI isn't responding` ANR dialog during boot.** Click
  **Wait**. Android's system server gets starved during boot under
  nested-virt CPU pressure (you'll see `Long monitor contention ... for
  1.9s` in logcat). The dialog typically clears once dexopt + initial
  indexing finish (~10–15 minutes after boot). Idle perf afterward is
  much better.
- **~1–2 second tap-to-feedback latency**, even after warmup. DroidFarm
  renders the phone screen by polling `adb screencap` every ~1–2 s
  — it's a screenshotting console, not VNC/scrcpy. This floor is
  architectural; the only fixes are switching to scrcpy (separate
  project) or running on bare metal.
- **~30–50% slower than bare metal.** GCE's hypervisor wraps your VM,
  and your VM's KVM wraps the emulator. Two layers of hypervisor cost
  exists no matter how big your machine type is.

**To soften the worst of it on a nested-virt VM**, when you click **Add
phone** in the UI, bump the per-phone resources before clicking add:

| Setting | Default | Recommended for nested-virt |
|---|---:|---:|
| vCPU | 2 | **4** |
| RAM | 2560 MB | **4096 MB** |

With 4 vCPU / 4 GB you fit 2 phones comfortably on `n2-standard-8`
(8 vCPU / 32 GB) or 4 phones on `n2-standard-16`. If you need more than
that or sub-second responsiveness, see [A6](#a6--when-to-leave-the-cloud-bare-metal).

### A3. Tear it down

```bash
gcloud compute instances delete droidfarm --zone=us-central1-a
```

You're billed for the VM while it exists. If you want to keep state but
stop the meter, `gcloud compute instances stop` instead — restart later
with `gcloud compute instances start`, then re-run `gcp-tunnel.sh`.

### A4. Cost ballpark (us-central1, on-demand, 2025)

| Config | Hourly | Monthly (24×7) | Monthly (8h × 22d) |
|---|---:|---:|---:|
| n1-standard-4 | ~$0.19 | ~$140 | ~$33 |
| n2-standard-8 (default) | ~$0.39 | ~$280 | ~$68 |
| n2-standard-16 | ~$0.78 | ~$560 | ~$137 |

Add ~$0.17/GB-month for SSD (default disk is 200 GB pd-ssd ≈ $34/mo).
IAP and outbound traffic are negligible at hobby scale.

The VM bills while it exists, even when stopped (boot disk only when
stopped). To save money on a long break:

```bash
# stop — keeps disk + state, you pay only for storage
gcloud compute instances stop droidfarm --zone=us-central1-a
# resume
gcloud compute instances start droidfarm --zone=us-central1-a
# permanent teardown
gcloud compute instances delete droidfarm --zone=us-central1-a
```

When you `start` again, re-run `./scripts/gcp-tunnel.sh` from your
laptop and the previous phones / proxies / APKs are right where you
left them.

### A5. Troubleshooting (Linux + GCE)

Indexed by what you see. If it's not here, check
[`docs/TROUBLESHOOTING.md`](TROUBLESHOOTING.md) and
`tail -200 ~/.droidfarm/bootstrap.log` on the VM.

#### `gcp-launch.sh` aborts with "nested virtualization is required"

The VM was created without `--enable-nested-virtualization` or you used
an unsupported machine type. Fix:

```bash
gcloud compute instances delete droidfarm --zone=us-central1-a
./scripts/gcp-launch.sh   # re-run; the script always sets the flag
```

Machine families that support nested virt: **N1, N2, C2, C3** on Intel,
**N2D, C2D** on AMD with `--threads-per-core=1`. **Unsupported**: E2,
T2A, T2D, M-series, A-series, GPU types.

#### `gcp-tunnel.sh` errors with `permission denied (publickey)`

`gcloud auth login` and confirm your account has
`roles/iap.tunnelResourceAccessor` on the project (or owner / editor).

#### `gcloud` complains the IAP API isn't enabled

```bash
gcloud services enable iap.googleapis.com
```

#### `ERROR: JAVA_HOME is not set and no 'java' command could be found in your PATH.`

Your `gcp-launch.sh` predates the JDK install fix. Either `git pull` and
re-run, or one-shot:

```bash
sudo apt-get install -y openjdk-17-jdk-headless
export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
export PATH="$JAVA_HOME/bin:$PATH"
./scripts/gcp-launch.sh   # re-runs idempotently, the apt install is a no-op next time
```

#### Phone-create fails: `Package path is not valid. Valid system image paths are: system-images;android-XX;...`

The driver default and the installed system image have drifted. Either:

```bash
# A) install the image the driver wants (default android-34)
sdkmanager --install "system-images;android-34;google_apis;x86_64"

# B) pin DroidFarm to whatever you have installed, then restart the backend
DROIDFARM_ANDROID_SYSTEM_IMAGE='system-images;android-33;google_apis;x86_64' \
  ./droidfarm.sh
```

#### Phone-start fails: `PermissionError: [Errno 13] Permission denied: '/dev/kvm'`

The backend is running in a process that doesn't have the `kvm` group
active. Check:

```bash
cat /proc/$(pgrep -f 'uvicorn droidfarm.main:app')/status | grep -i Groups
# kvm group is GID 109 on Ubuntu 22.04 — if 109 isn't in the list, the
# backend can't open /dev/kvm.
```

Fix: stop the backend, **fully exit your SSH session** (group membership
changes only apply to *new* login sessions), reconnect, then re-run
`./scripts/gcp-launch.sh`.

#### `git checkout devin/<branch>` returns `pathspec did not match any file(s) known to git`

`gcp-launch.sh` versions before the follow-up patch cloned with
`--depth 1`. Plain `git fetch` doesn't pull other branches in a shallow
clone. Two options:

```bash
# A) fetch a single branch and create a local tracking ref in one shot
git fetch origin <branch>:<branch>
git checkout <branch>

# B) un-shallow the clone, then fetch normally
git fetch --unshallow
git checkout <branch>
```

Latest `gcp-launch.sh` does a full clone, so this only bites you on
VMs provisioned with the older script.

#### `System UI isn't responding` dialog appears during phone boot

Click **Wait**. The Android system server is starved during boot under
nested-virt CPU pressure. Should clear once `dexopt` + initial indexing
finish (~10–15 minutes after first boot). If it keeps re-appearing
after that, your phone is undersized — delete it, add a new one with 4
vCPU / 4096 MB RAM (see [A2.6](#a26-performance-expectations-under-nested-virt)).

#### Phone boots but the emulator runs at 2 fps / animations are choppy

KVM acceleration didn't actually engage — the emulator silently fell
back to TCG software emulation. Reproduce manually:

```bash
emulator -avd <any-avd-name> -no-window -no-audio -verbose 2>&1 | head -30 | grep -i -E 'kvm|tcg'
```

If you see `TCG enabled` instead of `KVM accelerator detected`,
`/dev/kvm` is unavailable to the emulator. Check `ls -l /dev/kvm`
(should exist and be group-writable by `kvm`) and the Groups check
above. If `/dev/kvm` doesn't exist at all, nested virt didn't apply to
the VM — delete and re-create.

#### Backend won't start; `bootstrap.log` shows nothing or a Python traceback

```bash
tail -200 ~/.droidfarm/bootstrap.log
# common causes:
#   - missing apt packages: re-run gcp-launch.sh
#   - frontend build failed (Node version mismatch): nvm install 20 / re-run
#   - data dir permissions: ls -la ~/.droidfarm and ~/droidfarm/data
```

#### Phones look fine but the UI in your browser is blank or hangs

The SSH tunnel died. From your laptop:

```bash
# Ctrl-C the old tunnel terminal if it's still hung, then re-run:
./scripts/gcp-tunnel.sh
```

Reload `http://localhost:7870`.

### A6. When to leave the cloud (bare metal)

Nested-virt is fine for **automation** (cron jobs, scheduled actions,
scripted workflows where you don't watch the screen). It is **not great
for interactive use** — the ~1–2 s screencap polling baseline plus
~30–50% slower CPU adds up to a UI that feels noticeably laggy.

If you need responsive interactive control or more than ~6 phones:

| Provider | Box | Typical price | Notes |
|---|---|---:|---|
| Hetzner | AX41-NVMe (Ryzen 5 3600, 64 GB) | ~$60/mo | Best $/perf for solo / small farms. |
| Hetzner | AX52 (i5-13500, 64 GB) | ~$80/mo | Newer Intel for the apps that detect "old CPU". |
| Equinix Metal | c3.small.x86 | ~$0.50/hr | Hourly, on-demand. Native KVM. |
| AWS | `c5.metal` / `m5.metal` | ~$4–6/hr | Steep, but useful if you're already in AWS. |
| OVH | Game-1-LE / Advance-1 | ~$70/mo | EU latency. |

DroidFarm's `droidfarm.sh` works the same on bare-metal Linux as it
does on the GCE VM — install the same `qemu-kvm` / `openjdk-17` /
Android SDK packages and run it. See
[`docs/linux-setup.md`](linux-setup.md) for the bare bash launcher
and [`docs/DEPLOYMENT.md`](DEPLOYMENT.md) for full deployment
recommendations.

---

## Path B — Windows + LDPlayer

This is the original DroidFarm path. Use it if you specifically need
LDPlayer (e.g. its ARM-on-x86 translation or its Play Services tweaks).
For most cloud users, Path A is faster and cheaper.

---

### B1. Pick a machine type that supports nested virt

GCP only allows nested virt on Intel/AMD x86 machine families. Rough sizing for DroidFarm:

| Instance family | vCPU | RAM | Good for |
|---|---:|---:|---|
| `n2-standard-4` | 4 | 16 GB | 1–3 phones, testing |
| `n2-standard-8` | 8 | 32 GB | **4–8 phones, daily driver** |
| `n2-standard-16` | 16 | 64 GB | 10+ phones, heavy automation |
| `c3-standard-8` | 8 | 32 GB | Same as n2-standard-8 but newer Sapphire Rapids CPUs |

**Unsupported:** Tau `T2D` / `T2A` (Arm), E2 (shared-core), A2 (GPU-accel; nested-virt is blocked).

> 💡 DroidFarm's control plane is lightweight (Python sidecar + Tauri UI). The heavy hitter is LDPlayer itself — budget ~2 GB RAM + ~1 vCPU *per phone* plus ~4 GB RAM for Windows + DroidFarm overhead.

### B2. Create the VM with nested virt enabled

#### Option A — gcloud CLI (recommended)

```powershell
# From your local machine, not inside GCP
gcloud compute instances create droidfarm `
    --zone=us-central1-a `
    --machine-type=n2-standard-8 `
    --image-family=windows-2022 `
    --image-project=windows-cloud `
    --enable-nested-virtualization `
    --boot-disk-size=200GB `
    --boot-disk-type=pd-ssd `
    --network-interface=nic-type=GVNIC
```

Notes:
- `--enable-nested-virtualization` is the critical flag. Without it, LDPlayer fails even if CPU virtualization is shown as "enabled" inside Windows.
- `pd-ssd` with 200 GB is comfortable: Windows + LDPlayer + 10 Android profiles + APKs. Go bigger if you'll preinstall a lot of apps per phone.
- `GVNIC` gets you better network throughput (proxy latency matters for geo-spoofed phones).

#### Option B — Cloud Console (GUI)

1. Go to **Compute Engine → VM instances → Create instance**.
2. Machine config: family **General purpose**, series **N2** (or C3), type `n2-standard-8`.
3. Boot disk: **Windows Server 2022 Datacenter**, 200 GB SSD.
4. Scroll to **Advanced options → Management → Metadata**, click **+ Add item**:
   - Key: `enable-nested-virtualization`
   - Value: `true`
5. Scroll to **Advanced options → Machine**, check **Enable nested virtualization**.
6. Create.

#### Option C — Enable on an existing VM

```powershell
gcloud compute instances stop <NAME> --zone=<ZONE>
gcloud compute instances update <NAME> `
    --zone=<ZONE> `
    --enable-nested-virtualization
gcloud compute instances start <NAME> --zone=<ZONE>
```

The VM must be stopped — updating a running instance won't apply the change.

### B3. Verify nested virt inside Windows

RDP into the VM and open **PowerShell (admin)**:

```powershell
systeminfo | Select-String "Hypervisor"
```

You want one of:
- `A hypervisor has been detected. Features required for Hyper-V will not be displayed.` ← **perfect** (means nested virt is live and Windows sees it).
- `Hyper-V Requirements: ... VM Monitor Mode Extensions: Yes` → **good**.

If you see `VM Monitor Mode Extensions: No` — nested virt is **not** enabled. Re-check step 2.

Also double-check Hyper-V is **off** on the VM (LDPlayer uses its own VT-x layer and conflicts with Hyper-V):

```powershell
Get-WindowsOptionalFeature -Online -FeatureName Microsoft-Hyper-V | Select-Object State
```

If `Enabled`, disable and reboot:

```powershell
Disable-WindowsOptionalFeature -Online -FeatureName Microsoft-Hyper-V -NoRestart
bcdedit /set hypervisorlaunchtype off
Restart-Computer
```

### B4. Install LDPlayer 9

```powershell
# Silent-ish install from the official installer
$installer = "$env:TEMP\ldplayer9.exe"
Invoke-WebRequest "https://res.ldrescdn.com/download/package/LDPlayer9.exe" -OutFile $installer
Start-Process $installer -ArgumentList "/S" -Wait
```

Verify:

```powershell
& 'C:\LDPlayer\LDPlayer9\ldconsole.exe' list
```

DroidFarm auto-detects `ldconsole.exe` at the default path. If you installed elsewhere, set `DROIDFARM_LDCONSOLE` env var to the absolute path.

### B5. Install DroidFarm

```powershell
git clone https://github.com/devasan1/droidfarm.git C:\droidfarm
cd C:\droidfarm
.\scripts\install.ps1          # installs Python 3.11, Node 20, Rust (for Tauri), ADB, tun2socks
.\scripts\start.ps1            # builds + launches the desktop app
```

By default DroidFarm listens on `127.0.0.1:7870`. The Tauri window opens automatically.

### B6. Firewall / networking

If you plan to drive the UI from a remote browser (e.g. bypassing RDP), open port 7870:

```powershell
New-NetFirewallRule -DisplayName "DroidFarm" `
    -Direction Inbound -Protocol TCP -LocalPort 7870 -Action Allow
gcloud compute firewall-rules create droidfarm `
    --direction=INGRESS --action=ALLOW --rules=tcp:7870 `
    --source-ranges=<YOUR_IP>/32
```

Don't leave 7870 open to `0.0.0.0/0` — it has full control over your phones.

### B7. Troubleshooting

| Symptom | Fix |
|---|---|
| LDPlayer window opens then closes immediately | Nested virt not on — re-check B3 |
| "The virtual machine could not be started" | Hyper-V is conflicting — disable it (step 3) |
| Phones boot but no internet | Windows Defender blocking LDPlayer's TAP adapter; add an exclusion |
| Proxy set but phone still shows real IP in apps | System HTTP proxy alone isn't enough — switch that phone to "tun2socks" mode in DroidFarm (default) |
| `ldconsole list` returns nothing | LDPlayer installed elsewhere — set `DROIDFARM_LDCONSOLE` |
| Extremely slow phone boot (minutes) | You're probably on E2 or Tau — migrate to N2/C3 |
