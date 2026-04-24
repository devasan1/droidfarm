"""Whole-farm export and import.

Exports the SQLite DB + the APK library + templates metadata as a
single zip file, so you can move a farm between Windows VMs (or from
GCP to your laptop) in one download.

**What's NOT in the export**: the LDPlayer ``vms/`` directory (the
actual phone disks — apps installed, cookies, login sessions). Those
live in LDPlayer's install folder and can be many GBs per phone.
Instead the export carries the *DB rows* for each phone (name, proxy,
geo overrides, fingerprint, etc), so importing on a new host recreates
the phone definitions and — when they're started — re-clones fresh
emulators from the template. Running autostart phones will boot clean
after import.

If you specifically want to move the inside-phone state (apps +
cookies) too, LDPlayer has its own backup format (``ldconsole backup
--name <phone> --file <.ldbk>``); we expose that via the ``include_vm``
query parameter, which tells the backend to also dump each phone's
.ldbk into the zip. That path only works on Windows with a real
LDPlayer install — on mock / Linux / Docker it's a no-op.
"""

from __future__ import annotations

import io
import json
import logging
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from droidfarm.config import SETTINGS
from droidfarm.db import Apk, Phone, Proxy, session_scope

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/farm", tags=["farm"])


def _model_to_dict(obj) -> dict:
    """Dump a SQLAlchemy model to a plain dict (JSON-safe)."""
    d: dict = {}
    for col in obj.__table__.columns:
        val = getattr(obj, col.name)
        if isinstance(val, datetime):
            val = val.isoformat()
        d[col.name] = val
    return d


