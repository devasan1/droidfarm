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
| `DROIDFARM_MOCK` | auto | Force mock driver (`1` / `0`) |

## 2. Docker

```bash
docker compose up --build
```

Then open http://localhost:7870. Stop with `Ctrl+C`.

To expose on your LAN instead of localhost:

```bash
docker compose up --build  # already binds 0.0.0.0:7870
# on the host:  open http://<your-ip>:7870 from another machine
```

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
