"""Phone CRUD + lifecycle."""

from __future__ import annotations

import logging
import threading

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from droidfarm.config import SETTINGS
from droidfarm.core.driver import LaunchOptions, get_driver
from droidfarm.core.geoip import lookup_host_geo
from droidfarm.core.locales import locale_and_tz_for
from droidfarm.core.templates import (
    ensure_templates,
    source_template_for,
    wipe_from_template,
)
from droidfarm.db import Apk, Phone, Proxy, session_scope
from droidfarm.schemas import PhoneIn, PhoneOut, ProxyOut

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/phones", tags=["phones"])


@router.get("/host-geo")
def host_geo() -> dict:
    """Preview what the VM's own public-IP geoIP looks like — useful for
    the UI so users can see what "Bypass IP" will apply before they create
    the phone."""
    g = lookup_host_geo()
    return {
        "ok": g.ok,
        "error": g.error,
        "ip": g.ip,
        "country": g.country,
        "region": g.region,
        "city": g.city,
        "latitude": g.latitude,
        "longitude": g.longitude,
        "timezone": g.timezone,
        "provider": g.provider,
    }


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
        show_setup_wizard=phone.show_setup_wizard,
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

            # Ensure the LDPlayer instance exists. New phones are cloned from
            # one of the prepared templates — that keeps them data-clean +
            # (optionally) past the first-boot setup wizard.
            existing = next((i for i in driver.list() if i.name == name), None)
            if existing is None:
                # Make sure both templates are prepared; skipped after the first run.
                try:
                    ensure_templates(driver, SETTINGS.data_dir)
                except Exception as e:
                    logger.warning("template preparation failed: %s", e)
                with session_scope() as s:
                    p2 = s.get(Phone, phone_id)
                    skip = not (p2.show_setup_wizard if p2 else False)
                source = source_template_for(skip_setup=skip)
                driver.clone(name, source, opts)
            else:
                driver.modify(name, opts)

            inst = driver.start(name, opts)

            # Spoof locale / timezone / GPS so the phone matches the proxy
            # country. Best-effort: a failure here doesn't crash the phone.
            with session_scope() as s:
                phone = s.get(Phone, phone_id)
                go = dict(phone.geo_overrides or {}) if phone else {}
            try:
                _apply_geo_overrides(driver, name, inst, go)
            except Exception as e:
                logger.warning("geo-spoof for %s failed (phone still started): %s", name, e)

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


def _apply_geo_overrides(driver, name: str, inst, go: dict) -> None:
    """Push locale / timezone / GPS into a freshly-booted phone.

    Strategy:
      1. Ask the driver to set GPS natively (LDPlayer has ``locate``).
         Mock driver just logs.
      2. For locale + timezone + mock-location-app broadcast, we need
         adb. On real LDPlayer, ``inst.adb_port`` is populated; we connect
         to 127.0.0.1:<port>, wait for boot, then apply setprop commands.
      3. If adb isn't available (e.g. MockDriver on Linux dev), skip the
         adb step — GPS was already handled by the driver.
    """
    lat = go.get("latitude")
    lon = go.get("longitude")
    if lat is not None and lon is not None:
        try:
            driver.set_gps(name, float(lat), float(lon))
        except Exception as e:
            logger.warning("driver.set_gps(%s) failed: %s", name, e)

    if not getattr(driver, "supports_adb", True):
        return  # e.g. MockDriver — skip adb steps on dev VMs

    port = getattr(inst, "adb_port", None)
    if port is None:
        return  # driver hasn't surfaced an adb port yet

    # Lazy import so the adb module doesn't need to load on CI without adb.
    from droidfarm.core import adb

    serial = f"127.0.0.1:{port}"
    try:
        adb.connect(serial)
    except Exception as e:
        logger.warning("adb connect %s failed: %s", serial, e)
        return

    if not adb.wait_for_boot(serial, timeout_s=180):
        logger.warning("phone %s didn't finish booting within 180s", name)
        return

    locale = go.get("locale")
    tz = go.get("timezone")
    if locale:
        try:
            adb.set_locale(serial, locale)
        except Exception as e:
            logger.warning("set_locale(%s, %s) failed: %s", serial, locale, e)
    if tz:
        try:
            adb.set_timezone(serial, tz)
        except Exception as e:
            logger.warning("set_timezone(%s, %s) failed: %s", serial, tz, e)
    if lat is not None and lon is not None:
        try:
            adb.set_mock_location(serial, float(lat), float(lon))
        except Exception as e:
            logger.warning("set_mock_location failed: %s", e)


