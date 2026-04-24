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

        # Opt-in auto-rotate: only trigger when the user has explicitly
        # enabled it on THIS proxy row. Default is off for every proxy
        # — rotation never happens silently.
        if (
            not result.ok
            and p.auto_rotate
            and p.phone is not None
        ):
            try:
                repl = _pick_replacement(s, for_proxy=p)
                if repl is not None:
                    logger.info(
                        "auto-rotate: %s -> %s for phone %s",
                        p.label, repl.label, p.phone.name,
                    )
                    p.phone.proxy_id = repl.id
                else:
                    logger.warning(
                        "auto-rotate: %s failed but no healthy replacement available",
                        p.label,
                    )
            except Exception as e:
                logger.warning("auto-rotate attempt failed for %s: %s", p.label, e)


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


class _AutoRotateIn(BaseModel):
    auto_rotate: bool


@router.post("/{proxy_id}/auto-rotate", response_model=ProxyOut)
def set_auto_rotate(proxy_id: int, payload: _AutoRotateIn) -> ProxyOut:
    """Per-proxy opt-in toggle. Default is OFF for every row — nothing
    gets rotated unless the user explicitly enables it here."""
    with session_scope() as s:
        p = s.get(Proxy, proxy_id)
        if p is None:
            raise HTTPException(status_code=404, detail="proxy not found")
        p.auto_rotate = payload.auto_rotate
        return _proxy_to_out(p)  # type: ignore[return-value]


def _pick_replacement(session, *, for_proxy: Proxy) -> Proxy | None:
    """Find a healthy, unassigned proxy to swap in. Prefer same country."""
    candidates = session.execute(
        select(Proxy).where(
            Proxy.is_healthy.is_(True),
            Proxy.id != for_proxy.id,
        )
    ).scalars().all()
    # In-use proxies have a back-ref phone (1:1 via unique FK).
    free = [p for p in candidates if p.phone is None]
    if not free:
        return None
    same_country = [p for p in free if for_proxy.country and p.country == for_proxy.country]
    return (same_country or free)[0]


@router.post("/{proxy_id}/rotate", response_model=dict)
def rotate_proxy(proxy_id: int) -> dict:
    """Manually swap this proxy's assigned phone to a new, healthy
    proxy (same country if possible). Works regardless of the
    ``auto_rotate`` flag — this endpoint is always user-triggered."""
    with session_scope() as s:
        p = s.get(Proxy, proxy_id)
        if p is None:
            raise HTTPException(status_code=404, detail="proxy not found")
        if p.phone is None:
            raise HTTPException(
                status_code=409,
                detail="proxy is not assigned to any phone",
            )
        phone = p.phone
        repl = _pick_replacement(s, for_proxy=p)
        if repl is None:
            raise HTTPException(
                status_code=409,
                detail="no free healthy proxy available to rotate to",
            )
        old_label = p.label
        phone.proxy_id = repl.id
        s.flush()
        return {
            "ok": True,
            "phone": phone.name,
            "old_proxy": old_label,
            "new_proxy": repl.label,
            "new_country": repl.country,
        }


@router.get("/stats")
def proxy_stats() -> dict:
    """Aggregate health stats for the dashboard strip at the top of the
    Proxies page."""
    from sqlalchemy import func

    with session_scope() as s:
        total = s.execute(select(func.count(Proxy.id))).scalar() or 0
        healthy = s.execute(
            select(func.count(Proxy.id)).where(Proxy.is_healthy.is_(True))
        ).scalar() or 0
        unhealthy = total - healthy
        in_use = s.execute(
            select(func.count(Proxy.id)).where(Proxy.id.in_(
                select(Proxy.id).join(Proxy.phone)
            ))
        ).scalar() or 0
        auto_rotate = s.execute(
            select(func.count(Proxy.id)).where(Proxy.auto_rotate.is_(True))
        ).scalar() or 0
        latencies = [
            l for (l,) in s.execute(
                select(Proxy.latency_ms).where(Proxy.latency_ms.isnot(None))
            ).all()
        ]
        avg_latency = int(sum(latencies) / len(latencies)) if latencies else None
        last_checked = s.execute(
            select(func.max(Proxy.last_checked_at))
        ).scalar()

    return {
        "total": total,
        "healthy": healthy,
        "unhealthy": unhealthy,
        "in_use": in_use,
        "free": total - in_use,
        "auto_rotate_enabled": auto_rotate,
        "avg_latency_ms": avg_latency,
        "last_checked_at": last_checked.isoformat() if last_checked else None,
    }


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
