# DroidFarm

Desktop control plane for running multiple Android emulator phones on Windows,
each with its own unique proxy and a geo profile that matches the proxy's
country/city.

> This is the bootstrap `main`. The full implementation lives on feature
> branches — see the open pull requests.

## Status

Active development. First feature drop lands via PR from
`devin/1776998174-scaffold`, which covers:

- LDPlayer 9 driver + mock driver for Linux dev
- Per-phone unique proxy assignment
- GeoIP-matched locale / timezone / GPS spoofing
- Live per-phone preview + interactive full-size viewer
- Soft-delete / Trash / restore / type-to-confirm purge
- APK library + common-apps catalog
- Bulk multi-select actions
- Per-phone console / logcat / apps tabs
- Per-phone hardware fingerprint randomization
- Autostart on backend + host reboot
- Export / import whole farm
- Proxy health dashboard + opt-in auto-rotate
- Cron-style scheduled actions
- Linux launcher + Docker
- Tauri v2 shell + Windows `.msi` / `.exe` release workflow

See the PR for full details.
