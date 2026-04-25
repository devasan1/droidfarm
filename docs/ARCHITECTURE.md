# DroidFarm — Architecture & Contributor Guide (A–Z)

This document is the canonical "where does the code live, why is it structured
that way, and where do I change X?" guide for DroidFarm. It's written so a new
engineer (or the author's future self six months from now) can extend, debug,
or harden any part of the system without spelunking.

If you want to **use** DroidFarm, read [README.md](../README.md) first. This
doc is for **building on** DroidFarm.

---

## 1. One-paragraph summary

DroidFarm is a single-node Android farm controller. It runs a FastAPI backend
(Python 3.11) that manages a fleet of emulated Android phones through a
pluggable "driver" — LDPlayer 9 on Windows for the production path, a
no-op mock driver for development on Linux/macOS. A React + Vite + Tailwind
frontend, served by the same FastAPI process in production (it's bundled to
static files), gives you a grid of phones with live previews, a proxies table,
an APK library, a trash bin, cron-style schedules, and settings (import /
export). State — phones, proxies, APKs, schedules — lives in a SQLite file
under `%APPDATA%\DroidFarm` on Windows or `~/.droidfarm` on Linux, so the
whole farm survives close/reopen and host reboots with no data loss. A Tauri v2
shell wraps the whole thing into a `.msi` / `.exe` for one-click Windows install.

---

## 2. Design goals (so you know what to preserve)

1. **Single-node, zero-config.** You download one file (`DroidFarm.bat` or the
   `.msi`) and double-click. No DB server, no separate services, no cloud.
2. **Close / reopen = zero data loss.** Every phone's proxy, fingerprint,
   geo overrides, installed APKs, cached cookies, login sessions, and uptime
   counter survive across restarts.
3. **Unique proxy per phone, DB-enforced.** You cannot silently give two
   phones the same proxy. The `proxies.phone_id` FK has a UNIQUE constraint at
   the SQLAlchemy and SQLite level.
4. **Per-phone fingerprint + geo coherence.** IMEI, Android ID, MAC, serial,
   GSF ID, build props, WebView UA, locale, timezone, GPS — all derived from
   the proxy country and pinned per phone. Two clones from the same template
   never share identity.
5. **Opt-in destructive actions.** Auto-rotate proxies is **off by default**
   per proxy row. Wipe is a per-tile button. Purge (irreversible delete)
   requires type-to-confirm.
6. **Linux/macOS dev parity.** You can develop the whole stack without
   Windows. Mock driver returns colored PNG frames so the UI renders; every
   backend workflow is identical.

When you're making a change, ask: *does this preserve those six?* If not, the
change should be an explicit opt-in flag, not the new default.

---

## 3. Top-level repo layout

```
droidfarm/
├── README.md                  # user-facing quickstart
├── LICENSE                    # Apache-2.0
├── DroidFarm.bat              # Windows single-click launcher
├── droidfarm.sh               # Linux/macOS equivalent
├── scripts/bootstrap.ps1      # PowerShell bootstrap the .bat calls
├── Dockerfile + docker-compose.yml   # alt Linux deploy
├── .github/workflows/windows-release.yml   # CI that builds the .msi
├── docs/                      # markdown docs (this file, gcp-setup, linux-setup)
├── backend/                   # Python FastAPI app
│   ├── pyproject.toml
│   ├── droidfarm/
│   │   ├── __init__.py        # exports version
│   │   ├── main.py            # FastAPI app factory + startup hooks
│   │   ├── config.py          # settings + data-dir resolution
│   │   ├── db.py              # SQLAlchemy models + session factory
│   │   ├── schemas.py         # Pydantic request/response schemas
│   │   ├── api/               # HTTP routes (one file per resource)
│   │   │   ├── routes_health.py
│   │   │   ├── routes_phones.py
│   │   │   ├── routes_proxies.py
│   │   │   ├── routes_apks.py
│   │   │   ├── routes_schedules.py
│   │   │   └── routes_farm.py     # export / import zip
│   │   └── core/              # domain logic (not HTTP-aware)
│   │       ├── driver.py      # LDPlayerDriver + MockDriver + Driver abstract base
│   │       ├── adb.py         # subprocess wrapper around `adb`
│   │       ├── templates.py   # golden-template (factory / configured) bootstrap
│   │       ├── fingerprint.py # per-phone IMEI/MAC/Android-ID generator
│   │       ├── geoip.py       # ipapi.co lookup via proxy or direct
│   │       ├── locales.py     # country → locale + timezone table (~80 rows)
│   │       ├── cities.py      # country+city → lat/lon/tz table (~250 rows)
│   │       ├── app_catalog.py # curated 12-app APKMirror catalog
│   │       └── scheduler.py   # cron polling daemon
│   └── tests/                 # pytest suite (FastAPI TestClient)
├── frontend/                  # React + Vite + Tailwind SPA
│   ├── package.json
│   ├── vite.config.ts
│   ├── tailwind.config.js
│   └── src/
│       ├── main.tsx           # Router + page mounts
│       ├── App.tsx            # Sidebar nav
│       ├── lib/
│       │   ├── api.ts         # typed fetch client; the ONE place base URL lives
│       │   └── types.ts       # shared TypeScript interfaces
│       ├── components/        # reusable pieces (AddPhoneModal, ConfirmModal, PhoneViewer)
│       └── pages/             # one .tsx per sidebar entry (Phones, Proxies, …)
└── src-tauri/                 # Rust shell that wraps the web UI into a .msi
    ├── Cargo.toml
    ├── tauri.conf.json
    └── src/main.rs
```

**Rule of thumb:** domain logic goes in `backend/droidfarm/core/`, HTTP goes
in `backend/droidfarm/api/`, UI goes in `frontend/src/pages/` or
`frontend/src/components/`. If a function is HTTP-aware (uses FastAPI's
`HTTPException`, `Request`, `Depends`) it should live under `api/`; everything
else belongs in `core/` where it can be unit-tested without booting a server.

---

## 4. Runtime architecture

```
┌────────────────────────────────────────────────────────────────┐
│  DroidFarm.bat / Tauri .msi                                   │
│       │                                                       │
│       └─► python -m droidfarm.main  (FastAPI on :7870)         │
│                  │                                            │
│                  ├─► SQLite:   %APPDATA%\DroidFarm\droidfarm.sqlite │
│                  ├─► APK dir:  %APPDATA%\DroidFarm\apks\           │
│                  ├─► Template: %APPDATA%\DroidFarm\templates.json  │
│                  │                                            │
│                  ├─► Driver (LDPlayer on Win / Mock on *nix)      │
│                  │       │                                    │
│                  │       └─► ldconsole.exe + adb → phone VMs  │
│                  │                                            │
│                  ├─► Scheduler thread (poll every 10s)        │
│                  │       └─► croniter → due schedules → action│
│                  │                                            │
│                  └─► Static: frontend/dist/ (React SPA)       │
└────────────────────────────────────────────────────────────────┘
```

All four paths (LDPlayer control, SQLite writes, HTTP requests, scheduler)
run in a single Python process. The scheduler is a background `threading.Thread`
started in the FastAPI `startup` hook. SQLite handles concurrency via its own
journal mode; the codebase uses the `session_scope()` context manager so every
write commits or rolls back atomically.

**Ports used:**

| Port  | What                    |
|-------|-------------------------|
| 7870  | FastAPI HTTP + static   |
| 5173  | Vite dev server (dev only) |

---

## 5. The database (`backend/droidfarm/db.py`)

SQLite, synchronous SQLAlchemy. Each table is one `class` with `Mapped[...]`
columns.

| Table      | Purpose                                            |
|------------|----------------------------------------------------|
| `proxies`  | Proxy list. `phone_id` FK with UNIQUE constraint.  |
| `phones`   | Phones. `proxy_id` FK, soft-delete via `deleted_at`.|
| `apks`     | APK library. `filename`, `sha256`, `size`.         |
| `schedules`| Cron-style jobs. `cron`, `action`, `params` JSON.  |

**Adding a column to an existing table:**

1. Add the `mapped_column(...)` to the model in `db.py`.
2. Add an in-place migration block in `main.py`'s `startup` hook next to the
   existing ones (see `ALTER TABLE phones ADD COLUMN deleted_at` for the
   pattern). This is intentionally simple — we don't use Alembic because the
   cost of a full migration framework isn't worth it for a single-user
   desktop app. The migration block checks `PRAGMA table_info(...)` for the
   new column name and `ALTER TABLE` it in if missing.
3. Update the matching Pydantic schema in `schemas.py`.
4. Update `frontend/src/lib/types.ts` so the TS side sees the new field.

**Adding a new table:**

1. Add the `class` in `db.py`. Do **not** rename or reorder existing classes —
   SQLAlchemy's metadata cares about order for foreign-key resolution in some
   cases.
2. On first boot after adding, `Base.metadata.create_all(engine)` (called from
   `main.py`) auto-creates the new table in existing DBs.

---

## 6. The driver layer (`backend/droidfarm/core/driver.py`)

The single most important abstraction in the codebase.

```python
class Driver(ABC):
    @abstractmethod
    def list_instances(self) -> list[str]: ...
    @abstractmethod
    def create(self, name: str, profile: DeviceProfile) -> None: ...
    @abstractmethod
    def clone_from_template(self, new: str, template: str) -> None: ...
    @abstractmethod
    def start(self, name: str) -> None: ...
    @abstractmethod
    def stop(self, name: str) -> None: ...
    @abstractmethod
    def destroy(self, name: str) -> None: ...
    @abstractmethod
    def set_proxy(self, name: str, proxy: ProxySpec) -> None: ...
    @abstractmethod
    def set_geo(self, name: str, lat: float, lon: float) -> None: ...
    @abstractmethod
    def adb_address(self, name: str) -> str | None: ...
    # ... etc
```

Three implementations ship with the repo:

- **`LDPlayerDriver`** — shells out to `ldconsole.exe` (LDPlayer 9's CLI) for
  lifecycle + native GPS/locale spoofing, and to `adb` for in-phone commands
  (settings, setprop, screencap). Used in production on Windows. ldconsole
  returns non-zero exit codes (commonly 3) on `add` and `copy` even when
  successful — `_run` accepts `check=False` and the caller verifies via
  `list2`.
- **`AndroidEmulatorDriver`** — wraps Google's stock `emulator`,
  `avdmanager`, and `adb` from the Android SDK. The cross-platform driver:
  used on **macOS** (Apple Silicon → arm64-v8a system image, native via HVF;
  Intel → x86_64 with HAXM), **Linux** (KVM via `/dev/kvm`), and **Windows
  without LDPlayer** (WHPX/HAXM). AVDs live under
  `~/.android/avd/<name>.avd/` plus a sibling `<name>.ini`. Cloning is a
  filesystem copy + `.ini` rewrite (faster than ldconsole's `copy`). Per-AVD
  settings (resolution, dpi, cpu, ram, IMEI) are written into `config.ini`
  before boot. Locale / timezone / Android ID / GPS are applied via `adb`
  after boot.
- **`MockDriver`** — no-op in-memory driver that returns colored PNG
  screenshots. Used on hosts without any real driver, in CI, and in pytest.
  It persists nothing; state lives only in its own dict. `supports_adb` is
  False, so any adb-dependent operation returns 501.

**Choosing at runtime:** `backend/droidfarm/config.py` and `get_driver()` in
`driver.py` together pick the driver in this priority:

1. `DROIDFARM_MOCK=1` env → `MockDriver` (CI / dev override).
2. `DROIDFARM_DRIVER` env (`ldplayer` / `android_emulator` / `mock`) →
   forced choice (still requires the underlying tool to be present).
3. `ldconsole.exe` detected (Windows) → `LDPlayerDriver`.
4. Android SDK detected (any OS) → `AndroidEmulatorDriver`.
5. Otherwise → `MockDriver`.

Detection paths:

- **LDPlayer**: scans `C:\`, `D:\`, `E:\` drives for
  `\LDPlayer\LDPlayer9\ldconsole.exe`,
  `\Program Files\LDPlayer\LDPlayer9\ldconsole.exe`,
  `\Program Files (x86)\LDPlayer\LDPlayer9\ldconsole.exe`,
  `\LDPlayer9\ldconsole.exe`. Override with `DROIDFARM_LDCONSOLE`.
- **Android SDK**: `~/Library/Android/sdk` (Mac), `~/Android/Sdk` (Linux),
  `%LOCALAPPDATA%\Android\Sdk` (Windows), plus the standard env vars
  `ANDROID_SDK_ROOT` / `ANDROID_HOME`. Override with
  `DROIDFARM_ANDROID_SDK`.

`/api/health` returns `{driver, ldconsole, android_sdk, adb, platform, ...}`
so the frontend can render the right sidebar pill (green for a real driver,
amber for mock) and the Settings → Driver section can show install
instructions for whichever driver is missing.

**Adding a new driver** (e.g. a `RedroidDriver` for real Android on Linux via
Docker):

1. Create a class in `backend/droidfarm/core/driver.py` (or a sibling module
   imported from there) that subclasses `Driver` and implements every
   abstract method.
2. Add detection in `config.py` (a `_default_<thing>()` function + a new
   field on `Settings`).
3. Wire it into `get_driver()` in `driver.py` with the appropriate
   priority.
4. Update `/api/health` and the frontend's `DriverBadge` / Settings page so
   the new driver is surfaced in the UI.
5. Add tests that exercise the new driver against the abstract `Driver`
   contract (see `tests/test_api.py` for how the mock is exercised).

This is how iOS support (hypothetical) or a QEMU-based Android-x86 driver
would be added.

---

## 7. API surface (`backend/droidfarm/api/`)

Every route file is a `fastapi.APIRouter` that gets mounted in `main.py`:

```python
app.include_router(phones_router, prefix="/api/phones", tags=["phones"])
```

### Route-file cheat-sheet

| File                      | Prefix               | Key endpoints                              |
|---------------------------|----------------------|--------------------------------------------|
| `routes_health.py`        | `/api/health`        | GET for liveness + driver/adb info.        |
| `routes_phones.py`        | `/api/phones`        | CRUD + start/stop/wipe + screenshot + shell + logcat + install-apk + trash/restore/purge + regenerate-fingerprint + bulk ops. This is the biggest file (~1100 lines). |
| `routes_proxies.py`       | `/api/proxies`       | CRUD + import + health-check + stats + rotate + set-auto-rotate. |
| `routes_apks.py`          | `/api/apks`          | Upload + catalog + fetch-from-url + delete. |
| `routes_schedules.py`     | `/api/schedules`     | CRUD + run-now + action-specs. |
| `routes_farm.py`          | `/api/farm`          | Export zip + import zip.                    |

**Conventions you should follow when adding a route:**

- **Put specific paths before parameterised paths.** FastAPI matches in
  declaration order. `/api/proxies/stats` MUST be defined before
  `/api/proxies/{proxy_id}` or the former will try to parse "stats" as an int.
  We got bitten by this — the fix is in commit `6085841`.
- **Pydantic for request + response.** Don't accept raw `dict` bodies;
  declare a `schemas.py` class.
- **HTTPException for client errors, `logger.exception` + 500 for server
  errors.** Never let an unhandled exception bubble through; it leaks
  stack traces.
- **Wrap DB work in `with session_scope() as s:`.** Never pass a `Session`
  across a `yield`; commit before you return.

---

## 8. Pydantic schemas (`backend/droidfarm/schemas.py`)

One class per "shape" of data crossing the API boundary. When you add a new
column to a model, add it to the matching `*Out` schema and (if writable)
the `*In` / `*Create` / `*Patch` schemas. Keep the schema names consistent:

- `FooCreate` — POST body
- `FooPatch`  — PATCH body (all fields optional)
- `FooOut`    — GET response

---

## 9. Frontend architecture (`frontend/src/`)

**Stack:** React 18 + React Router v6 + TypeScript + Vite + Tailwind v3 +
lucide-react icons. No Redux, no Zustand — each page holds its own state via
`useState` + `useEffect` + a `refresh()` callback that re-hits the API. For
a desktop-scale app (one user, <100 phones) that's plenty.

**The single source of truth for "what's the backend URL":**
`frontend/src/lib/api.ts`'s `BASE` constant. In dev it's `http://localhost:7870`;
in production (served from the same host) it's empty string. Never hardcode a
URL anywhere else.

### Page structure

Every page file (`pages/Phones.tsx`, etc.) follows this shape:

```tsx
export default function SomePage() {
  const [rows, setRows] = useState<Row[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    try { setRows(await api.listRows()); } catch (e) { setError(String(e)); }
  }

  useEffect(() => { refresh(); }, []);

  return (
    <div>
      <PageHeader ... />
      {error && <ErrorBanner text={error} />}
      {rows?.map(r => <RowCard key={r.id} row={r} onChange={refresh} />)}
    </div>
  );
}
```

**Adding a new page:**

1. Create `frontend/src/pages/MyPage.tsx`.
2. Add it to the router in `main.tsx`:
   ```tsx
   <Route path="mypage" element={<MyPage />} />
   ```
3. Add a sidebar entry in `App.tsx`:
   ```tsx
   <Nav to="/mypage" icon={<IconX size={16} />}>My page</Nav>
   ```
4. Add any new API methods to `lib/api.ts` and types to `lib/types.ts`.

### Live screenshots

`<img src="/api/phones/{id}/screenshot?t={n}" />` where `t` is a cache-busting
counter that bumps every 2 seconds. The server returns a fresh PNG each call.
For the expand-viewer we poll at ~5 fps (200ms). Coordinates in the viewer are
mapped from the rendered image rect back to the phone's native resolution so
taps land where you click regardless of window size.

---

## 10. Where to make common changes

| Want to…                                   | Edit                                                     |
|--------------------------------------------|----------------------------------------------------------|
| Add a new driver (e.g. QEMU / Redroid)     | `backend/droidfarm/core/driver.py` (+ factory in config) |
| Change the default data directory          | `backend/droidfarm/config.py` — `_default_data_dir()`    |
| Add a new column to `phones`               | `db.py` + in-place migration in `main.py` + `schemas.py` + `lib/types.ts` |
| Add a new sidebar page                     | `frontend/src/pages/` + `main.tsx` + `App.tsx`           |
| Add a new scheduled action                 | `scheduler.py` (`_run_action`) + `routes_schedules.py` (action specs) + `Schedules.tsx` |
| Add a new APK catalog app                  | `backend/droidfarm/core/app_catalog.py`                  |
| Extend the country → locale/tz table       | `backend/droidfarm/core/locales.py`                      |
| Add a city to the city → lat/lon table     | `backend/droidfarm/core/cities.py`                       |
| Change what fingerprint fields are pinned  | `backend/droidfarm/core/fingerprint.py`                  |
| Tweak the dark theme                       | `frontend/tailwind.config.js` + `frontend/src/index.css` |
| Add a Tauri system-tray item               | `src-tauri/src/main.rs`                                  |
| Change the Windows installer icon          | `src-tauri/icons/*`                                      |
| Add a CI check                             | `.github/workflows/windows-release.yml` (or new file)    |

---

## 11. Per-feature deep dives

These are the subsystems that required the most thought; read these before
you touch them.

### 11.1 Unique proxy per phone

`proxies.phone_id` is a nullable INT with a UNIQUE constraint. When you assign
a phone to a proxy, we update `phones.proxy_id` and SQLite enforces that no
other row in `phones` can hold the same `proxy_id` (the UNIQUE is on the
join-side in `proxies`). This is how we guarantee you can't accidentally give
two phones the same IP.

On phone deletion (soft): we null `phones.proxy_id` so the proxy becomes free
for reuse. On restore: if the original proxy is still free, we re-bind it.

**Don't bypass this by hand-editing SQLite.** If you're writing new code, use
the `assign_proxy(phone_id, proxy_id)` helper in `routes_phones.py` which
checks the constraint before writing.

### 11.2 Fingerprint randomization

`fingerprint.py` generates one `Fingerprint` dataclass per phone:

- **IMEI**: random 14 digits + Luhn checksum. Apps see the same IMEI across
  reboots of the same phone.
- **Android ID**: 16 hex chars.
- **MAC wifi + bt**: random OUI from a curated list of real manufacturers
  (Samsung, Xiaomi, Motorola, etc).
- **Serial, GSF ID, advertising ID, Firebase IID**: random.
- **Build props**: pulled from a curated 12-device catalog
  (Pixel 6, Galaxy S22, Xiaomi 12, OnePlus 10, Nokia X20, Motorola Edge 30,
  etc). We copy `ro.product.model`, `ro.product.manufacturer`,
  `ro.product.device`, `ro.product.brand`, `ro.build.fingerprint` as a
  coherent set so a "Pixel 6" phone doesn't claim to be a "Samsung device"
  in another field.
- **WebView UA**: derived from the build so Chrome-in-the-phone tells apps
  the expected UA string.

Applied at first boot via LDPlayer's native `modify` command (for IMEI, model,
manufacturer, MAC) plus `adb shell setprop ro.product.*` + `settings put
secure android_id <n>` for the rest. Results persist across reboots because
LDPlayer writes them to the instance's disk and setprops are set on boot by
our worker.

**Regenerate on demand:** `POST /api/phones/{id}/regenerate-fingerprint`
picks a new random device and re-applies. Useful if a particular fingerprint
got flagged.

### 11.3 Geo spoof: locale + timezone + GPS from proxy country

Two tables:

1. `locales.py` — country code → (locale, timezone). ~80 rows, curated.
   Example: `"DE" → ("de-DE", "Europe/Berlin")`.
2. `cities.py` — (country, city) → (lat, lon, timezone). ~250 rows.
   Example: `("DE", "Berlin") → (52.520, 13.405, "Europe/Berlin")`.

Flow on phone create:

1. Proxy health-check populates `country, city, latitude, longitude, timezone`
   from ipapi.co.
2. Phone inherits those values (or uses manual overrides from the Add-phone
   modal for Bypass-IP mode).
3. On boot: worker waits for `sys.boot_completed=1`, then:
   - `ldconsole locate --name X --LLI <lng,lat>` (LDPlayer native GPS; Fused
     Location / Play Services see it).
   - `adb shell appops set android mock_location allow` + broadcast through
     mock-location provider (legacy LocationManager apps).
   - `adb shell setprop persist.sys.locale <locale>` + `persist.sys.timezone`.
   - `adb shell service call iphonesubinfo …` sets IMEI (on top of the
     LDPlayer-level IMEI, for apps that check via TelephonyManager).

Persisted in `phones.geo_overrides` JSON so restarts reuse the same numbers.

### 11.4 Clean templates (`templates.py`)

On first real-LDPlayer boot we prep two hidden instances:

- `_droidfarm_template_factory` — untouched fresh AOSP clone. Will run
  setup wizard when copied. Used when the user checks "Show first-boot setup
  wizard" in Add-phone modal.
- `_droidfarm_template_configured` — booted once, setup wizard dismissed via
  `settings put global device_provisioned 1` + `settings put secure
  user_setup_complete 1`. Used by default (checkbox off → "already past
  setup").

Both are flagged in `%APPDATA%\DroidFarm\templates.json` so they don't get
rebuilt on every backend start. Every `ldconsole add` is really
`ldconsole copy --name <new> --from <template>` — fresh data, fresh Android ID,
identical base image.

### 11.5 Scheduler (`scheduler.py`)

A background `threading.Thread` that wakes every 10 seconds. For each schedule
row where `enabled=True` and `next_run_at <= now`, it:

1. Resolves `target_phone_ids` (empty list = all live phones).
2. Fires the action (`start`, `stop`, `wipe`, `rotate_gps`, `launch_package`,
   `force_stop_package`, `shell`) per target.
3. Updates `last_run_at`, `last_status`, `last_error`.
4. Computes the next `next_run_at` via `croniter.get_next(datetime)`.

All actions are idempotent — firing `start` on an already-running phone is a
no-op. The scheduler never raises; it catches and logs every action exception
so one bad schedule doesn't break the polling loop.

**Adding a new action type:**

1. Add the action name to `ACTIONS` in `scheduler.py`.
2. Implement the branch in `_run_action(sched, phone)`.
3. Add the action to `schedule_actions()` in `routes_schedules.py` with a
   param spec so the UI knows what inputs to render.
4. The frontend `Schedules.tsx` reads `/api/schedules/actions` and renders
   dynamic form fields. No frontend changes needed for a new action unless
   you want custom UI.

### 11.6 Export / import (`routes_farm.py`)

Export streams a ZIP containing:

- `droidfarm.sqlite` — the full DB
- `apks/` — every APK in the library (by hash-name)
- `templates.json` — so the new host knows templates don't need rebuilding
- `ldbk/` — optional LDPlayer `.ldbk` backups (Windows only, checkbox in UI)

Import is a merge by default (only add missing rows; don't overwrite). An
explicit checkbox switches to "wipe and replace" mode; that path calls
`DELETE FROM phones/proxies/apks` before loading.

---

## 12. Adding a new feature end-to-end (worked example)

Say you want to add a **"pin phone to top of grid"** feature.

1. **DB**: add `phones.pinned: Mapped[bool]` with default False in `db.py`.
2. **Migration**: add an `ALTER TABLE phones ADD COLUMN pinned INTEGER DEFAULT 0`
   block in `main.py`'s startup migration section.
3. **Schema**: add `pinned: bool` to `PhoneOut` and `PhonePatch` in `schemas.py`.
4. **Route**: the existing `PATCH /api/phones/{id}` already accepts arbitrary
   fields from `PhonePatch` — no new route needed.
5. **API client**: no changes if `patchPhone` already spreads the body.
6. **Types**: add `pinned: boolean` to `Phone` in `lib/types.ts`.
7. **UI**: in `Phones.tsx`, sort phones by `(pinned ? 0 : 1)` before rendering,
   add a pin button to each tile that calls `api.patchPhone(id, { pinned: !p.pinned })`.
8. **Test**: add one pytest in `tests/test_api.py` that patches `pinned=True`
   and reads back.

Total diff: <100 lines across 5 files. That's the shape every feature should have.

---

## 13. Testing

### Backend

```bash
cd backend
python -m venv .venv
. .venv/bin/activate
pip install -e . pytest httpx
python -m pytest
```

`tests/test_api.py` spins up the FastAPI app in a `TestClient` with the mock
driver and verifies the full phone create / proxy assign / screenshot /
delete / restore flow. Add a test per new endpoint.

### Frontend

```bash
cd frontend
npm install
npm run build       # type-checks + bundles
npm run dev         # Vite dev server on :5173 with HMR
```

There's no frontend unit test harness yet; this is a place we could grow
into (Vitest + React Testing Library) if UI complexity demands it.

### End-to-end

```bash
./droidfarm.sh      # Linux/macOS
# or DroidFarm.bat  # Windows
```

Opens `http://localhost:7870`. On Linux without LDPlayer/redroid you'll see
the mock driver's colored PNGs; every other workflow is real.

---

## 14. Build & release

### Windows installer (.msi / .exe)

1. Tag a release: `git tag v0.1.0 && git push origin v0.1.0`.
2. `.github/workflows/windows-release.yml` fires on the tag push. It:
   - Installs Node 20, Rust stable, caches cargo.
   - `npm ci && npm run build` to produce `frontend/dist/`.
   - `tauri-apps/tauri-action@v0` builds `DroidFarm_<version>_x64_en-US.msi`
     and `DroidFarm_<version>_x64-setup.exe`.
   - Attaches both to a draft GitHub release named after the tag.
3. Review the draft, publish when happy.

You cannot build the `.msi` from Linux — WiX is Windows-only. That's why the
CI runner is `windows-latest`.

### Linux Docker image

```bash
docker compose build
docker compose up -d
```

Publishes to port 7870 on the host. Persistent data lives in a named volume
`droidfarm-data` that maps to `/root/.droidfarm` in the container.

---

## 15. Debugging tips

- **"I see 'Error: [object Object]' in the UI."** `req()` in `lib/api.ts`
  stringifies error detail properly as of `6085841`. If you see this, you're
  on an older build — rebuild the frontend.
- **"One of my routes 422s with `int_parsing` on a string."** You likely
  defined a specific path (e.g. `/foo/stats`) AFTER a parameterised one
  (`/foo/{id}`) in the same router. FastAPI matches in order — move the
  specific one up.
- **"Phone stuck in `starting` forever."** Check `last_error` on the phone
  row. If empty, the boot worker is still running; check backend logs for
  `adb` / `ldconsole` errors. On mock driver this shouldn't happen.
- **"Scheduler fired twice for one cron tick."** It shouldn't — we update
  `next_run_at` before executing. If you see this, check that only one
  FastAPI process is running (`ps aux | grep droidfarm`).
- **"SQLite locked."** You're hitting the DB from two processes. Don't do
  that — single-process is the design. If you're running tests in parallel,
  use `pytest-xdist -n 1` or give each test its own `data_dir`.
- **"Uptime counter resets on page reload."** Uptime is derived from
  `last_started_at` — which persists. If it resets, the phone actually
  rebooted (check driver logs).

---

## 16. Security & privacy notes

- DroidFarm binds to `127.0.0.1:7870` by default. **Do not** change it to
  `0.0.0.0` without adding auth first — the API is unauthenticated (single-user
  desktop tool).
- Proxy passwords live in SQLite in plaintext. Treat `%APPDATA%\DroidFarm` as
  sensitive. If you're running on a shared GCP VM, enable full-disk encryption.
- No telemetry, no auto-update, no phone-home. The only external HTTP call
  the backend makes is to ipapi.co for geo-lookup (you can pin a custom host
  via `DROIDFARM_GEOIP_URL`).

---

## 17. Roadmap ideas (not committed — feel free to pick one)

- **Auth layer.** JWT + basic user/pass for multi-user LAN installs.
- **Redroid driver** on Linux (real Android without LDPlayer). Requires host
  kernel with `binder_linux` module.
- **iOS support** as a separate driver that talks to physical iPhones via
  `go-ios`. See Architecture Q&A in the main conversation for caveats.
- **Playbook engine.** YAML per phone that says "day 1: open app X, scroll for
  5min, like 3 posts". Would layer on top of scheduler.
- **Per-proxy latency history graph** (sparkline on the Proxies page).
- **Frontend test suite** (Vitest + React Testing Library).
- **Golden-template versioning.** Right now templates are rebuilt if the user
  manually deletes them; we could version them and auto-rebuild on Android
  version bump.
- **Multi-host farms.** Control multiple LDPlayer VMs from one UI. Requires
  splitting the app into a control plane + worker plane.

---

## 18. FAQ

**Q: Why not Postgres?**
A: Single-user desktop app. SQLite is file-in-place, zero-config, and durable.
The DB will happily hold 10k phone rows without breaking a sweat; that's ~5
orders of magnitude more than anyone would use.

**Q: Why LDPlayer and not Android Studio's emulator?**
A: LDPlayer has a CLI (`ldconsole.exe`) that's purpose-built for running many
instances in parallel with low overhead. Android Studio's emulator is great
for dev but boots slower, uses more RAM per instance, and its CLI is less
batch-friendly.

**Q: Why Tauri and not Electron?**
A: Bundle size (~10MB vs ~150MB), memory (Tauri uses the OS WebView, so the
overhead is the Rust shell only), and a cleaner Rust-side sidecar story for
spawning the Python backend.

**Q: Why opt-in auto-rotate instead of automatic?**
A: Silent rotation breaks long-running logins. If the user is halfway through
adding an account on a phone and we rotate its proxy under them, the session
is dead. The design decision was made after a specific user ask: *"Proxy
auto-rotate should only happen when the user selects to do so, else no."*

---

*Last updated: April 2026. If you change a fundamental assumption here, update
this doc in the same PR.*
