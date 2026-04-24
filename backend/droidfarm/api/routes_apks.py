"""APK library: upload, list, delete."""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from sqlalchemy import select

from droidfarm.config import SETTINGS
from droidfarm.db import Apk, session_scope
from droidfarm.schemas import ApkOut

router = APIRouter(prefix="/api/apks", tags=["apks"])


def _apk_to_out(a: Apk) -> ApkOut:
    return ApkOut(
        id=a.id,
        filename=a.filename,
        package_name=a.package_name,
        version_name=a.version_name,
        size_bytes=a.size_bytes,
        sha256=a.sha256,
        added_at=a.added_at,
    )


@router.post("", response_model=ApkOut, status_code=201)
def upload_apk(file: UploadFile = File(...)) -> ApkOut:
    if not file.filename or not file.filename.lower().endswith(".apk"):
        raise HTTPException(status_code=415, detail="expected a .apk file")
    dest: Path = SETTINGS.apks_dir / file.filename
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    sha = hashlib.sha256(dest.read_bytes()).hexdigest()
    with session_scope() as s:
        apk = Apk(
            filename=file.filename,
            size_bytes=dest.stat().st_size,
            sha256=sha,
        )
        s.add(apk)
        s.flush()
        return _apk_to_out(apk)


@router.get("", response_model=list[ApkOut])
def list_apks() -> list[ApkOut]:
    with session_scope() as s:
        return [_apk_to_out(a) for a in s.execute(select(Apk).order_by(Apk.id)).scalars().all()]


@router.delete("/{apk_id}", status_code=204)
def delete_apk(apk_id: int) -> None:
    with session_scope() as s:
        apk = s.get(Apk, apk_id)
        if apk is None:
            raise HTTPException(status_code=404, detail="apk not found")
        path = SETTINGS.apks_dir / apk.filename
        if path.exists():
            path.unlink()
        s.delete(apk)
