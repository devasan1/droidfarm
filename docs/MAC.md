# macOS

The Mac guide lives next to the scripts it documents:
**[`../mac/README.md`](../mac/README.md)**.

That's the A-Z install + usage guide for a fresh Mac. Look there for:

- What the `mac/` folder contains.
- What `mac/setup.sh` installs (Xcode CLT, Homebrew, JDK 17, Python 3.11,
  Node 20, Android SDK, system image, factory AVD, DroidFarm venv).
- How to launch via `mac/droidfarm.command`.
- How to uninstall via `mac/uninstall.sh`.
- The full manual procedure if `setup.sh` ever breaks.
- Troubleshooting specific to Mac.

Related docs:

- [`PLATFORMS.md`](PLATFORMS.md) — feature parity matrix for all drivers.
- [`DEPLOYMENT.md`](DEPLOYMENT.md) — choosing a host (local Mac vs.
  Hetzner vs. cloud).
- [`TROUBLESHOOTING.md`](TROUBLESHOOTING.md) — Mac-specific issues start
  in the "macOS / Android Emulator" section.
- [`ARCHITECTURE.md`](ARCHITECTURE.md) — how `AndroidEmulatorDriver` fits
  into the driver abstraction.
