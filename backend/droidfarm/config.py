"""Runtime configuration — paths, ports, driver selection."""

from __future__ import annotations

import os
import platform
from dataclasses import dataclass
from pathlib import Path


def _default_data_dir() -> Path:
    env = os.environ.get("DROIDFARM_DATA_DIR")
    if env:
        return Path(env).expanduser().resolve()
    # On Windows, %APPDATA%\DroidFarm is the convention.
    if platform.system() == "Windows":
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / "DroidFarm"
    return Path.home() / ".droidfarm"


def _default_ldconsole() -> str | None:
    env = os.environ.get("DROIDFARM_LDCONSOLE")
    if env:
        return env
    # Default install paths for LDPlayer 9 on Windows. We scan a handful of
    # common drives + Program Files variants — users routinely install
    # LDPlayer to D:\ to keep the SSD free.
    drives = ["C:", "D:", "E:"]
    suffixes = [
        r"\LDPlayer\LDPlayer9\ldconsole.exe",
        r"\Program Files\LDPlayer\LDPlayer9\ldconsole.exe",
        r"\Program Files (x86)\LDPlayer\LDPlayer9\ldconsole.exe",
        r"\LDPlayer9\ldconsole.exe",
    ]
    for d in drives:
        for s in suffixes:
            p = d + s
            if Path(p).exists():
                return p
    return None


def _default_adb() -> str:
    env = os.environ.get("DROIDFARM_ADB")
    if env:
        return env
    if platform.system() == "Windows":
        for p in (
            r"C:\LDPlayer\LDPlayer9\adb.exe",
            r"C:\Android\platform-tools\adb.exe",
        ):
            if Path(p).exists():
                return p
    # macOS / Linux: prefer the SDK-bundled adb if a SDK was detected.
    sdk = _default_android_sdk()
    if sdk:
        candidate = Path(sdk) / "platform-tools" / "adb"
        if candidate.exists():
            return str(candidate)
    return "adb"


def _default_android_sdk() -> str | None:
    """Locate Google's Android SDK (cmdline-tools + platform-tools + emulator).

    Used by ``AndroidEmulatorDriver`` on macOS, Linux, and Windows-without-LDPlayer.
    Honours the standard Android env vars first, then falls back to the
    platform-conventional location (``~/Library/Android/sdk`` on macOS,
    ``~/Android/Sdk`` on Linux, ``%LOCALAPPDATA%\\Android\\Sdk`` on Windows,
    plus the ``mac/sdk/`` location populated by ``mac/setup.sh``).
    """
    env = os.environ.get("DROIDFARM_ANDROID_SDK") or os.environ.get(
        "ANDROID_SDK_ROOT"
    ) or os.environ.get("ANDROID_HOME")
    candidates: list[Path] = []
    if env:
        candidates.append(Path(env).expanduser())
    system = platform.system()
    if system == "Darwin":
        candidates.append(Path.home() / "Library" / "Android" / "sdk")
        candidates.append(Path.home() / ".droidfarm" / "android-sdk")
        candidates.append(Path("/opt/android-sdk"))
    elif system == "Linux":
        candidates.append(Path.home() / "Android" / "Sdk")
        candidates.append(Path.home() / ".droidfarm" / "android-sdk")
        candidates.append(Path("/opt/android-sdk"))
    elif system == "Windows":
        local = os.environ.get("LOCALAPPDATA")
        if local:
            candidates.append(Path(local) / "Android" / "Sdk")
        candidates.append(Path("C:/Android/Sdk"))
    for c in candidates:
        # An SDK root is recognized by having either platform-tools/adb or
        # the cmdline-tools/latest layout produced by sdkmanager.
        adb = c / ("platform-tools/adb.exe" if system == "Windows" else "platform-tools/adb")
        if adb.exists():
            return str(c)
    return None


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    db_path: Path
    apks_dir: Path
    logs_dir: Path
    host: str
    port: int
    dev_mode: bool
    # LDPlayer integration (Windows)
    ldconsole_path: str | None
    # Google Android SDK root (macOS / Linux / Windows fallback)
    android_sdk_path: str | None
    adb_path: str
    # Force the mock driver (for CI / Linux dev). When unset we auto-detect.
    mock_driver: bool

    @classmethod
    def load(cls) -> Settings:
        data = _default_data_dir()
        ldconsole = _default_ldconsole()
        android_sdk = _default_android_sdk()
        # Auto-enable mock driver whenever NEITHER backend is available.
        # If the user has LDPlayer (Windows) or an Android SDK (Mac / Linux),
        # pick a real driver. Otherwise fall back to mock.
        mock_env = os.environ.get("DROIDFARM_MOCK")
        if mock_env is not None:
            mock = mock_env == "1"
        else:
            mock = ldconsole is None and android_sdk is None

        settings = cls(
            data_dir=data,
            db_path=data / "droidfarm.sqlite",
            apks_dir=data / "apks",
            logs_dir=data / "logs",
            host=os.environ.get("DROIDFARM_HOST", "127.0.0.1"),
            port=int(os.environ.get("DROIDFARM_PORT", "7870")),
            dev_mode=os.environ.get("DROIDFARM_DEV", "0") == "1",
            ldconsole_path=ldconsole,
            android_sdk_path=android_sdk,
            adb_path=_default_adb(),
            mock_driver=mock,
        )
        for p in (settings.data_dir, settings.apks_dir, settings.logs_dir):
            p.mkdir(parents=True, exist_ok=True)
        return settings


SETTINGS = Settings.load()
