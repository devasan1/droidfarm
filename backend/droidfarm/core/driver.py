"""Abstraction over the Android-emulator engine.

Three implementations:

* ``LDPlayerDriver`` wraps ``ldconsole.exe`` on Windows.
* ``AndroidEmulatorDriver`` wraps Google's stock ``emulator`` + ``avdmanager``
  CLIs from the Android SDK. Works on macOS (Apple Silicon native via HVF),
  Linux (with KVM), and Windows (with HAXM/WHPX). Primary path for the M-series
  Mac story.
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
import os
import re
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
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


# ---------- Google Android Emulator (cross-platform) ----------


class AndroidEmulatorDriver(Driver):
    """Drives Google's stock Android emulator (qemu-based) via ``avdmanager``
    and ``emulator``.

    This is the cross-platform driver — works on:

    * **macOS** (Apple Silicon: arm64 system images run native via HVF; very fast)
    * **Linux** (uses KVM; needs ``/dev/kvm`` accessible)
    * **Windows** (uses WHPX/HAXM; LDPlayer is preferred there for performance)

    AVDs live under ``$ANDROID_AVD_HOME`` (defaults to ``~/.android/avd``).
    Each AVD is a directory of the form ``<name>.avd/`` plus a sibling
    ``<name>.ini`` pointer file. We "clone" by copying the directory and
    rewriting ``config.ini`` paths.

    Per-instance ports are allocated deterministically from a stable index
    (5554+2*i console, 5555+2*i adb) so a phone always lands on the same
    port across runs of the backend.
    """

    # Adb port lower bound. Convention is 5555 for emulator-5554, then steps
    # of 2. We start at index 0 ⇒ adb_port 5555.
    _ADB_PORT_BASE = 5555

    def __init__(
        self,
        sdk_root: Path,
        avd_home: Path | None = None,
        system_image: str | None = None,
    ) -> None:
        self.sdk_root = Path(sdk_root)
        self.avd_home = Path(avd_home) if avd_home else Path.home() / ".android" / "avd"
        # Default arm64 image on Apple Silicon Macs; x86_64 on Intel.
        # The setup script picks one and pins it here.
        self.system_image = system_image or _default_system_image()

        self._emulator = self._find_tool("emulator/emulator", "emulator")
        self._avdmanager = self._find_tool("cmdline-tools/latest/bin/avdmanager", "avdmanager")
        self._adb = self._find_tool("platform-tools/adb", "adb")
        self._lock = threading.Lock()
        self._procs: dict[str, subprocess.Popen[bytes]] = {}
        self._index_map: dict[str, int] = {}

    # ------------------------------------------------------------------
    # Tool discovery

    def _find_tool(self, sdk_relpath: str, exe_name: str) -> str:
        """Locate an SDK tool. Tries ``<sdk_root>/<sdk_relpath>`` first, then PATH."""
        ext = ".exe" if os.name == "nt" else ""
        bat = ".bat" if os.name == "nt" else ""

        candidates = [
            self.sdk_root / f"{sdk_relpath}{ext}",
            self.sdk_root / f"{sdk_relpath}{bat}",
        ]
        # avdmanager / sdkmanager on Windows are .bat; emulator/adb are .exe.
        # Use is_file() so we never accidentally return a directory whose name
        # collides with the binary (e.g. <sdk_root>/emulator is a dir, the
        # binary is <sdk_root>/emulator/emulator).
        for c in candidates:
            if c.is_file():
                return str(c)

        which = shutil.which(exe_name)
        if which:
            return which

        raise FileNotFoundError(
            f"Could not locate {exe_name} under {self.sdk_root} or on PATH. "
            f"Re-run the platform setup script."
        )

    # ------------------------------------------------------------------
    # Subprocess helpers

    def _run(self, cmd: list[str], *, timeout: float = 60.0, check: bool = True,
             env_overrides: dict[str, str] | None = None) -> str:
        env = os.environ.copy()
        env["ANDROID_SDK_ROOT"] = str(self.sdk_root)
        env["ANDROID_HOME"] = str(self.sdk_root)  # legacy alias still used by some tools
        env["ANDROID_AVD_HOME"] = str(self.avd_home)
        if env_overrides:
            env.update(env_overrides)
        logger.debug("emulator-driver run: %s", cmd)
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                           check=False, env=env)
        if check and r.returncode != 0:
            raise RuntimeError(
                f"{Path(cmd[0]).name} {cmd[1] if len(cmd) > 1 else ''} failed "
                f"(exit {r.returncode}): {r.stderr.strip() or r.stdout.strip()}"
            )
        return r.stdout

    # ------------------------------------------------------------------
    # AVD-directory utilities

    def _avd_dir(self, name: str) -> Path:
        return self.avd_home / f"{name}.avd"

    def _avd_ini(self, name: str) -> Path:
        return self.avd_home / f"{name}.ini"

    def _allocate_index(self, name: str) -> int:
        """Stable per-name index. Persisted in config.ini so reboots keep
        the same adb port for a given phone."""
        if name in self._index_map:
            return self._index_map[name]
        # Read prior index from config.ini if present.
        cfg = self._avd_dir(name) / "config.ini"
        if cfg.exists():
            for line in cfg.read_text().splitlines():
                m = re.match(r"\s*droidfarm\.index\s*=\s*(\d+)\s*$", line)
                if m:
                    idx = int(m.group(1))
                    self._index_map[name] = idx
                    return idx
        # Otherwise pick the next free slot among already-known indices.
        # Walk avd_home directly instead of calling _scan_avds() — _scan_avds
        # itself calls back into _allocate_index, so the two would recurse
        # infinitely the first time an AVD is created (config.ini doesn't yet
        # have droidfarm.index because we're in the middle of allocating it).
        used = set(self._index_map.values())
        if self.avd_home.exists():
            for ini in self.avd_home.glob("*.ini"):
                cfg2 = self._avd_dir(ini.stem) / "config.ini"
                if not cfg2.exists():
                    continue
                for line in cfg2.read_text().splitlines():
                    m = re.match(r"\s*droidfarm\.index\s*=\s*(\d+)\s*$", line)
                    if m:
                        used.add(int(m.group(1)))
        idx = 0
        while idx in used:
            idx += 1
        self._index_map[name] = idx
        return idx

    def _adb_port_for(self, idx: int) -> int:
        return self._ADB_PORT_BASE + 2 * idx

    def _console_port_for(self, idx: int) -> int:
        return self._ADB_PORT_BASE - 1 + 2 * idx

    def _read_config(self, name: str) -> dict[str, str]:
        cfg = self._avd_dir(name) / "config.ini"
        if not cfg.exists():
            return {}
        out: dict[str, str] = {}
        for line in cfg.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, _, v = line.partition("=")
                out[k.strip()] = v.strip()
        return out

    def _write_config(self, name: str, updates: dict[str, str]) -> None:
        cfg = self._avd_dir(name) / "config.ini"
        existing = self._read_config(name)
        existing.update(updates)
        # Preserve a stable key order: known-good keys first, then alphabetical.
        lines = [f"{k}={v}" for k, v in sorted(existing.items())]
        cfg.write_text("\n".join(lines) + "\n")

    def _scan_avds(self) -> list[EmulatorInstance]:
        if not self.avd_home.exists():
            return []
        out: list[EmulatorInstance] = []
        running = self._running_serials()
        for ini in sorted(self.avd_home.glob("*.ini")):
            name = ini.stem
            d = self.avd_home / f"{name}.avd"
            if not d.is_dir():
                continue
            idx = self._allocate_index(name)
            adb_port = self._adb_port_for(idx)
            is_running = f"emulator-{self._console_port_for(idx)}" in running
            status = "running" if is_running else "stopped"
            inst = EmulatorInstance(
                name=name,
                index=idx,
                status=status,
                adb_port=adb_port if is_running else None,
            )
            out.append(inst)
        return out

    def _running_serials(self) -> set[str]:
        try:
            out = self._run([self._adb, "devices"], timeout=10, check=False)
        except Exception:
            return set()
        serials: set[str] = set()
        for line in out.splitlines()[1:]:
            line = line.strip()
            if not line or "\t" not in line:
                continue
            serial, state = line.split("\t", 1)
            if state.strip() == "device":
                serials.add(serial.strip())
        return serials

    # ------------------------------------------------------------------
    # Driver API

    def list(self) -> list[EmulatorInstance]:
        return self._scan_avds()

    def _find(self, name: str) -> EmulatorInstance | None:
        return next((i for i in self._scan_avds() if i.name == name), None)

    def create(self, name: str, opts: LaunchOptions) -> EmulatorInstance:
        # avdmanager needs --abi inferred from the system image.
        m = re.search(r";([^;]+)$", self.system_image)
        abi = m.group(1) if m else "arm64-v8a"
        cmd = [
            self._avdmanager,
            "--silent",
            "create", "avd",
            "-n", name,
            "-k", self.system_image,
            "--abi", abi,
            "--device", "pixel_6",
            "--force",
        ]
        # avdmanager prompts on stdin for "Do you wish to create a custom hardware profile?".
        # Pipe "no" so it proceeds with the default.
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env={**os.environ,
                 "ANDROID_SDK_ROOT": str(self.sdk_root),
                 "ANDROID_HOME": str(self.sdk_root),
                 "ANDROID_AVD_HOME": str(self.avd_home)},
        )
        try:
            stdout, stderr = proc.communicate(input="no\n", timeout=180)
        except subprocess.TimeoutExpired:
            proc.kill()
            raise RuntimeError("avdmanager create avd timed out")
        if proc.returncode != 0:
            raise RuntimeError(f"avdmanager create avd failed: {stderr.strip() or stdout.strip()}")
        # Stamp the index + apply hardware tweaks.
        idx = self._allocate_index(name)
        self._write_config(name, {"droidfarm.index": str(idx)})
        self.modify(name, opts)
        inst = self._find(name)
        if inst is None:
            raise RuntimeError(
                f"avdmanager reported success but {name} did not appear in {self.avd_home}"
            )
        return inst

    def clone(self, name: str, source: str, opts: LaunchOptions) -> EmulatorInstance:
        src_dir = self._avd_dir(source)
        src_ini = self._avd_ini(source)
        if not src_dir.exists() or not src_ini.exists():
            raise RuntimeError(f"source AVD '{source}' not found in {self.avd_home}")
        dst_dir = self._avd_dir(name)
        dst_ini = self._avd_ini(name)
        if dst_dir.exists() or dst_ini.exists():
            raise RuntimeError(f"destination AVD '{name}' already exists")
        shutil.copytree(src_dir, dst_dir)
        # Rewrite the .ini pointer to use the new path.
        ini_text = src_ini.read_text()
        ini_text = re.sub(
            r"path=.+", f"path={dst_dir}", ini_text
        )
        ini_text = re.sub(
            r"path\.rel=.+", f"path.rel=avd/{name}.avd", ini_text
        )
        dst_ini.write_text(ini_text)
        # Clear per-instance state files that should not be shared between clones.
        for f in ("hardware-qemu.ini.lock", "*.lock"):
            for p in dst_dir.glob(f):
                try:
                    p.unlink()
                except Exception:
                    pass
        # Stamp the new clone with its own index.
        idx = self._allocate_index(name)
        self._write_config(name, {"droidfarm.index": str(idx)})
        self.modify(name, opts)
        inst = self._find(name)
        if inst is None:
            raise RuntimeError(f"clone of {source} → {name} did not appear in {self.avd_home}")
        return inst

    def destroy(self, name: str) -> None:
        # Stop first if running.
        try:
            self.stop(name)
        except Exception:
            pass
        try:
            self._run([self._avdmanager, "--silent", "delete", "avd", "-n", name], check=False)
        except Exception as e:
            logger.warning("avdmanager delete failed for %s: %s", name, e)
        # Belt and braces — also clean up files in case avdmanager is unhappy.
        d = self._avd_dir(name)
        i = self._avd_ini(name)
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)
        if i.exists():
            try:
                i.unlink()
            except Exception:
                pass
        self._index_map.pop(name, None)

    def modify(self, name: str, opts: LaunchOptions) -> None:
        updates: dict[str, str] = {}
        # Resolution: "1080x1920" → width 1080, height 1920.
        if opts.resolution:
            try:
                w, h = opts.resolution.lower().split("x")
                updates["hw.lcd.width"] = str(int(w))
                updates["hw.lcd.height"] = str(int(h))
            except Exception:
                logger.warning("ignoring malformed resolution %r", opts.resolution)
        if opts.dpi:
            updates["hw.lcd.density"] = str(int(opts.dpi))
        if opts.cpu:
            updates["hw.cpu.ncore"] = str(int(opts.cpu))
        if opts.ram_mb:
            updates["hw.ramSize"] = str(int(opts.ram_mb))
            # heap roughly 1/8 of RAM, capped at 1024.
            updates["vm.heapSize"] = str(min(1024, max(256, int(opts.ram_mb) // 8)))
        if opts.imei:
            updates["hw.gsmModem.imei"] = opts.imei
        if updates:
            self._write_config(name, updates)
        # locale / timezone / android_id / mac / manufacturer-model are
        # applied at runtime via adb after boot — see post_modify_via_adb.

    def start(self, name: str, opts: LaunchOptions) -> EmulatorInstance:
        if not self._avd_dir(name).exists():
            raise RuntimeError(f"AVD '{name}' does not exist; create it first")
        idx = self._allocate_index(name)
        port = self._console_port_for(idx)
        # Headless launch — DroidFarm renders the screen via screencap, no
        # native window needed. -no-snapshot-load avoids stale state from
        # the template; -no-snapshot-save keeps disk small.
        cmd = [
            self._emulator,
            "-avd", name,
            "-port", str(port),
            "-no-window",
            "-no-audio",
            "-no-boot-anim",
            "-no-snapshot-save",
            "-gpu", "swiftshader_indirect",
        ]
        if opts.proxy:
            cmd.extend(["-http-proxy", opts.proxy])
        env = os.environ.copy()
        env["ANDROID_SDK_ROOT"] = str(self.sdk_root)
        env["ANDROID_HOME"] = str(self.sdk_root)
        env["ANDROID_AVD_HOME"] = str(self.avd_home)
        logger.info("starting emulator %s on console port %d (adb port %d)",
                    name, port, port + 1)
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
            start_new_session=True,
        )
        with self._lock:
            self._procs[name] = proc

        # Wait for adb to see emulator-<port> as 'device'.
        deadline = time.monotonic() + 120
        serial = f"emulator-{port}"
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                raise RuntimeError(f"emulator process for {name} exited early "
                                   f"(code {proc.returncode})")
            if serial in self._running_serials():
                return EmulatorInstance(
                    name=name, index=idx, status="running",
                    adb_port=self._adb_port_for(idx), pid=proc.pid,
                )
            time.sleep(2)
        raise TimeoutError(f"{name} did not register with adb within 120s")

    def stop(self, name: str) -> None:
        idx = self._allocate_index(name)
        port = self._console_port_for(idx)
        serial = f"emulator-{port}"
        # Preferred: tell the emulator to shut down cleanly via adb.
        try:
            self._run([self._adb, "-s", serial, "emu", "kill"], timeout=15, check=False)
        except Exception:
            pass
        # Wait briefly, then SIGTERM the process if still alive.
        time.sleep(2)
        with self._lock:
            proc = self._procs.pop(name, None)
        if proc and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=10)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

    def install_apk(self, name: str, apk_path: Path) -> None:
        idx = self._allocate_index(name)
        port = self._console_port_for(idx)
        serial = f"emulator-{port}"
        if serial not in self._running_serials():
            raise RuntimeError(f"{name} is not running — start it first")
        self._run([self._adb, "-s", serial, "install", "-r", str(apk_path)],
                  timeout=600)

    def set_gps(self, name: str, latitude: float, longitude: float) -> None:
        idx = self._allocate_index(name)
        port = self._console_port_for(idx)
        serial = f"emulator-{port}"
        if serial not in self._running_serials():
            return
        # adb emu geo fix <lon> <lat>
        self._run(
            [self._adb, "-s", serial, "emu", "geo", "fix", str(longitude), str(latitude)],
            timeout=10, check=False,
        )

    def screencap(self, name: str, adb_port: int | None) -> bytes:
        if adb_port is None:
            raise RuntimeError(f"{name} is not running — no adb port")
        from droidfarm.core import adb as adb_mod

        # Google emulator's adb serial is "emulator-<console_port>" — but
        # connecting to "127.0.0.1:<adb_port>" works just the same and
        # matches how LDPlayer's screencap path goes. We use the ip:port
        # form here for symmetry with LDPlayerDriver.
        serial = f"127.0.0.1:{adb_port}"
        adb_mod.connect(serial)
        return adb_mod.screencap_png(serial)


def _default_system_image() -> str:
    """Pick a sensible default system image for the host CPU.

    Apple Silicon → arm64-v8a (native). Intel → x86_64.
    Caller can always override via DROIDFARM_ANDROID_SYSTEM_IMAGE.
    """
    env = os.environ.get("DROIDFARM_ANDROID_SYSTEM_IMAGE")
    if env:
        return env
    import platform
    machine = platform.machine().lower()
    if machine in ("arm64", "aarch64"):
        return "system-images;android-34;google_apis;arm64-v8a"
    return "system-images;android-34;google_apis;x86_64"


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
    """Lazily construct the correct driver for the current environment.

    Priority:

    1. ``DROIDFARM_MOCK=1`` → ``MockDriver`` (CI / dev override).
    2. ``DROIDFARM_DRIVER`` env var (``ldplayer`` / ``android_emulator`` / ``mock``).
    3. LDPlayer detected → ``LDPlayerDriver`` (preferred on Windows).
    4. Android SDK detected → ``AndroidEmulatorDriver`` (Mac / Linux / Windows fallback).
    5. Otherwise ``MockDriver``.
    """
    global _driver_instance
    with _driver_lock:
        if _driver_instance is not None:
            return _driver_instance
        from droidfarm.config import SETTINGS

        explicit = os.environ.get("DROIDFARM_DRIVER", "").strip().lower()

        if SETTINGS.mock_driver or explicit == "mock":
            _driver_instance = MockDriver()
        elif explicit == "ldplayer" and SETTINGS.ldconsole_path:
            _driver_instance = LDPlayerDriver(SETTINGS.ldconsole_path)
        elif explicit == "android_emulator" and SETTINGS.android_sdk_path:
            _driver_instance = AndroidEmulatorDriver(Path(SETTINGS.android_sdk_path))
        elif SETTINGS.ldconsole_path:
            _driver_instance = LDPlayerDriver(SETTINGS.ldconsole_path)
        elif SETTINGS.android_sdk_path:
            _driver_instance = AndroidEmulatorDriver(Path(SETTINGS.android_sdk_path))
        else:
            _driver_instance = MockDriver()
        return _driver_instance


# Test helper — never called in production.
def _reset_for_tests() -> None:
    global _driver_instance
    with _driver_lock:
        _driver_instance = None
