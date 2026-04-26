# Where to deploy DroidFarm

DroidFarm needs a host that can run Android emulators. Not every host can.
This doc explains which hosts work, which don't, and what they cost.

Short version:

> **For interactive use or >6 phones, use bare-metal Linux (Hetzner) or your local Mac/PC.**
>
> **For automation / batch workloads, GCE with `--enable-nested-virtualization` works well via [`docs/gcp-setup.md`](gcp-setup.md) at ~30–50% bare-metal speed.**

Why: Android emulators need hardware-accelerated virtualization (HVF on
Mac, KVM on Linux, Hyper-V/WHPX on Windows). Most cloud VMs expose
*nested* virtualization, which is slower than native and on some
providers incomplete. The Linux Android emulator + nested KVM
combination on GCE works in practice (now validated end-to-end with
`scripts/gcp-launch.sh`); LDPlayer + nested Hyper-V on GCE Windows
does not.

## Decision tree

```
Will I run real phones on this host?
├── No (dev / CI / UI work) ────► any cheap VM + MockDriver. Done.
├── Yes, 1–4 phones, ad-hoc    ────► your local Mac or Windows PC.
├── Yes, 1–4 phones, always-on ────► mini PC at home (Mac mini, NUC, etc.).
├── Yes, automation / batch jobs ───► GCE n2-standard-8 with nested virt. See docs/gcp-setup.md.
├── Yes, 5–15 phones, always-on ───► bare-metal Linux (Hetzner AX42 / EX44).
├── Yes, 20+ phones, always-on ────► multiple bare-metal boxes + redroid (planned).
└── Yes, but I'm locked into AWS/GCP ─► GCE nested virt for moderate use, otherwise `*.metal`.
```

## Hosts that work well

### Local Mac (Apple Silicon)

- **M1 / M2 / M3 / M4** Mac Mini / Studio / MacBook.
- Emulator runs native arm64 Android via HVF — no config needed.
- Best price/performance for 1–6 phones.
- Walkthrough: [`mac/README.md`](../mac/README.md).
- **Caveat:** disk fills fast (~6 GB per AVD); the 256GB base model maxes
  out at ~5 phones with heavy apps.

### Local Windows PC

- Desktop or laptop with 16 GB+ RAM and a modern CPU.
- LDPlayer 9 is the fastest option on Windows (ARM translation + Play
  Store preinstalled).
