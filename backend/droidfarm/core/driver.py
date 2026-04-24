"""Abstraction over the Android-emulator engine.

Two implementations:

* ``LDPlayerDriver`` wraps ``ldconsole.exe`` on Windows.
* ``MockDriver`` pretends to run phones so the backend can be developed
  and tested on Linux / CI without an emulator installed.

The API is intentionally small: create, list, start, stop, destroy, modify,
install APK. Anything richer (ADB shell, tap/swipe automation) goes through
the ADB wrapper directly against the ``127.0.0.1:<port>`` that the driver
exposes once the phone is running.
"""

from __future__ import annotations

import abc
import logging
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class EmulatorInstance:
    """Driver's view of one phone."""

    name: str
    index: int
    status: str  # stopped | starting | running | stopping | crashed
    adb_port: int | None = None
    pid: int | None = None


@dataclass
class LaunchOptions:
    """Per-phone runtime tweaks the driver should apply before starting."""

    resolution: str = "1080x1920"
    dpi: int = 420
    cpu: int = 2
    ram_mb: int = 4096
    proxy: str | None = None  # "host:port" — only used for system-http mode
    locale: str | None = None
    timezone: str | None = None
    # GPS lat/long applied via adb after boot, not by the driver itself.
    imei: str | None = None
    manufacturer: str | None = None
    model: str | None = None
    android_id: str | None = None
    mac: str | None = None


# Template instance names. The backend auto-creates + snapshots these on
# first real-driver boot (see core.templates). Clones preserve all
# attributes but reset volatile state — "clean phone, already past setup"
# (configured) vs. "clean phone, first-boot wizard shows" (factory).
TEMPLATE_FACTORY_NAME = "_droidfarm_template_factory"
TEMPLATE_CONFIGURED_NAME = "_droidfarm_template_configured"


class Driver(abc.ABC):
    """Contract every emulator driver must satisfy."""

    # True when the phones this driver boots are reachable via adb on
    # their ``adb_port``. MockDriver sets this to False so geo-spoof, APK
    # install, etc. degrade gracefully on dev VMs without adb.
    supports_adb: bool = True

    @abc.abstractmethod
    def list(self) -> list[EmulatorInstance]: ...

    @abc.abstractmethod
    def create(self, name: str, opts: LaunchOptions) -> EmulatorInstance: ...

    @abc.abstractmethod
    def clone(self, name: str, source: str, opts: LaunchOptions) -> EmulatorInstance:
        """Create a new instance by copying an existing one.

        Used for factory-clean phones: we keep a hidden template instance
        that's already set up (or untouched for the 'factory' flavor) and
        clone from it so every new phone starts identical + disposable.
        """

    @abc.abstractmethod
    def destroy(self, name: str) -> None: ...

    @abc.abstractmethod
    def start(self, name: str, opts: LaunchOptions) -> EmulatorInstance: ...

    @abc.abstractmethod
    def stop(self, name: str) -> None: ...

    @abc.abstractmethod
    def modify(self, name: str, opts: LaunchOptions) -> None: ...

    @abc.abstractmethod
    def install_apk(self, name: str, apk_path: Path) -> None: ...

    def set_gps(self, name: str, latitude: float, longitude: float) -> None:
        """Best-effort GPS spoof. Default no-op; real drivers override."""
        return

    def backup_instance(self, name: str) -> Path | None:
        """Produce a portable backup (e.g. .ldbk) of the phone's disk
        so the farm export can carry it. Default: not supported."""
        return None

    def screencap(self, name: str, adb_port: int | None) -> bytes:
        """Return a PNG of the phone's current framebuffer, or raise if
        unavailable (not running, driver can't). Override in subclasses."""
        raise NotImplementedError("screencap not supported by this driver")


def _mock_png(width: int, height: int, color: tuple[int, int, int]) -> bytes:
    """Minimal flat-color PNG encoder — used by MockDriver so the
    screenshot endpoint still returns a valid image on non-LDPlayer hosts."""
    import struct
    import zlib

    r, g, b = color
    scanline = b"\x00" + bytes([r, g, b]) * width
    raw = scanline * height

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data))
        )

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    idat = zlib.compress(raw)
    return sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")


# ---------- LDPlayer (real Windows driver) ----------

