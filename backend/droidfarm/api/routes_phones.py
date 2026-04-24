"""Phone CRUD + lifecycle (stubs — driver wiring lands in the next commit)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from droidfarm.db import Phone, Proxy, session_scope
from droidfarm.schemas import PhoneIn, PhoneOut, ProxyOut

router = APIRouter(prefix="/api/phones", tags=["phones"])


def _proxy_to_out(p: Proxy | None) -> ProxyOut | None:
    if p is None:
        return None
    return ProxyOut(
        id=p.id,
        label=p.label,
        scheme=p.scheme,  # type: ignore[arg-type]
        host=p.host,
        port=p.port,
        username=p.username,
        has_password=p.password is not None,
        country=p.country,
        region=p.region,
        city=p.city,
        latitude=p.latitude,
        longitude=p.longitude,
        timezone=p.timezone,
        asn=p.asn,
        provider=p.provider,
        is_healthy=p.is_healthy,
        last_checked_at=p.last_checked_at,
        last_error=p.last_error,
        latency_ms=p.latency_ms,
        created_at=p.created_at,
        notes=p.notes,
        assigned_to_phone_id=p.phone.id if p.phone else None,
        assigned_to_phone_name=p.phone.name if p.phone else None,
    )


def _phone_to_out(phone: Phone) -> PhoneOut:
    return PhoneOut(
        id=phone.id,
        name=phone.name,
        ldplayer_index=phone.ldplayer_index,
        device_profile=phone.device_profile,
        android_version=phone.android_version,
        resolution=phone.resolution,
        dpi=phone.dpi,
        cpu=phone.cpu,
        ram_mb=phone.ram_mb,
        status=phone.status,  # type: ignore[arg-type]
        autostart=phone.autostart,
        proxy_mode=phone.proxy_mode,  # type: ignore[arg-type]
        proxy=_proxy_to_out(phone.proxy),
        geo_overrides=phone.geo_overrides or {},
        preinstall_apks=phone.preinstall_apks or [],
        created_at=phone.created_at,
        last_started_at=phone.last_started_at,
        last_error=phone.last_error,
    )


def _reserve_proxy(session, phone_in: PhoneIn) -> Proxy | None:
    if phone_in.proxy_id is not None:
        p = session.get(Proxy, phone_in.proxy_id)
        if p is None:
            raise HTTPException(status_code=404, detail="proxy not found")
        if p.phone is not None:
            raise HTTPException(
                status_code=409, detail=f"proxy {p.id} already assigned to {p.phone.name}"
            )
        return p
    if phone_in.auto_assign_proxy:
        free = session.execute(
            select(Proxy)
            .outerjoin(Phone, Phone.proxy_id == Proxy.id)
            .where(Phone.id.is_(None), Proxy.is_healthy.is_(True))
            .order_by(Proxy.id)
            .limit(1)
        ).scalar_one_or_none()
        if free is None:
            raise HTTPException(
                status_code=409,
                detail="no healthy unassigned proxy available — import more first",
            )
        return free
    return None


@router.post("", response_model=PhoneOut, status_code=201)
def create_phone(payload: PhoneIn) -> PhoneOut:
    with session_scope() as s:
        if s.execute(select(Phone).where(Phone.name == payload.name)).scalar_one_or_none():
            raise HTTPException(status_code=409, detail="phone name already exists")
        proxy = _reserve_proxy(s, payload)
        phone = Phone(
            name=payload.name,
            device_profile=payload.device_profile,
            android_version=payload.android_version,
            resolution=payload.resolution,
            dpi=payload.dpi,
            cpu=payload.cpu,
            ram_mb=payload.ram_mb,
            autostart=payload.autostart,
            proxy_mode=payload.proxy_mode,
            proxy=proxy,
            preinstall_apks=payload.preinstall_apks,
            geo_overrides={},
        )
        s.add(phone)
        s.flush()
        return _phone_to_out(phone)


@router.get("", response_model=list[PhoneOut])
def list_phones() -> list[PhoneOut]:
    with session_scope() as s:
        phones = s.execute(select(Phone).order_by(Phone.id)).scalars().all()
        return [_phone_to_out(p) for p in phones]


@router.get("/{phone_id}", response_model=PhoneOut)
def get_phone(phone_id: int) -> PhoneOut:
    with session_scope() as s:
        phone = s.get(Phone, phone_id)
        if phone is None:
            raise HTTPException(status_code=404, detail="phone not found")
        return _phone_to_out(phone)


@router.delete("/{phone_id}", status_code=204)
def delete_phone(phone_id: int) -> None:
    with session_scope() as s:
        phone = s.get(Phone, phone_id)
        if phone is None:
            raise HTTPException(status_code=404, detail="phone not found")
        s.delete(phone)


@router.post("/{phone_id}/start", response_model=PhoneOut)
def start_phone(phone_id: int) -> PhoneOut:
    """Mark the phone as 'starting' — driver integration lands in the next commit."""
    with session_scope() as s:
        phone = s.get(Phone, phone_id)
        if phone is None:
            raise HTTPException(status_code=404, detail="phone not found")
        phone.status = "starting"
        phone.last_error = None
        s.flush()
        return _phone_to_out(phone)


@router.post("/{phone_id}/stop", response_model=PhoneOut)
def stop_phone(phone_id: int) -> PhoneOut:
    with session_scope() as s:
        phone = s.get(Phone, phone_id)
        if phone is None:
            raise HTTPException(status_code=404, detail="phone not found")
        phone.status = "stopping"
        s.flush()
        return _phone_to_out(phone)
