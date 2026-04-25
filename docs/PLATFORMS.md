# Platforms & feature parity

DroidFarm runs on Windows, macOS, and Linux. Each host uses a different
driver under the hood, so some features vary. Use this document to pick a
platform, understand trade-offs, and diagnose "why is X not working on Y".

## At a glance

| Platform              | Driver                    | Acceleration      | Recommended for             |
| --------------------- | ------------------------- | ----------------- | --------------------------- |
| Windows + LDPlayer 9  | `LDPlayerDriver`          | Hyper-V / WHPX    | Windows power users, fastest single-host throughput |
| Windows (no LDPlayer) | `AndroidEmulatorDriver`   | WHPX / HAXM       | Windows dev without installing LDPlayer |
| macOS (Apple Silicon) | `AndroidEmulatorDriver`   | HVF (native arm64) | Mac users; arm64 apps run native |
| macOS (Intel)         | `AndroidEmulatorDriver`   | HAXM              | Legacy Intel Macs           |
| Linux (bare metal)    | `AndroidEmulatorDriver`   | KVM (`/dev/kvm`)  | Dedicated servers (Hetzner, OVH) |
| Linux (cloud VM)      | `AndroidEmulatorDriver` + software fallback | None (slow) | Control-plane / CI only, not real farming |
| Linux + redroid       | (planned)                 | Containers        | High-density farms (10+ phones) on bare metal |
| Any, no emulator      | `MockDriver`              | N/A               | Dev / pytest / UI work      |

## Feature parity matrix

| Capability                  | LDPlayer (Win) | AndroidEmulator (all) | MockDriver |
| --------------------------- | -------------- | --------------------- | ---------- |
| Phone lifecycle (create/clone/start/stop/destroy) | ✓ | ✓ | ✓ (in-memory) |
| Headless / background boot  | ✓              | ✓ (`-no-window`)      | N/A        |
| Live screencap (adb)        | ✓              | ✓                     | flat-color placeholder |
| APK install                 | ✓              | ✓                     | logs only  |
| GPS fix                     | ✓ (ldconsole `locate`) | ✓ (`adb emu geo fix`) | logs only |
| Locale / language / country | ✓              | ✓ (adb `setprop`)     | logs only  |
| Timezone                    | ✓              | ✓ (adb `setprop`)     | logs only  |
| IMEI spoof                  | ✓ (ldconsole `modify`) | ✓ (AVD `config.ini`) | N/A    |
| Android ID spoof            | ✓              | ✓ (adb sqlite)        | N/A        |
| Manufacturer / model spoof  | ✓              | partial (requires `-writable-system` + remount) | N/A |
| MAC address spoof           | ✓              | partial (boot-time `-prop`) | N/A    |
| Per-phone HTTP proxy        | ✓              | ✓ (`emulator -http-proxy`) | N/A   |
| Per-phone SOCKS / tun2socks | ✓              | ✓ (same sidecar pattern) | N/A    |
| Play Store preinstalled     | ✓ (bundled)    | ✓ (with `google_apis_playstore` image) | N/A |
| ARM app support             | ✓ (x86 host, ARM translation) | ✓ on arm64 host; translated on x86 | N/A |
| `.ldbk` backup / import     | ✓              | ✗ (uses AVD-dir copy) | N/A        |
| Snapshot / restore          | ✓              | ✓ (emulator snapshots) | N/A       |
| Scheduler integration       | ✓              | ✓                     | ✓ (no-op) |
| SafetyNet / Play Integrity detection | detected as emulator | detected as emulator | N/A |

## Performance expectations

Numbers are approximate; your mileage varies with the apps you're running.

| Host                                      | Phones (comfortable) | Boot time (cold) | Boot time (snapshot) |
| ----------------------------------------- | -------------------- | ---------------- | -------------------- |
| Windows desktop, 8-core Ryzen, 32GB       | 6–8 LDPlayer         | ~30s             | ~8s                  |
| M4 Mac Mini, 16GB                         | 4 Android Emulator   | ~60s             | ~10s                 |
| M4 Mac Studio, 64GB                       | 10–12                | ~45s             | ~8s                  |
| Hetzner AX42 (Ryzen 7 7700, 64GB)         | 8–10 Linux emulator  | ~45s             | ~10s                 |
| Hetzner EX44 (i5-13500, 64GB)             | 10–12                | ~40s             | ~8s                  |
| GCP n2-standard-8 + nested virt           | 2 (software fallback) | ~5min            | ~1min                |
| GCP n2-standard-8 without nested virt     | **does not work**    | —                | —                    |