class LDPlayerDriver(Driver):
    """Drives LDPlayer 9 via the bundled ``ldconsole.exe`` CLI.

    ldconsole commands used (see LDPlayer SDK docs):
      list2                                 → index,name,top_handle,bind_handle,isrunning,pid,pid_vbox,width,height,dpi
      add     --name X
      remove  --name X
      launch  --name X
      quit    --name X
      modify  --name X --resolution WxH --dpi D --cpu N --memory M
      adb     --name X --command "..."
      installapp --name X --filename "C:\\path\\a.apk"

    LDPlayer assigns ADB ports starting at 5555 + 2*index, so we derive the
    adb connection string deterministically.
    """

    def __init__(self, ldconsole_path: str):
        self.ldconsole = ldconsole_path

    def _run(self, *args: str, timeout: float = 60.0) -> str:
        cmd = [self.ldconsole, *args]
        logger.debug("ldconsole %s", " ".join(args))
        r = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if r.returncode != 0:
            raise RuntimeError(f"ldconsole {args[0]} failed: {r.stderr or r.stdout}")
        return r.stdout

    # ------------------------------------------------------------------

    def list(self) -> list[EmulatorInstance]:
        out = self._run("list2")
        instances: list[EmulatorInstance] = []
        for line in out.splitlines():
            parts = line.split(",")
            if len(parts) < 7:
                continue
            try:
                idx = int(parts[0])
                name = parts[1]
                is_running = parts[4] == "1"
                pid = int(parts[5]) if parts[5] and parts[5] != "-1" else None
            except ValueError:
                continue
            instances.append(
                EmulatorInstance(
                    name=name,
                    index=idx,
                    status="running" if is_running else "stopped",
                    adb_port=5555 + 2 * idx if is_running else None,
                    pid=pid,
                )
            )
        return instances

    def _find(self, name: str) -> EmulatorInstance | None:
        return next((i for i in self.list() if i.name == name), None)

    def create(self, name: str, opts: LaunchOptions) -> EmulatorInstance:
        self._run("add", "--name", name)
        self.modify(name, opts)
        inst = self._find(name)
        if inst is None:
            raise RuntimeError(f"created {name} but ldconsole didn't list it")
        return inst

    def clone(self, name: str, source: str, opts: LaunchOptions) -> EmulatorInstance:
        # ldconsole copy --name NEW --from SRC
        self._run("copy", "--name", name, "--from", source)
        self.modify(name, opts)
        inst = self._find(name)
        if inst is None:
            raise RuntimeError(f"cloned {name} from {source} but ldconsole didn't list it")
        return inst

    def destroy(self, name: str) -> None:
        self._run("remove", "--name", name)

    def modify(self, name: str, opts: LaunchOptions) -> None:
        w, _, h = opts.resolution.partition("x")
        args = [
            "modify",
            "--name", name,
            "--resolution", f"{w},{h},{opts.dpi}",
            "--cpu", str(opts.cpu),
            "--memory", str(opts.ram_mb),
        ]
        if opts.imei:
            args += ["--imei", opts.imei]
        if opts.manufacturer:
            args += ["--manufacturer", opts.manufacturer]
        if opts.model:
            args += ["--model", opts.model]
        self._run(*args)

    def start(self, name: str, opts: LaunchOptions) -> EmulatorInstance:
        self._run("launch", "--name", name)
        # Poll for up to 90s until ldconsole reports "running".
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            inst = self._find(name)
            if inst and inst.status == "running":
                return inst
            time.sleep(2)
        raise TimeoutError(f"{name} did not reach 'running' within 90s")

    def stop(self, name: str) -> None:
        self._run("quit", "--name", name)

    def install_apk(self, name: str, apk_path: Path) -> None:
        self._run("installapp", "--name", name, "--filename", str(apk_path), timeout=600)

    def set_gps(self, name: str, latitude: float, longitude: float) -> None:
        """Push a fake GPS fix directly to the LDPlayer GPS provider.

        ldconsole has native support for this: ``locate --name X --LLI lng,lat``.
        Apps consuming Fused Location / Google Play Services pick it up
        without needing a mock-location app.
        """
        self._run("locate", "--name", name, "--LLI", f"{longitude},{latitude}")

    def screencap(self, name: str, adb_port: int | None) -> bytes:
        """PNG framebuffer via adb exec-out. Fast enough for ~1-2fps
        thumbnails in the grid."""
        if adb_port is None:
            raise RuntimeError(f"{name} is not running — no adb port")
        from droidfarm.core import adb as adb_mod

        serial = f"127.0.0.1:{adb_port}"
        adb_mod.connect(serial)
        return adb_mod.screencap_png(serial)


