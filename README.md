# DroidFarm

A desktop control plane for running **multiple Android emulators** on your Windows box, each with its **own proxy** so every phone truly looks like it's in a different country/city. Built for 1-10 concurrent devices, APK sideloading, Google Play pre-installed, ARM app support, and persistent always-on operation.

> ⚠️ **Running on a GCP Windows VM?** You **must** enable nested virtualization first or no emulator will boot. See [`docs/gcp-setup.md`](docs/gcp-setup.md) for the exact steps.

---

## What it does

- **Add phone** → modal where you pick a device profile (Pixel 6 / Android 13 by default), optionally preinstall APKs, and **pick a proxy** from your pool (auto-assigns a unique one if you don't).
- **Phone grid** with a live scrcpy-style thumbnail of each phone, status chip, current proxy IP + country flag, and click-to-fullscreen control.
- **Always-on by default** — phones keep running through app restarts, host reboots, and GCP spot-preemption. Each phone reclaims the same proxy it had before.
- **"Feels like it's in that city"** — DroidFarm matches every phone's system locale, language, timezone, and GPS coordinates to its assigned proxy's geoIP so apps see consistent signals (not a US timezone on a German IP).
- **APK library** — drag an APK onto the window to add it to the shared library, then right-click any phone → Install.
- **ADB shell** per phone built into the UI.

## Stack

- **Emulator engine:** LDPlayer 9 — Play Store preinstalled, ARM translation on by default, scales to 10 concurrent instances on an 8-core Windows host.
- **Control app:** Tauri v2 (React + TypeScript + Tailwind frontend, Rust shell that ships a tiny Windows `.msi`).
- **Backend sidecar:** Python 3.11 FastAPI, drives `ldconsole.exe` + `adb` + the proxy pool; SQLite for persistence.
- **Proxy routing:** per-phone `tun2socks` sidecar so every byte of app traffic (including pinned connections) goes through the proxy.

## Quick start (Windows)

Double-click **`DroidFarm.bat`**. First run installs Python 3.11, Node 20, Git, LDPlayer 9, then builds the frontend and boots the backend. Subsequent launches take ~3 seconds.

See **[`docs/gcp-setup.md`](docs/gcp-setup.md)** if you're hosting on GCP — nested virt is a prerequisite.

## Quick start (Linux / macOS)

```bash
git clone https://github.com/devasan1/droidfarm.git
cd droidfarm
./droidfarm.sh
```

or with Docker:

```bash
docker compose up --build
```

Then open http://localhost:7870. Details (including redroid driver for real Android instances on Linux): **[`docs/linux-setup.md`](docs/linux-setup.md)**.

DroidFarm opens to a blank grid. Click **+ Add phone**, point it at a proxy (or paste a list into Proxies first), and wait ~60s for the first phone to boot.

## Proxies

Import a proxy list (`user:pass@host:port`, one per line, or CSV) via **Proxies → Import**. DroidFarm health-checks each proxy on import and records its country / city / ASN via a free geoIP lookup. When you add a phone with "Auto-assign", the app picks a healthy unused proxy and locks it to that phone.

Trusted vendors (have used for farming workflows):

| Vendor | Type | Pricing | Notes |
|---|---|---|---|
| [Bright Data](https://brightdata.com) | Residential / Mobile / ISP | Enterprise | Biggest pool, highest quality, ~$15/GB |
| [Oxylabs](https://oxylabs.io) | Residential / Mobile | Mid-high | Strong docs, generous trial |
| [Smartproxy / Decodo](https://smartproxy.com) | Residential / Mobile | Mid | Best balance of price & quality |
| [IPRoyal](https://iproyal.com) | Residential / Mobile | **$1.75/GB** | Best value entry point |
| [SOAX](https://soax.com) | Residential / Mobile | Mid | Flexible city/carrier targeting |
| [Proxy-Cheap](https://proxy-cheap.com) | Residential / Mobile | Cheap | Budget tier |

Avoid lifetime "$50 forever" sellers — those are either botnets or resold junk.

## Repo layout

```
droidfarm/
├── app/                  Tauri v2 shell (Rust)
├── frontend/             React + Vite + Tailwind UI
├── backend/              Python FastAPI sidecar
│   └── droidfarm/
│       ├── api/          HTTP routes (phones, proxies, apks, settings)
│       ├── core/         LDPlayer driver, ADB wrapper, proxy pool, geo spoof
│       └── main.py
├── scripts/              install.ps1, start.ps1, dev.ps1, etc.
└── docs/                 gcp-setup.md and other guides
```

## Status

Early scaffold — backend skeleton + GCP guide first. Commit cadence: every 4-5 min. See `git log` for where we are.

## License

Apache-2.0.
