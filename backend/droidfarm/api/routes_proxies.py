"""Proxy CRUD + bulk import + health-check/geo lookup."""

from __future__ import annotations

import logging
import re
import threading
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from droidfarm.api.routes_phones import _proxy_to_out
from droidfarm.core.geoip import check_proxy
from droidfarm.db import Proxy, session_scope
from droidfarm.schemas import ProxyIn, ProxyOut

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/proxies", tags=["proxies"])


class ProxyImportBody(BaseModel):
    text: str
    default_scheme: str = "http"
    label_prefix: str = ""


# Accept formats:
#   user:pass@host:port
#   host:port:user:pass
#   host:port
#   scheme://user:pass@host:port
_URL_RE = re.compile(
    r"^(?:(?P<scheme>https?|socks5)://)?"
    r"(?:(?P<user>[^:@\s]+)(?::(?P<pwd>[^@\s]*))?@)?"
    r"(?P<host>[^:@\s/]+):(?P<port>\d+)$"
)


def _is_blank_or_comment(raw: str) -> bool:
    line = raw.strip()
    return not line or line.startswith("#")


def _parse_line(line: str, default_scheme: str) -> dict | None:
    line = line.strip()
    if not line:
        return None
    # Try URL-style first
    m = _URL_RE.match(line)
    if m:
        return {
            "scheme": m.group("scheme") or default_scheme,
            "host": m.group("host"),
            "port": int(m.group("port")),
            "username": m.group("user"),
            "password": m.group("pwd"),
        }
    # Fall back to host:port:user:pass colon-separated form
    parts = line.split(":")
    if len(parts) == 4:
        host, port, user, pwd = parts
        return {
            "scheme": default_scheme,
            "host": host,
            "port": int(port),
            "username": user,
            "password": pwd,
        }
    if len(parts) == 2:
        host, port = parts
        return {
            "scheme": default_scheme,
            "host": host,
            "port": int(port),
            "username": None,
            "password": None,
        }
    return None


@router.post("", response_model=ProxyOut, status_code=201)
def create_proxy(payload: ProxyIn) -> ProxyOut:
    with session_scope() as s:
        p = Proxy(**payload.model_dump())
        s.add(p)
        s.flush()
        return _proxy_to_out(p)  # type: ignore[return-value]


@router.post("/import")
def import_proxies(body: ProxyImportBody) -> dict:
    """Bulk-import a newline-separated list.

    Returns counts of imported / skipped / errors along with the new rows.
    """
    imported: list[ProxyOut] = []
    skipped: list[dict] = []
    with session_scope() as s:
        for idx, raw in enumerate(body.text.splitlines()):
            if _is_blank_or_comment(raw):
                continue
            parsed = _parse_line(raw, body.default_scheme)
            if parsed is None:
                skipped.append({"line": idx + 1, "raw": raw, "reason": "unparseable"})
                continue
            label = f"{body.label_prefix}{parsed['host']}:{parsed['port']}"
            p = Proxy(label=label, **parsed)
            s.add(p)
            s.flush()
            imported.append(_proxy_to_out(p))  # type: ignore[arg-type]
    return {
        "imported": len(imported),
        "skipped": len(skipped),
        "proxies": imported,
        "errors": skipped,
    }


@router.get("", response_model=list[ProxyOut])
def list_proxies() -> list[ProxyOut]:
    with session_scope() as s:
        proxies = s.execute(select(Proxy).order_by(Proxy.id)).scalars().all()
        return [_proxy_to_out(p) for p in proxies]  # type: ignore[misc]


@router.get("/{proxy_id}", response_model=ProxyOut)
def get_proxy(proxy_id: int) -> ProxyOut:
    with session_scope() as s:
        p = s.get(Proxy, proxy_id)
        if p is None:
            raise HTTPException(status_code=404, detail="proxy not found")
        return _proxy_to_out(p)  # type: ignore[return-value]


def _persist_check_result(proxy_id: int) -> None:
    """Run check_proxy and write the result back to the DB."""
    with session_scope() as s:
        p = s.get(Proxy, proxy_id)
        if p is None:
            return
        snapshot = p  # ORM object is bound; we can read it here for the check
        result = check_proxy(snapshot)
        p.is_healthy = result.ok
        p.last_checked_at = datetime.now(timezone.utc)
        p.last_error = result.error
        p.latency_ms = result.latency_ms
        if result.ok:
            # Only overwrite geo when the lookup actually succeeded — keep
            # whatever the user entered manually on failure.
            if result.country: p.country = result.country
            if result.region: p.region = result.region
            if result.city: p.city = result.city
            if result.latitude is not None: p.latitude = result.latitude
            if result.longitude is not None: p.longitude = result.longitude
            if result.timezone: p.timezone = result.timezone
            if result.asn: p.asn = result.asn
            if result.provider: p.provider = result.provider


def _check_in_background(proxy_id: int) -> None:
    threading.Thread(
        target=_persist_check_result,
        args=(proxy_id,),
        name=f"check-proxy-{proxy_id}",
        daemon=True,
    ).start()


@router.post("/{proxy_id}/check", response_model=ProxyOut)
def check_proxy_endpoint(proxy_id: int) -> ProxyOut:
    """Synchronously reach out through the proxy, populate geo + health."""
    with session_scope() as s:
        p = s.get(Proxy, proxy_id)
        if p is None:
            raise HTTPException(status_code=404, detail="proxy not found")
    _persist_check_result(proxy_id)
    with session_scope() as s:
        p = s.get(Proxy, proxy_id)
        assert p is not None
        return _proxy_to_out(p)  # type: ignore[return-value]


@router.post("/check-all")
def check_all_proxies() -> dict:
    """Kick off a health-check of every proxy in the background."""
    with session_scope() as s:
        ids = list(s.execute(select(Proxy.id)).scalars().all())
    for pid in ids:
        _check_in_background(pid)
    return {"queued": len(ids)}


@router.delete("/{proxy_id}", status_code=204)
def delete_proxy(proxy_id: int) -> None:
    with session_scope() as s:
        p = s.get(Proxy, proxy_id)
        if p is None:
            raise HTTPException(status_code=404, detail="proxy not found")
        if p.phone is not None:
            raise HTTPException(
                status_code=409,
                detail=f"proxy is in use by {p.phone.name} — stop + detach first",
            )
        s.delete(p)