@router.get("/export")
def export_farm(include_vm: bool = False) -> StreamingResponse:
    """Stream a zip of the whole farm state.

    Zip layout:
        farm.json               — DB snapshot (phones / proxies / apks)
        apks/<filename>.apk     — every APK in the library
        templates.json          — template prep state
        README.txt              — human-readable description
        (when include_vm=1, also:)
        vms/<phone-name>.ldbk   — LDPlayer backup per phone
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # 1. DB snapshot.
        with session_scope() as s:
            phones = [
                _model_to_dict(p)
                for p in s.execute(select(Phone)).scalars().all()
            ]
            proxies = [
                _model_to_dict(p)
                for p in s.execute(select(Proxy)).scalars().all()
            ]
            apks = [
                _model_to_dict(a)
                for a in s.execute(select(Apk)).scalars().all()
            ]
        snapshot = {
            "schema_version": 1,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "phones": phones,
            "proxies": proxies,
            "apks": apks,
        }
        zf.writestr("farm.json", json.dumps(snapshot, indent=2, default=str))

        # 2. APK bytes.
        apks_dir: Path = SETTINGS.apks_dir
        for apk in apks:
            apk_path = apks_dir / apk["filename"]
            if apk_path.exists():
                zf.write(apk_path, f"apks/{apk['filename']}")

        # 3. Templates metadata (if present).
        tpl_path = SETTINGS.data_dir / "templates.json"
        if tpl_path.exists():
            zf.write(tpl_path, "templates.json")

        # 4. Optional per-phone LDPlayer backup.
        if include_vm:
            try:
                from droidfarm.core.driver import get_driver
                driver = get_driver()
                if getattr(driver, "supports_adb", True):
                    for phone in phones:
                        try:
                            backup = driver.backup_instance(phone["name"])
                            if backup and Path(backup).exists():
                                zf.write(
                                    backup, f"vms/{phone['name']}.ldbk"
                                )
                        except Exception as e:
                            logger.warning(
                                "ldbk export for %s failed: %s",
                                phone["name"],
                                e,
                            )
            except Exception as e:
                logger.warning("include_vm export failed overall: %s", e)

        # 5. Human-readable README.
        zf.writestr(
            "README.txt",
            (
                "DroidFarm export\n"
                f"Exported at: {snapshot['exported_at']}\n"
                f"Phones: {len(phones)}  Proxies: {len(proxies)}  "
                f"APKs: {len(apks)}\n\n"
                "Restore with:  POST /api/farm/import  (multipart file=zip)\n"
                "or:  droidfarm-cli import <this-zip>  (coming soon)\n\n"
                "Note: inside-phone state (installed apps, cookies, "
                "logins) is NOT included unless this export was made "
                "with include_vm=1 on a Windows host with LDPlayer.\n"
            ),
        )

    buf.seek(0)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = f"droidfarm-{stamp}.zip"
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/import")
async def import_farm(
    file: UploadFile = File(...),
    merge: bool = True,
) -> dict:
    """Restore a farm zip.

    Default ``merge=True`` only adds missing rows (by name for phones /
    proxies, by sha256 for APKs) — safe to run against a populated
    DroidFarm without stomping existing data.

    ``merge=False`` wipes existing phones / proxies / apks first. Not
    reversible; confirm in the UI before calling.
    """
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(
            status_code=415, detail="expected a .zip from /api/farm/export"
        )

    # Stash upload to a temp file so zipfile can seek.
    tmp = SETTINGS.data_dir / "_incoming_import.zip"
    with tmp.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    try:
        with zipfile.ZipFile(tmp, "r") as zf:
            if "farm.json" not in zf.namelist():
                raise HTTPException(
                    status_code=400, detail="zip missing farm.json"
                )
            snapshot = json.loads(zf.read("farm.json"))

            # Restore APK bytes first (phones reference them).
            apks_dir: Path = SETTINGS.apks_dir
            apks_dir.mkdir(parents=True, exist_ok=True)
            restored_files = 0
            for info in zf.infolist():
                if info.filename.startswith("apks/") and not info.is_dir():
                    dest = apks_dir / Path(info.filename).name
                    with zf.open(info) as src, dest.open("wb") as out:
                        shutil.copyfileobj(src, out)
                    restored_files += 1

            created = {"phones": 0, "proxies": 0, "apks": 0}
            skipped = {"phones": 0, "proxies": 0, "apks": 0}

            with session_scope() as s:
                if not merge:
                    # Purge existing rows so we start clean.
                    for cls in (Phone, Proxy, Apk):
                        for row in s.execute(select(cls)).scalars().all():
                            s.delete(row)
                    s.flush()

                existing_proxy_hp = {
                    (p.host, p.port)
                    for p in s.execute(select(Proxy)).scalars().all()
                }
                for row in snapshot.get("proxies", []):
                    if (row["host"], row["port"]) in existing_proxy_hp:
                        skipped["proxies"] += 1
                        continue
                    data = {k: v for k, v in row.items() if k != "id"}
                    s.add(Proxy(**data))
                    created["proxies"] += 1

                existing_apk_sha = {
                    a.sha256
                    for a in s.execute(select(Apk)).scalars().all()
                }
                for row in snapshot.get("apks", []):
                    if row.get("sha256") in existing_apk_sha:
                        skipped["apks"] += 1
                        continue
                    data = {k: v for k, v in row.items() if k != "id"}
                    s.add(Apk(**data))
                    created["apks"] += 1

                existing_phone_names = {
                    p.name
                    for p in s.execute(select(Phone)).scalars().all()
                }
                for row in snapshot.get("phones", []):
                    if row["name"] in existing_phone_names:
                        skipped["phones"] += 1
                        continue
                    data = {
                        k: v
                        for k, v in row.items()
                        # drop fk / server-managed fields; the imported
                        # phone will re-attach proxies by host/port on
                        # next start.
                        if k not in {"id", "proxy_id", "ldplayer_index"}
                    }
                    s.add(Phone(**data))
                    created["phones"] += 1

            # Templates state — if empty locally, pick up from import.
            tpl = SETTINGS.data_dir / "templates.json"
            if "templates.json" in zf.namelist() and not tpl.exists():
                with zf.open("templates.json") as src, tpl.open("wb") as out:
                    shutil.copyfileobj(src, out)

    finally:
        try:
            tmp.unlink()
        except Exception:
            pass

    return {
        "ok": True,
        "merge": merge,
        "created": created,
        "skipped": skipped,
        "apk_files_restored": restored_files,
        "exported_at": snapshot.get("exported_at"),
    }