def _fill_locale_defaults(d: dict) -> dict:
    """If the caller gave us a country but no locale/timezone, fill in
    sensible defaults so 'feels like that city' is actually true.

    Timezone comes from the proxy's own tz field first (more accurate),
    then falls back to the country-default table. Locale is always
    country-derived since proxies don't expose one.
    """
    country = d.get("country")
    loc, tz = locale_and_tz_for(country) if country else (None, None)
    if loc and not d.get("locale"):
        d["locale"] = loc
    if tz and not d.get("timezone"):
        d["timezone"] = tz
    return d


def _geo_overrides_from_proxy(p: Proxy | None) -> dict:
    if p is None:
        return {}
    d = {
        k: v
        for k, v in {
            "country": p.country,
            "region": p.region,
            "city": p.city,
            "latitude": p.latitude,
            "longitude": p.longitude,
            "timezone": p.timezone,
        }.items()
        if v is not None
    }
    return _fill_locale_defaults(d)


def _geo_overrides_for_bypass() -> dict:
    """Geo overrides for 'no proxy / bypass' mode — look up the host VM's
    public IP and pin that country/city/timezone/GPS onto the phone so the
    phone is consistent with the host's own egress."""
    g = lookup_host_geo()
    if not g.ok:
        logger.warning("host geoIP lookup failed: %s", g.error)
        return {}
    d = {
        k: v
        for k, v in {
            "country": g.country,
            "region": g.region,
            "city": g.city,
            "latitude": g.latitude,
            "longitude": g.longitude,
            "timezone": g.timezone,
        }.items()
        if v is not None
    }
    return _fill_locale_defaults(d)


