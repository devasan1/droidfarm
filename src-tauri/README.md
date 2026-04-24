# DroidFarm Tauri shell

This directory wraps the DroidFarm Python backend + React frontend
in a native Windows desktop app that produces a single `.msi` (or
NSIS `.exe`) installer. End users double-click the installer, then
double-click the Start-menu entry — no `.bat` file involved.

## What the shell does

1. Installer places the backend tree + the built frontend next to
   `DroidFarm.exe` (see `bundle.resources` in `tauri.conf.json`).
2. On launch, `src/main.rs`:
   - spawns `python -m droidfarm` as a child process,
   - waits up to 30 s for the backend to listen on `127.0.0.1:7870`,
   - opens a native window pointed at `http://localhost:7870`.
3. Closing the window kills the backend child.

## Building locally on Windows

Prereqs:
- Rust (stable) via https://rustup.rs
- Node 20+
- Python 3.11+ on PATH (used at runtime; not needed for the build)
- Visual Studio 2022 Build Tools (C++ toolset + Windows 10 SDK)

```powershell
# from repo root
cd frontend ; npm install ; npm run build ; cd ..
cd src-tauri
cargo install tauri-cli --version "^2"
cargo tauri build
```

Output:
- `src-tauri/target/release/bundle/msi/DroidFarm_0.1.0_x64_en-US.msi`
- `src-tauri/target/release/bundle/nsis/DroidFarm_0.1.0_x64-setup.exe`

## Building in CI

`.github/workflows/windows-release.yml` does the above on a GitHub
`windows-latest` runner and attaches the installers as a release
asset on any `v*` tag push. To cut a release:

```bash
git tag v0.1.0
git push origin v0.1.0
```

## Limitations

- `.msi` **cannot be built from Linux or macOS** — Microsoft's WiX
  toolset is Windows-only. Use the CI workflow, or a Windows box.
- The current shell assumes Python 3.11+ is already on PATH. If it
  isn't, the shell exits cleanly with a stderr message; the NSIS
  post-install option is set up to run `DroidFarm.bat` which in
  turn installs Python via winget. (Planned: bundle a PyInstaller
  build of the backend to remove the Python dependency entirely.)
- LDPlayer 9 is still installed on first run by `DroidFarm.bat`,
  not by this installer, because it's ~600 MB and optional on
  systems that want mock mode.
