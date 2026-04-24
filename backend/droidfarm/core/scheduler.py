"""Cron-style background scheduler.

Periodically wakes up, finds every enabled ``Schedule`` whose
``next_run_at`` is in the past, executes its ``action`` against the
targeted phones, and advances ``next_run_at`` to the next cron tick.

The scheduler is a single daemon thread started from the FastAPI
lifespan hook. Since DroidFarm is a desktop app with at most a few
schedules, a simple polling loop at 10s resolution is plenty — no
need for APScheduler, Celery, etc.
"""

from __future__ import annotations

import logging
import random
import threading
import time
from datetime import datetime, timezone

from croniter import croniter
from sqlalchemy import select

from droidfarm.db import Phone, Schedule, session_scope

logger = logging.getLogger(__name__)

POLL_INTERVAL_S = 10

# Allowed action names. Keep in sync with the frontend dropdown.
ACTIONS = {
    "start",
    "stop",
    "wipe",
    "rotate_gps",
    "launch_package",
    "force_stop_package",
    "shell",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def compute_next_run(cron_expr: str, *, base: datetime | None = None) -> datetime:
    """Parse a 5-field cron expression and return the next UTC trigger."""
    base = base or _now()
    it = croniter(cron_expr, base)
    return it.get_next(datetime)


def validate_cron(cron_expr: str) -> None:
    """Raise ValueError if the cron expression is invalid."""
    if not croniter.is_valid(cron_expr):
        raise ValueError(f"invalid cron expression: {cron_expr!r}")


def _resolve_target_phones(session, sched: Schedule) -> list[Phone]:
    if sched.target_phone_ids:
        rows = (
            session.execute(
                select(Phone).where(
                    Phone.id.in_(sched.target_phone_ids),
                    Phone.deleted_at.is_(None),
                )
            )
            .scalars()
            .all()
        )
        return list(rows)
    # Empty list = all live phones.
    return list(
        session.execute(
            select(Phone).where(Phone.deleted_at.is_(None))
        )
        .scalars()
        .all()
    )


def _run_action(sched: Schedule, phone: Phone) -> None:
    """Execute one (action, phone) pair. Imported lazily to avoid
    circular imports with routes_phones (which in turn imports db)."""
    from droidfarm.api.routes_phones import (
        _start_in_background,
        _stop_in_background,
        _wipe_in_background,
    )
    from droidfarm.core import adb
    from droidfarm.db import session_scope as ss

    action = sched.action
    params = sched.params or {}

    if action == "start":
        _start_in_background(phone.id)
        return
    if action == "stop":
        _stop_in_background(phone.id)
        return
    if action == "wipe":
        _wipe_in_background(phone.id)
        return

    # Remaining actions need a running phone + adb serial.
    if phone.status != "running":
        raise RuntimeError(f"phone {phone.name} is not running")
    # Serial is emulator-<index*2+5555> by LDPlayer convention; mock
    # driver also tolerates that. Use the stored ldplayer_index.
    idx = phone.ldplayer_index
    if idx is None:
        raise RuntimeError(f"phone {phone.name} has no ldplayer_index")
    serial = f"emulator-{5554 + (idx + 1) * 2}"

    if action == "rotate_gps":
        # Jitter the phone's current lat/lon by ±delta_deg (default
        # ±0.002, ~200m). Useful for farming patterns that need to
        # look like the phone is walking around town. Falls back to
        # the geo_overrides' base lat/lon if not present.
        with ss() as s:
            p = s.get(Phone, phone.id)
            assert p is not None
            go = dict(p.geo_overrides or {})
            lat = go.get("latitude")
            lon = go.get("longitude")
            if lat is None or lon is None:
                raise RuntimeError("phone has no base GPS to rotate around")
            delta = float(params.get("delta_deg", 0.002))
            new_lat = float(lat) + random.uniform(-delta, delta)
            new_lon = float(lon) + random.uniform(-delta, delta)
            go["latitude"] = new_lat
            go["longitude"] = new_lon
            p.geo_overrides = go
        # Push to the device.
        try:
            adb.shell(
                serial,
                "am",
                "broadcast",
                "-a",
                "com.droidfarm.SET_LOCATION",
                "--ef",
                "lat",
                str(new_lat),
                "--ef",
                "lon",
                str(new_lon),
            )
        except Exception:
            # Best-effort: mock driver won't have that broadcast wired.
            pass
        return

    if action == "launch_package":
        pkg = params.get("package")
        if not pkg:
            raise RuntimeError("launch_package requires params.package")
        adb.launch_package(serial, pkg)
        return

    if action == "force_stop_package":
        pkg = params.get("package")
        if not pkg:
            raise RuntimeError("force_stop_package requires params.package")
        adb.force_stop_package(serial, pkg)
        return

    if action == "shell":
        cmd = params.get("cmd")
        if not cmd:
            raise RuntimeError("shell requires params.cmd")
        parts = cmd.split() if isinstance(cmd, str) else list(cmd)
        adb.shell(serial, *parts)
        return

    raise RuntimeError(f"unknown action: {action}")


def _tick() -> None:
    """One iteration of the poller — find due schedules, run them,
    advance next_run_at."""
    now = _now()
    with session_scope() as s:
        due = list(
            s.execute(
                select(Schedule).where(
                    Schedule.enabled.is_(True),
                    Schedule.next_run_at.isnot(None),
                    Schedule.next_run_at <= now,
                )
            )
            .scalars()
            .all()
        )

    for sched in due:
        sched_id = sched.id
        # Reload in its own session so we write back atomically.
        with session_scope() as s:
            fresh = s.get(Schedule, sched_id)
            if fresh is None or not fresh.enabled:
                continue
            phones = _resolve_target_phones(s, fresh)
            errors: list[str] = []
            for ph in phones:
                try:
                    _run_action(fresh, ph)
                except Exception as e:
                    errors.append(f"{ph.name}: {e}")
                    logger.warning(
                        "schedule %s on %s failed: %s", fresh.name, ph.name, e
                    )
            fresh.last_run_at = now
            if errors:
                fresh.last_status = "error"
                fresh.last_error = "; ".join(errors)[:500]
            else:
                fresh.last_status = "ok" if phones else "no-targets"
                fresh.last_error = None
            try:
                fresh.next_run_at = compute_next_run(fresh.cron, base=now)
            except Exception as e:
                fresh.enabled = False
                fresh.last_status = "error"
                fresh.last_error = f"cron parse failed, disabled: {e}"


_STOP = threading.Event()
_THREAD: threading.Thread | None = None


def _loop() -> None:
    logger.info("scheduler thread started (poll every %ss)", POLL_INTERVAL_S)
    while not _STOP.is_set():
        try:
            _tick()
        except Exception as e:
            logger.warning("scheduler tick failed: %s", e)
        _STOP.wait(POLL_INTERVAL_S)
    logger.info("scheduler thread stopped")


def start_scheduler() -> None:
    """Idempotent — safe to call once on app startup."""
    global _THREAD
    if _THREAD is not None and _THREAD.is_alive():
        return
    _STOP.clear()
    _THREAD = threading.Thread(target=_loop, name="droidfarm-scheduler", daemon=True)
    _THREAD.start()


def stop_scheduler() -> None:
    _STOP.set()