Apple Silicon's advantage: **native arm64 Android**. Most apps ship arm64
binaries and skip the x86→ARM translation layer that LDPlayer relies on.
That makes M-series Macs punch above their weight on paper — an M4 Mac
Mini often matches a much beefier Windows desktop for arm64-first apps.

## Environment variables

Every driver / path / setting has an env-var override for when auto-detection
isn't what you want.

| Variable                      | Default                                            | Effect |
| ----------------------------- | -------------------------------------------------- | ------ |
| `DROIDFARM_MOCK`              | auto                                               | `1` forces the mock driver |
| `DROIDFARM_DRIVER`            | auto                                               | Force `ldplayer` / `android_emulator` / `mock` |
| `DROIDFARM_LDCONSOLE`         | auto-scan drives                                   | Absolute path to `ldconsole.exe` |
| `DROIDFARM_ANDROID_SDK`       | `~/Library/Android/sdk` (Mac) / `~/Android/Sdk` (Linux) / `%LOCALAPPDATA%\Android\Sdk` (Win) | Absolute path to Android SDK root |
| `ANDROID_SDK_ROOT` / `ANDROID_HOME` | (same)                                       | Honored by Google tooling too |
| `DROIDFARM_ANDROID_SYSTEM_IMAGE` | `system-images;android-34;google_apis;arm64-v8a` on arm64, `...;x86_64` on x86 | Which image to use for new AVDs |
| `DROIDFARM_ADB`               | SDK `platform-tools/adb`                           | Absolute path to `adb` |
| `DROIDFARM_STATIC_DIR`        | unset (dev mode proxies Vite)                      | Directory with the built `frontend/dist` (the Tauri shell / mac launcher sets this) |
| `DROIDFARM_DATA_DIR`          | `%APPDATA%\DroidFarm` (Win) / `~/.droidfarm` (Unix) | SQLite, APKs, logs |
| `DROIDFARM_HOST`              | `127.0.0.1`                                        | bind address |
| `DROIDFARM_PORT`              | `7870`                                             | HTTP port |
| `DROIDFARM_DEV`               | `0`                                                | `1` enables extra logging and dev-only routes |

## Which driver am I running?

Check the sidebar pill in the app, or:

```bash
curl -s http://127.0.0.1:7870/api/health | python -m json.tool
```

The `driver` field is one of `ldplayer`, `android_emulator`, or `mock`.

## Switching platforms without losing data

Use **Settings → Export farm** on the old host and **Settings → Import
farm** on the new one. The export is a zip containing phone / proxy / APK
definitions plus APK blobs. It does **not** contain the emulator disks —
each host will clone fresh phones from its own factory template. Apps and
data that were installed on the old host are not migrated.

If you need the emulator disks too (e.g. Windows → Windows migration only),
check the "Include VM disks" box in Export. This produces a much larger
zip and only makes sense between hosts running the same driver flavor.

## Known limitations per driver

### LDPlayerDriver

- Windows only (LDPlayer has no macOS build).
- Hyper-V conflicts: can't run simultaneously with WSL2 in some
  configurations; disable Hyper-V if you're not using it for other things.
- `add` / `copy` return non-zero exit codes on success — the driver
  tolerates this by verifying via `list2`.
- Some apps detect LDPlayer specifically via Frida probes; rename
  `/system/lib*/ldconsole*` or use Magisk Hide if this matters.

### AndroidEmulatorDriver

- `google_apis` images don't include the Play Store. Use
  `google_apis_playstore` for Play Store support, but note those images are
  signed and can't run as root (breaks build-prop spoofing).
- Build-prop spoofing (manufacturer / model strings) requires
  `-writable-system` + `adb root` + `adb remount`; slower cold boot and
  breaks Play Integrity.
- `.ldbk` imports are not supported — cloning is native to the AVD layout.

### MockDriver

- No real phones. Every adb-dependent operation returns 501 with a
  friendly "current driver does not surface adb" message.
- Screenshots are flat-color placeholders (one color per phone index).