# ---------- Mock driver (Linux dev / CI) ----------

class MockDriver(Driver):
    """Keeps an in-memory registry of fake phones so the API works end-to-end
    on machines without LDPlayer (Linux dev boxes, CI)."""

    supports_adb: bool = False

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._phones: dict[str, EmulatorInstance] = {}
        self._next_index = 0

    # ------------------------------------------------------------------

    def list(self) -> list[EmulatorInstance]:
        with self._lock:
            return list(self._phones.values())

    def create(self, name: str, opts: LaunchOptions) -> EmulatorInstance:
        with self._lock:
            if name in self._phones:
                return self._phones[name]
            idx = self._next_index
            self._next_index += 1
            inst = EmulatorInstance(name=name, index=idx, status="stopped")
            self._phones[name] = inst
            logger.info("[mock] created %s (index=%d)", name, idx)
            return inst

    def clone(self, name: str, source: str, opts: LaunchOptions) -> EmulatorInstance:
        with self._lock:
            if name in self._phones:
                return self._phones[name]
            if source not in self._phones:
                # For the mock driver we treat a missing template as "auto-created"
                # so tests don't have to construct it explicitly.
                src_idx = self._next_index
                self._next_index += 1
                self._phones[source] = EmulatorInstance(
                    name=source, index=src_idx, status="stopped",
                )
            idx = self._next_index
            self._next_index += 1
            inst = EmulatorInstance(name=name, index=idx, status="stopped")
            self._phones[name] = inst
            logger.info("[mock] cloned %s from %s (index=%d)", name, source, idx)
            return inst

    def destroy(self, name: str) -> None:
        with self._lock:
            self._phones.pop(name, None)
            logger.info("[mock] destroyed %s", name)

    def modify(self, name: str, opts: LaunchOptions) -> None:
        logger.info("[mock] modify %s %s", name, opts)

    def start(self, name: str, opts: LaunchOptions) -> EmulatorInstance:
        with self._lock:
            inst = self._phones.get(name)
            if inst is None:
                raise KeyError(name)
            inst.status = "running"
            inst.adb_port = 5555 + 2 * inst.index
            inst.pid = 10000 + inst.index
            logger.info("[mock] started %s on adb port %d", name, inst.adb_port)
            return inst

    def stop(self, name: str) -> None:
        with self._lock:
            inst = self._phones.get(name)
            if inst is None:
                return
            inst.status = "stopped"
            inst.adb_port = None
            inst.pid = None
            logger.info("[mock] stopped %s", name)

    def install_apk(self, name: str, apk_path: Path) -> None:
        logger.info("[mock] install %s on %s", apk_path, name)

    def set_gps(self, name: str, latitude: float, longitude: float) -> None:
        logger.info("[mock] set_gps %s lat=%s lon=%s", name, latitude, longitude)

    def screencap(self, name: str, adb_port: int | None) -> bytes:
        # Deterministic per-phone color so each mock tile looks distinct.
        inst = self._phones.get(name)
        idx = inst.index if inst else 0
        r = 30 + (idx * 37) % 80
        g = 50 + (idx * 53) % 80
        b = 60 + (idx * 71) % 80
        return _mock_png(270, 480, (r, g, b))


# ---------- Selection ----------

_driver_lock = threading.Lock()
_driver_instance: Driver | None = None


def get_driver() -> Driver:
    """Lazily construct the correct driver for the current environment."""
    global _driver_instance
    with _driver_lock:
        if _driver_instance is not None:
            return _driver_instance
        from droidfarm.config import SETTINGS

        if SETTINGS.mock_driver or SETTINGS.ldconsole_path is None:
            _driver_instance = MockDriver()
        else:
            _driver_instance = LDPlayerDriver(SETTINGS.ldconsole_path)
        return _driver_instance


# Test helper — never called in production.
def _reset_for_tests() -> None:
    global _driver_instance
    with _driver_lock:
        _driver_instance = None
