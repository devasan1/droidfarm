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
    return {
        "ok": True,
        "version": __version__,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "data_dir": str(SETTINGS.data_dir),
        "mock_driver": SETTINGS.mock_driver,
        "ldconsole": SETTINGS.ldconsole_path,
        "adb": shutil.which(SETTINGS.adb_path) or SETTINGS.adb_path,
    }
