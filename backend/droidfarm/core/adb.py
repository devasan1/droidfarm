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
    """Requires the phone to have a mock-location app installed (we ship one
    during the first-run APK preinstall list)."""
    shell(serial, "am", "broadcast", "-a", "com.droidfarm.SET_LOCATION",
          "--ef", "lat", str(lat), "--ef", "lon", str(lon))
