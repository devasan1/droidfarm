"""APK library: upload, list, delete, catalog-fetch."""

from __future__ import annotations

import hashlib
import shutil
import urllib.request
import urllib.parse
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select

from droidfarm.config import SETTINGS
from droidfarm.core.app_catalog import list_catalog, get_entry
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


# =========================================================================
# Catalog — curated list of common apps users want to pre-load.
# =========================================================================

@router.get("/catalog")
def get_catalog() -> list[dict]:
    """Curated list of common apps (TikTok, Instagram, YouTube, etc).
    The UI shows this as an "Add from catalog" picker."""
    catalog = list_catalog()
    # Mark which entries the user already has in their library (by package).
    with session_scope() as s:
        existing = {
            (a.package_name or "").lower()
            for a in s.execute(select(Apk)).scalars().all()
            if a.package_name
        }
    for entry in catalog:
        entry["installed"] = entry["package"].lower() in existing
    return catalog


class FetchCatalogIn(BaseModel):
    url: str  # direct-download URL to the APK (user-provided)
    filename: str | None = None


@router.post("/catalog/{slug}/fetch", response_model=ApkOut, status_code=201)
def fetch_catalog_apk(slug: str, payload: FetchCatalogIn) -> ApkOut:
    """Download a user-provided APK URL into the library, tagged with
    the catalog entry's package name. Used by the "Fetch from URL"
    button on catalog tiles.

    We don't scrape APKMirror directly — that's fragile and against
    their ToS. The user pastes a direct-download URL they got from the
    catalog entry's source page, and we fetch it server-side.
    """
    entry = get_entry(slug)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"unknown catalog slug: {slug}")

    parsed = urllib.parse.urlparse(payload.url)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(status_code=400, detail="url must be http:// or https://")

    filename = payload.filename or f"{slug}.apk"
    if not filename.lower().endswith(".apk"):
        filename += ".apk"
    dest = SETTINGS.apks_dir / filename

    try:
        req = urllib.request.Request(
            payload.url,
            headers={
                "User-Agent": "DroidFarm/1.0 (+https://github.com/devasan1/droidfarm)",
            },
        )
        with urllib.request.urlopen(req, timeout=120) as resp, dest.open("wb") as f:
            shutil.copyfileobj(resp, f)
    except Exception as e:
        if dest.exists():
            dest.unlink()
        raise HTTPException(
            status_code=502,
            detail=f"failed to download from {payload.url}: {e}",
        )

    sha = hashlib.sha256(dest.read_bytes()).hexdigest()
    with session_scope() as s:
        apk = Apk(
            filename=filename,
            package_name=entry.package,
            size_bytes=dest.stat().st_size,
            sha256=sha,
        )
        s.add(apk)
        s.flush()
        return _apk_to_out(apk)
