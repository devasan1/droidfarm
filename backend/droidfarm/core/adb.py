"""Thin wrapper around the ``adb`` binary for per-phone commands."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from droidfarm.config import SETTINGS

logger = logging.getLogger(__name__)


class ADBError(RuntimeError):
    pass


def _run(
    serial: str | None,
    *args: str,
    timeout: float = 60.0,
    check: bool = True,
) -> str:
    cmd = [SETTINGS.adb_path]
    if serial:
        cmd += ["-s", serial]
    cmd.extend(args)
    logger.debug("adb %s", " ".join(cmd[1:]))
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if check and r.returncode != 0:
        raise ADBError(f"adb {args[0]} failed: {(r.stderr or r.stdout).strip()}")
    return r.stdout


def connect(host_port: str) -> None:
    """``adb connect 127.0.0.1:5555`` etc. Idempotent."""
    _run(None, "connect", host_port, check=False)


def disconnect(host_port: str) -> None:
    _run(None, "disconnect", host_port, check=False)


def shell(serial: str, *args: str, timeout: float = 60.0) -> str:
    return _run(serial, "shell", *args, timeout=timeout)


def screencap_png(serial: str, timeout: float = 8.0) -> bytes:
    """Capture the framebuffer as a PNG.

    Uses ``adb exec-out screencap -p`` which avoids the
    \\r\\n-to-\\n mangling of plain ``adb shell`` on Windows.
    """
    cmd = [SETTINGS.adb_path, "-s", serial, "exec-out", "screencap", "-p"]
    r = subprocess.run(cmd, capture_output=True, timeout=timeout)
    if r.returncode != 0:
        raise ADBError(f"screencap failed: {r.stderr.decode(errors='replace').strip()}")
    if not r.stdout.startswith(b"\x89PNG"):
        raise ADBError("screencap returned a non-PNG payload")
    return r.stdout


def input_tap(serial: str, x: int, y: int) -> None:
    shell(serial, "input", "tap", str(int(x)), str(int(y)))


def input_swipe(
    serial: str, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 100
) -> None:
    shell(
        serial,
        "input",
        "swipe",
        str(int(x1)),
        str(int(y1)),
        str(int(x2)),
        str(int(y2)),
        str(int(duration_ms)),
    )


def input_text(serial: str, text: str) -> None:
    """Send literal text to whatever view has focus. Spaces are encoded
    as %s per adb convention."""
    encoded = text.replace(" ", "%s")
    shell(serial, "input", "text", encoded)


def input_keyevent(serial: str, keycode: str | int) -> None:
    shell(serial, "input", "keyevent", str(keycode))


def install(serial: str, apk_path: Path, reinstall: bool = True) -> None:
    args = ["install"]
    if reinstall:
        args.append("-r")
    args.append(str(apk_path))
    _run(serial, *args, timeout=600)


def set_system_property(serial: str, key: str, value: str) -> None:
    shell(serial, "setprop", key, value)


def set_timezone(serial: str, tz: str) -> None:
    """e.g. 'America/Los_Angeles'. Changes persist across reboots."""
    shell(serial, "su", "-c", f"setprop persist.sys.timezone {tz}")


def set_locale(serial: str, locale: str) -> None:
    """e.g. 'en-US', 'de-DE'."""
    lang, _, region = locale.replace("_", "-").partition("-")
    shell(serial, "setprop", "persist.sys.language", lang)
    if region:
        shell(serial, "setprop", "persist.sys.country", region)
    shell(serial, "setprop", "persist.sys.locale", f"{lang}-{region}" if region else lang)


def set_http_proxy(serial: str, host_port: str | None) -> None:
    """System HTTP proxy. Many apps ignore this (TLS-pinned) — prefer
    tun2socks for reliable routing; this is for quick manual tests."""
    if host_port:
        shell(serial, "settings", "put", "global", "http_proxy", host_port)
    else:
        shell(serial, "settings", "put", "global", "http_proxy", ":0")


def set_mock_location(serial: str, lat: float, lon: float) -> None:
    """Enable mock-location + broadcast coordinates for apps that query
    LocationManager directly (secondary layer — the LDPlayer driver's
    native `locate` command is the primary GPS source)."""
    # Grant mock-location permission to the shell so the next line works
    # on stock AOSP builds. Some emulators expose this only via 'su'.
    try:
        shell(serial, "appops", "set", "com.android.shell",
              "android:mock_location", "allow")
    except ADBError as e:
        logger.debug("appops set mock_location failed (ok on LDPlayer): %s", e)
    # Modern API (cmd location) — available on Android 9+
    try:
        shell(serial, "cmd", "location", "set-location-enabled", "true")
    except ADBError:
        pass
    # Broadcast for a bundled mock-location helper app (we auto-install
    # one during the configured-template prep). Safe no-op if absent.
    shell(serial, "am", "broadcast", "-a", "com.droidfarm.SET_LOCATION",
          "--ef", "lat", str(lat), "--ef", "lon", str(lon))


def wait_for_boot(serial: str, timeout_s: float = 180.0) -> bool:
    """Block until ``sys.boot_completed=1``. Returns True on success."""
    import time

    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            out = shell(serial, "getprop", "sys.boot_completed", timeout=10).strip()
            if out == "1":
                return True
        except ADBError:
            pass
        time.sleep(3)
    return False
