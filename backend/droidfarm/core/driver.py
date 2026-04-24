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


class Driver(abc.ABC):
    """Contract every emulator driver must satisfy."""

    @abc.abstractmethod
    def list(self) -> list[EmulatorInstance]: ...

    @abc.abstractmethod
    def create(self, name: str, opts: LaunchOptions) -> EmulatorInstance: ...

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


# ---------- Mock driver (Linux dev / CI) ----------

class MockDriver(Driver):
    """Keeps an in-memory registry of fake phones so the API works end-to-end
    on machines without LDPlayer (Linux dev boxes, CI)."""

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
