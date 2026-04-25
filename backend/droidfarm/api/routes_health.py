"""Health + environment info."""

from __future__ import annotations

import platform
import shutil
from typing import Any

from fastapi import APIRouter

from droidfarm import __version__
from droidfarm.config import SETTINGS

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
def health() -> dict[str, Any]:
    # Resolve which driver flavor is active so the UI can render the right
    # badge (LDPlayer / AndroidEmulator / Mock) and the Settings page can
    # surface the right install instructions.
    if SETTINGS.mock_driver:
        driver = "mock"
    elif SETTINGS.ldconsole_path:
        driver = "ldplayer"
    elif SETTINGS.android_sdk_path:
        driver = "android_emulator"
    else:
        driver = "mock"
    return {
        "ok": True,
        "version": __version__,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "data_dir": str(SETTINGS.data_dir),
        "mock_driver": SETTINGS.mock_driver,
        "driver": driver,
        "ldconsole": SETTINGS.ldconsole_path,
        "android_sdk": SETTINGS.android_sdk_path,
        "adb": shutil.which(SETTINGS.adb_path) or SETTINGS.adb_path,
    }
