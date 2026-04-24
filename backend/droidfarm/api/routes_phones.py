"""Phone CRUD + lifecycle."""

from __future__ import annotations

import logging
import threading

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from droidfarm.core.driver import LaunchOptions, get_driver
from droidfarm.db import Phone, Proxy, session_scope
from droidfarm.schemas import PhoneIn, PhoneOut, ProxyOut

logger = logging.getLogger(__name__)

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


def _launch_opts(phone: Phone) -> LaunchOptions:
    opts = LaunchOptions(
        resolution=phone.resolution,
        dpi=phone.dpi,
        cpu=phone.cpu,
        ram_mb=phone.ram_mb,
    )
    if phone.proxy_mode == "system-http" and phone.proxy is not None:
        opts.proxy = f"{phone.proxy.host}:{phone.proxy.port}"
    go = phone.geo_overrides or {}
    opts.locale = go.get("locale")
    opts.timezone = go.get("timezone")
    opts.imei = go.get("imei")
    opts.manufacturer = go.get("manufacturer")
    opts.model = go.get("model")
    return opts


def _start_in_background(phone_id: int) -> None:
    """Kick off the driver-level create+start for a phone in a worker thread.

    The DB is updated from inside the worker so the UI's poll loop sees the
    status transitions stopped → starting → running (or crashed on failure).
    """

    def _worker() -> None:
        driver = get_driver()
        try:
            with session_scope() as s:
                phone = s.get(Phone, phone_id)
                if phone is None:
                    return
                name = phone.name
                opts = _launch_opts(phone)

            # Ensure the LDPlayer instance exists (create is idempotent for MockDriver;
            # real LDPlayer will error if you add an existing name, so we check first).
            existing = next((i for i in driver.list() if i.name == name), None)
            if existing is None:
                driver.create(name, opts)
            else:
                driver.modify(name, opts)

            inst = driver.start(name, opts)
            with session_scope() as s:
                phone = s.get(Phone, phone_id)
                if phone is None:
                    return
                phone.status = "running"
                phone.ldplayer_index = inst.index
                phone.last_error = None
        except Exception as e:
            logger.exception("start phone %s failed", phone_id)
            with session_scope() as s:
                phone = s.get(Phone, phone_id)
                if phone is not None:
                    phone.status = "crashed"
                    phone.last_error = str(e)

    threading.Thread(target=_worker, name=f"start-phone-{phone_id}", daemon=True).start()


def _stop_in_background(phone_id: int) -> None:
    def _worker() -> None:
        driver = get_driver()
        with session_scope() as s:
            phone = s.get(Phone, phone_id)
            if phone is None:
                return
            name = phone.name
        try:
            driver.stop(name)
        except Exception as e:
            logger.warning("stop phone %s failed: %s", name, e)
        with session_scope() as s:
            phone = s.get(Phone, phone_id)
            if phone is not None:
                phone.status = "stopped"

    threading.Thread(target=_worker, name=f"stop-phone-{phone_id}", daemon=True).start()


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
        phone_id = phone.id
        out = _phone_to_out(phone)

    # Always create the underlying LDPlayer instance so it shows up in the
    # emulator manager. Start it only when autostart=True.
    driver = get_driver()
    with session_scope() as s2:
        phone2 = s2.get(Phone, phone_id)
        if phone2 is not None:
            opts = _launch_opts(phone2)
            existing = next((i for i in driver.list() if i.name == phone2.name), None)
            if existing is None:
                inst = driver.create(phone2.name, opts)
                phone2.ldplayer_index = inst.index
            else:
                phone2.ldplayer_index = existing.index
                driver.modify(phone2.name, opts)
    if payload.autostart:
        with session_scope() as s3:
            phone3 = s3.get(Phone, phone_id)
            if phone3 is not None:
                phone3.status = "starting"
        _start_in_background(phone_id)

    return out


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
        name = phone.name
        s.delete(phone)

    # Best-effort cleanup of the underlying LDPlayer instance.
    try:
        driver = get_driver()
        driver.stop(name)
        driver.destroy(name)
    except Exception as e:
        logger.warning("driver cleanup for %s failed (ignored): %s", name, e)


@router.post("/{phone_id}/start", response_model=PhoneOut)
def start_phone(phone_id: int) -> PhoneOut:
    with session_scope() as s:
        phone = s.get(Phone, phone_id)
        if phone is None:
            raise HTTPException(status_code=404, detail="phone not found")
        phone.status = "starting"
        phone.last_error = None
        s.flush()
        out = _phone_to_out(phone)
    _start_in_background(phone_id)
    return out


@router.post("/{phone_id}/stop", response_model=PhoneOut)
def stop_phone(phone_id: int) -> PhoneOut:
    with session_scope() as s:
        phone = s.get(Phone, phone_id)
        if phone is None:
            raise HTTPException(status_code=404, detail="phone not found")
        phone.status = "stopping"
        s.flush()
        out = _phone_to_out(phone)
    _stop_in_background(phone_id)
    return out