@router.post("", response_model=PhoneOut, status_code=201)
def create_phone(payload: PhoneIn) -> PhoneOut:
    with session_scope() as s:
        if s.execute(select(Phone).where(Phone.name == payload.name)).scalar_one_or_none():
            raise HTTPException(status_code=409, detail="phone name already exists")

        bypass = payload.proxy_mode == "none" or payload.bypass_ip
        if bypass:
            # Force no proxy for bypass mode regardless of any proxy_id.
            proxy = None
            proxy_mode = "none"
        else:
            proxy = _reserve_proxy(s, payload)
            proxy_mode = payload.proxy_mode

        # Seed the per-phone geo from the proxy (when present) or from the
        # host VM (bypass). The geo-spoof step (next commit) reads this at
        # boot and pushes locale/timezone/GPS into Android via adb.
        if proxy is not None:
            geo = _geo_overrides_from_proxy(proxy)
        elif bypass:
            geo = _geo_overrides_for_bypass()
        else:
            geo = {}

        phone = Phone(
            name=payload.name,
            device_profile=payload.device_profile,
            android_version=payload.android_version,
            resolution=payload.resolution,
            dpi=payload.dpi,
            cpu=payload.cpu,
            ram_mb=payload.ram_mb,
            autostart=payload.autostart,
            show_setup_wizard=payload.show_setup_wizard,
            proxy_mode=proxy_mode,
            proxy=proxy,
            preinstall_apks=payload.preinstall_apks,
            geo_overrides=geo,
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


def _wipe_in_background(phone_id: int) -> None:
    """Destroy + re-clone the phone from its source template, preserving
    LaunchOptions so IMEI/resolution/etc. survive the wipe."""

    def _worker() -> None:
        driver = get_driver()
        try:
            with session_scope() as s:
                phone = s.get(Phone, phone_id)
                if phone is None:
                    return
                name = phone.name
                skip = not phone.show_setup_wizard
                opts = _launch_opts(phone)
            source = source_template_for(skip_setup=skip)
            wipe_from_template(driver, name, source, opts)
            inst = driver.start(name, opts)
            with session_scope() as s:
                phone = s.get(Phone, phone_id)
                if phone is not None:
                    phone.status = "running"
                    phone.ldplayer_index = inst.index
                    phone.last_error = None
        except Exception as e:
            logger.exception("wipe phone %s failed", phone_id)
            with session_scope() as s:
                phone = s.get(Phone, phone_id)
                if phone is not None:
                    phone.status = "crashed"
                    phone.last_error = str(e)

    threading.Thread(target=_worker, name=f"wipe-phone-{phone_id}", daemon=True).start()


@router.post("/{phone_id}/wipe", response_model=PhoneOut)
def wipe_phone(phone_id: int) -> PhoneOut:
    """Factory-reset the phone — destroys the LDPlayer instance and
    re-clones from its source template (factory or configured). Returns
    immediately with status='starting'; the actual wipe runs in the
    background and the UI picks up the state transition via its poll."""
    with session_scope() as s:
        phone = s.get(Phone, phone_id)
        if phone is None:
            raise HTTPException(status_code=404, detail="phone not found")
        phone.status = "starting"
        phone.last_error = None
        s.flush()
        out = _phone_to_out(phone)
    _wipe_in_background(phone_id)
    return out


# ---------- APK install ----------


class _InstallApkIn(BaseModel):
    apk_id: int


class _InstallResult(BaseModel):
    ok: bool
    apk_id: int
    phone_id: int
    filename: str
    error: str | None = None


@router.post("/{phone_id}/install-apk", response_model=_InstallResult)
def install_apk_on_phone(phone_id: int, payload: _InstallApkIn) -> _InstallResult:
    """Install an APK from the library onto a running phone.

    The phone must be running (``ldconsole`` wants a live instance, and
    adb obviously does too). We try the driver's native installapp first
    (fast — LDPlayer copies via the shared filesystem) and fall back to
    ``adb install -r`` if the driver says it can't.
    """
    with session_scope() as s:
        phone = s.get(Phone, phone_id)
        if phone is None:
            raise HTTPException(status_code=404, detail="phone not found")
        if phone.status != "running":
            raise HTTPException(
                status_code=409,
                detail=f"phone is {phone.status} — start it before installing APKs",
            )
        apk = s.get(Apk, payload.apk_id)
        if apk is None:
            raise HTTPException(status_code=404, detail="apk not found")
        phone_name = phone.name
        phone_ldindex = phone.ldplayer_index
        apk_filename = apk.filename

    apk_path = SETTINGS.apks_dir / apk_filename
    if not apk_path.exists():
        raise HTTPException(
            status_code=410,
            detail=f"apk file missing on disk: {apk_path} (re-upload the APK)",
        )

    driver = get_driver()
    try:
        # Native path (LDPlayer: fast, no adb hop).
        driver.install_apk(phone_name, apk_path)
        return _InstallResult(
            ok=True, apk_id=payload.apk_id, phone_id=phone_id, filename=apk_filename,
        )
    except Exception as native_exc:
        logger.info("driver.install_apk native path failed, trying adb: %s", native_exc)

    # Fallback: adb install -r (only if the driver surfaces adb + the phone
    # has an adb port).
    if not getattr(driver, "supports_adb", True):
        raise HTTPException(
            status_code=500,
            detail=f"driver install failed and adb fallback disabled: {native_exc}",
        )
    port = 5555 + 2 * (phone_ldindex or 0)
    from droidfarm.core import adb as adb_mod

    serial = f"127.0.0.1:{port}"
    try:
        adb_mod.connect(serial)
        adb_mod.install(serial, apk_path)
        return _InstallResult(
            ok=True, apk_id=payload.apk_id, phone_id=phone_id, filename=apk_filename,
        )
    except Exception as e:
        logger.exception("adb install fallback also failed")
        return _InstallResult(
            ok=False, apk_id=payload.apk_id, phone_id=phone_id,
            filename=apk_filename, error=str(e),
        )
