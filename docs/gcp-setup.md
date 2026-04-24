# Running DroidFarm on a GCP Windows VM

DroidFarm uses **LDPlayer 9** under the hood, which boots an Android VM on top of Intel VT-x / AMD-V. Because GCP Windows instances sit *inside* the GCE hypervisor, you must **explicitly enable nested virtualization** or LDPlayer will fail with "VT-x is not available" / "Unable to start VM" the moment you try to boot a phone.

This guide covers every step end-to-end.

---

## 1. Pick a machine type that supports nested virt

GCP only allows nested virt on Intel/AMD x86 machine families. Rough sizing for DroidFarm:

| Instance family | vCPU | RAM | Good for |
|---|---:|---:|---|
| `n2-standard-4` | 4 | 16 GB | 1–3 phones, testing |
| `n2-standard-8` | 8 | 32 GB | **4–8 phones, daily driver** |
| `n2-standard-16` | 16 | 64 GB | 10+ phones, heavy automation |
| `c3-standard-8` | 8 | 32 GB | Same as n2-standard-8 but newer Sapphire Rapids CPUs |

**Unsupported:** Tau `T2D` / `T2A` (Arm), E2 (shared-core), A2 (GPU-accel; nested-virt is blocked).

> 💡 DroidFarm's control plane is lightweight (Python sidecar + Tauri UI). The heavy hitter is LDPlayer itself — budget ~2 GB RAM + ~1 vCPU *per phone* plus ~4 GB RAM for Windows + DroidFarm overhead.

## 2. Create the VM with nested virt enabled

### Option A — gcloud CLI (recommended)

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

### Option B — Cloud Console (GUI)

1. Go to **Compute Engine → VM instances → Create instance**.
2. Machine config: family **General purpose**, series **N2** (or C3), type `n2-standard-8`.
3. Boot disk: **Windows Server 2022 Datacenter**, 200 GB SSD.
4. Scroll to **Advanced options → Management → Metadata**, click **+ Add item**:
   - Key: `enable-nested-virtualization`
   - Value: `true`
5. Scroll to **Advanced options → Machine**, check **Enable nested virtualization**.
6. Create.

### Option C — Enable on an existing VM

```powershell
gcloud compute instances stop <NAME> --zone=<ZONE>
gcloud compute instances update <NAME> `
    --zone=<ZONE> `
    --enable-nested-virtualization
gcloud compute instances start <NAME> --zone=<ZONE>
```

The VM must be stopped — updating a running instance won't apply the change.

## 3. Verify nested virt inside Windows

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

## 4. Install LDPlayer 9

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

## 5. Install DroidFarm

```powershell
git clone https://github.com/devasan1/droidfarm.git C:\droidfarm
cd C:\droidfarm
.\scripts\install.ps1          # installs Python 3.11, Node 20, Rust (for Tauri), ADB, tun2socks
.\scripts\start.ps1            # builds + launches the desktop app
```

By default DroidFarm listens on `127.0.0.1:7870`. The Tauri window opens automatically.

## 6. Firewall / networking

If you plan to drive the UI from a remote browser (e.g. bypassing RDP), open port 7870:

```powershell
New-NetFirewallRule -DisplayName "DroidFarm" `
    -Direction Inbound -Protocol TCP -LocalPort 7870 -Action Allow
gcloud compute firewall-rules create droidfarm `
    --direction=INGRESS --action=ALLOW --rules=tcp:7870 `
    --source-ranges=<YOUR_IP>/32
```

Don't leave 7870 open to `0.0.0.0/0` — it has full control over your phones.

## 7. Cost ballpark (us-central1, on-demand, 2025)

| Config | Hourly | Monthly (24×7) | Monthly (8h × 22d) |
|---|---:|---:|---:|
| n2-standard-4 | ~$0.19 | ~$140 | ~$33 |
| n2-standard-8 | ~$0.39 | ~$280 | ~$68 |
| n2-standard-16 | ~$0.78 | ~$560 | ~$137 |

Add ~$0.17/GB-month for the SSD. You can save ~60 % with a 3-year committed-use discount or by running spot instances (fine for farming since DroidFarm's autostart recovers from preemption).

## Troubleshooting

| Symptom | Fix |
|---|---|
| LDPlayer window opens then closes immediately | Nested virt not on — re-check step 3 |
| "The virtual machine could not be started" | Hyper-V is conflicting — disable it (step 3) |
| Phones boot but no internet | Windows Defender blocking LDPlayer's TAP adapter; add an exclusion |
| Proxy set but phone still shows real IP in apps | System HTTP proxy alone isn't enough — switch that phone to "tun2socks" mode in DroidFarm (default) |
| `ldconsole list` returns nothing | LDPlayer installed elsewhere — set `DROIDFARM_LDCONSOLE` |
| Extremely slow phone boot (minutes) | You're probably on E2 or Tau — migrate to N2/C3 |
