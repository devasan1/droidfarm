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
    return "adb"


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    db_path: Path
    apks_dir: Path
    logs_dir: Path
    host: str
    port: int
    dev_mode: bool
    # LDPlayer integration
    ldconsole_path: str | None
    adb_path: str
    # Force the mock driver (for CI / Linux dev). When unset we auto-detect.
    mock_driver: bool

    @classmethod
    def load(cls) -> Settings:
        data = _default_data_dir()
        ldconsole = _default_ldconsole()
        # Auto-enable mock driver whenever LDPlayer isn't installed (e.g. on
        # Linux dev boxes or Windows without LDPlayer yet).
        mock_env = os.environ.get("DROIDFARM_MOCK")
        if mock_env is not None:
            mock = mock_env == "1"
        else:
            mock = ldconsole is None

        settings = cls(
            data_dir=data,
            db_path=data / "droidfarm.sqlite",
            apks_dir=data / "apks",
            logs_dir=data / "logs",
            host=os.environ.get("DROIDFARM_HOST", "127.0.0.1"),
            port=int(os.environ.get("DROIDFARM_PORT", "7870")),
            dev_mode=os.environ.get("DROIDFARM_DEV", "0") == "1",
            ldconsole_path=ldconsole,
            adb_path=_default_adb(),
            mock_driver=mock,
        )
        for p in (settings.data_dir, settings.apks_dir, settings.logs_dir):
            p.mkdir(parents=True, exist_ok=True)
        return settings


SETTINGS = Settings.load()
