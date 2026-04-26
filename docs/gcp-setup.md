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
3. Installs `qemu-kvm`, Python 3.11, Node 20, the Android command-line
   tools, the `platform-tools` + `emulator` + a system image
   (`system-images;android-33;google_apis;x86_64`).
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
```

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

Add ~$0.17/GB-month for SSD. **Nested virt is ~30–50% slower than bare
metal** because of the double hypervisor layer — totally fine for 1–8
phones but it gets painful past that. For a heavier farm, a bare-metal
host (Hetzner AX line, AWS `.metal`, Equinix Metal) gives you native KVM
performance at a similar or lower price.

### A5. Troubleshooting

| Symptom | Fix |
|---|---|
| `gcp-launch.sh` fails with "Aborting: nested virtualization is required" | The VM was created without `--enable-nested-virtualization` or you used an unsupported machine type. Delete the instance and re-run. |
| `gcp-launch.sh` rejects `MACHINE_TYPE=...` upfront | You picked E2 / N2D / T2D / T2A — those don't support nested virt. Use N1 / N2 / C2 / C3. |
| `gcp-tunnel.sh` errors with "permission denied (publickey)" | Run `gcloud auth login` and make sure your account has `roles/iap.tunnelResourceAccessor` on the project. |
| Phones boot but feel slow | Default is `n2-standard-8`. Bump to `n2-standard-16` or move to bare metal. |
| `gcloud` IAP errors | Enable the API: `gcloud services enable iap.googleapis.com`. |

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