- 6–10 phones on a midrange gaming PC.
- Walkthrough: [`README.md`](../README.md#quick-start-windows).

### Bare-metal Linux (Hetzner, OVH, Vultr Bare Metal, SoYouStart)

- Real hardware, real KVM. No nested virt, no noise.
- **Hetzner AX42** (Ryzen 7 7700, 64 GB) — **€45/mo**. 8–10 phones.
- **Hetzner EX44** (i5-13500, 64 GB) — **€45/mo**. 10–12 phones.
- OVH SoYouStart has similar price/perf in other regions.
- Setup: install Ubuntu 24.04, run the Linux launcher (`./droidfarm.sh`).
- Walkthrough: [`docs/linux-setup.md`](linux-setup.md).

### GCP sole-tenant nodes

- Dedicated physical hardware on GCP. Not a VM — you're the only tenant.
- **~$1.50/hr minimum** (plus the VM on top), so ~$1,100/mo for a tiny
  one. Gets expensive fast.
- Only makes sense if you're already deep in GCP for other reasons and
  can't move the workload to Hetzner.

### AWS `.metal` instances

- `c5.metal` — 48 cores, 96 GB — ~$4/hr ≈ $2,900/mo.
- `m5.metal` — 96 cores, 384 GB — ~$4.60/hr ≈ $3,300/mo.
- Same "dedicated hardware" deal as GCP sole-tenant, priced per hour.
- Reasonable if you need to burst 50+ phones for a short campaign; brutal
  as a 24/7 host.

### GCE Linux + nested KVM (N1 / N2 / C2 / C3 with `--enable-nested-virtualization`)

- **Works**, but slower than bare metal. The Linux Android emulator
  uses nested KVM successfully on Intel-family GCE machine types.
  Validated end-to-end via `scripts/gcp-launch.sh` on `n2-standard-8`.
- **n2-standard-8** (8 vCPU / 32 GB) handles 2–4 phones at 4 vCPU /
  4 GB each.
- **n2-standard-16** (16 vCPU / 64 GB) handles 6–8 phones.
- ~30–50% slower than bare metal because of the double hypervisor
  layer. Fine for automation / cron jobs / scripted workflows. Painful
  for interactive UI use — the screencap-polling render path adds an
  inherent ~1–2 s tap-to-feedback latency on top of the CPU overhead.
- Boots take ~60–90 s; the very first phone takes ~2 min while
  DroidFarm builds the configured-template AVD.
- Walkthrough: [`docs/gcp-setup.md`](gcp-setup.md).

## Hosts that don't work (for real phones)

### GCE Windows + LDPlayer (nested Hyper-V)

- **Won't** run accelerated Android. LDPlayer requires nested Hyper-V
  specifically; GCP exposes nested KVM.
- The CPU features LDPlayer needs (`VT-x unrestricted guest`, `EPT`, a
  subset of APIC virt) aren't fully passed through to the Windows
  guest.
- Use the Linux + nested KVM path above instead, or move LDPlayer to a
  local Windows PC.

### Regular AWS EC2 (t3, m5, c5, etc.)

- Nitro hypervisor doesn't pass KVM through to the guest, so the
  Android emulator falls back to software emulation.
- Software emulation is 5-20x slower than KVM; unusable in practice.
- Use `*.metal` instances or move to GCE / bare metal.

### Azure VMs (D-series, E-series, etc.)

- Azure supports nested virt on most SKUs, but Android emulators hit the
  same Hyper-V/HVF gap. Same outcome as GCP/AWS.

### Docker / Kubernetes without `--privileged` and a kernel with KVM

- `redroid` (planned) will work in containers with `--privileged` on a
  Linux host that has `binder` + `ashmem` compiled into its kernel.
- Stock Docker Desktop on Mac/Windows uses a VM with a kernel missing
  those — see the discussion in [`docs/linux-kernel-setup.md`](linux-kernel-setup.md).

## What works, with caveats

### Oracle Cloud ARM Always Free

- 4 arm64 cores + 24 GB free forever.
- KVM works, arm64 system images run *natively*.
- Great for 1–2 phones as a free always-on host.
- Caveat: ingress speed is slow, may not be production-worthy; also
  Oracle reclaims "free" VMs aggressively if idle.

### Azure Dpsv5 / Dpdsv5 (ARM bare metal-adjacent)

- Ampere-based ARM64 VMs with KVM available to guests.
- Works for real emulators (arm64 native).
- Not the cheapest but a defensible cloud option when your org needs Azure.

## Cost comparison for 8 concurrent phones, 24/7

| Host                          | Monthly cost | Notes |
| ----------------------------- | ------------ | ----- |
| Hetzner AX42                  | **€45 ≈ $50** | Winner |
| Hetzner EX44                  | **€45 ≈ $50** | Winner |
| M4 Mac mini (one-time $600)   | amortized ~$17/mo over 3yr | Assumes you already have electricity/network |
| Used mini PC (one-time $300)  | amortized ~$8/mo | Same |
| Oracle ARM free tier          | $0            | Only 2 phones; free-tier can be revoked |
| GCE n2-standard-8 (on-demand)    | ~$280         | Works via nested virt; ~30–50% slower than bare metal |
| GCE n2-standard-8 (preemptible)  | ~$150         | Same as above but evicted every 24h max |
| AWS c5.metal                  | ~$2,900       | Massive overkill unless running 50+ phones |
| Azure Dpdsv5 (d8pdsv5)        | ~$280         | ARM-native, works |

## Operational considerations

### Persistent storage

- All drivers store state under `%APPDATA%\DroidFarm` (Win), `~/.droidfarm`
  (Mac/Linux). That's where you'd snapshot.
- Emulator disks live under `~/.android/avd/<name>.avd/` (AndroidEmulator)
  or LDPlayer's install dir (LDPlayer). Back these up separately if you
  want to preserve per-phone app state.
- Cloud: attach a persistent volume; don't use ephemeral local SSD for
  DroidFarm state.

### Networking

- Default bind is `127.0.0.1:7870`. To access remotely, set
  `DROIDFARM_HOST=0.0.0.0` **and** put a reverse proxy / VPN / SSH tunnel
  in front (DroidFarm has no built-in auth yet — don't expose it raw).
- Each phone's proxy is outbound only; phones don't need inbound.

### Monitoring

- `/api/health` is the liveness probe.
- Structured logs go to stdout; pipe them to your log aggregator.
- The scheduler emits `phone.started` / `phone.stopped` / `phone.crashed`
  events that you can hook into for alerting.

### Always-on

- DroidFarm's scheduler restarts phones automatically on crash / host
  reboot, as long as they have `autostart=true` (the default). The only
  thing you need to make survive is the backend process itself — run it
  under `systemd` on Linux, or configure it as a LaunchAgent on Mac.

### A sample Linux systemd unit

```ini
# /etc/systemd/system/droidfarm.service
[Unit]
Description=DroidFarm backend
After=network.target

[Service]
Type=simple
User=droidfarm
WorkingDirectory=/home/droidfarm/droidfarm
Environment=DROIDFARM_STATIC_DIR=/home/droidfarm/droidfarm/frontend/dist
Environment=ANDROID_SDK_ROOT=/home/droidfarm/Android/Sdk
ExecStart=/home/droidfarm/.droidfarm/venv/bin/python -m droidfarm
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### A sample macOS LaunchAgent

```xml
<!-- ~/Library/LaunchAgents/ai.devin.droidfarm.plist -->
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
  <dict>
    <key>Label</key><string>ai.devin.droidfarm</string>
    <key>ProgramArguments</key>
    <array>
      <string>/Users/you/droidfarm/mac/droidfarm.command</string>
    </array>
    <key>KeepAlive</key><true/>
    <key>RunAtLoad</key><true/>
  </dict>
</plist>
```

Load with `launchctl load ~/Library/LaunchAgents/ai.devin.droidfarm.plist`.

## FAQ

**Q: Can I run DroidFarm in Docker?**

A: The backend runs in Docker fine. Real emulators-in-Docker need a host
kernel with `binder`+`ashmem` (for redroid) OR KVM passthrough (for the
Google emulator). Docker Desktop on Mac/Windows does not satisfy either by
default; see [`docs/linux-kernel-setup.md`](linux-kernel-setup.md).

**Q: I already have a GCP VM with DroidFarm — is this all wasted?**

A: No. Two paths depending on the VM's machine type:

1. **N1 / N2 / C2 / C3 with `--enable-nested-virtualization`**: re-provision
   via `scripts/gcp-launch.sh` (or run it on the existing VM — it's
   idempotent). The Linux Android emulator works; see
   [`docs/gcp-setup.md`](gcp-setup.md).
2. **E2 / N2D / T2A / T2D / shared-core**: nested virt isn't supported.
   Use the VM as a **control-plane** host: run the backend + DB + UI
there, but run the phones on a different machine and point the scheduler
at them over a VPN. This is a less common setup; you'd have to adapt the
driver to dispatch commands over SSH to the remote phone host.

**Q: Does Apple Silicon hurt app compatibility?**

A: Most modern apps ship arm64; they run native. ~5% of apps are
x86-only and need an `x86_64` system image, which on Apple Silicon runs
through Rosetta-like translation and is slower (~1/3 the speed of
native). If your target app is one of those, LDPlayer on Windows or
bare-metal Linux may be a better fit.

**Q: Do I need to re-buy proxies when moving hosts?**

A: No. Proxies are vendor accounts, host-independent. Use
**Settings → Export farm / Import farm** to move the farm config from
one host to another.
