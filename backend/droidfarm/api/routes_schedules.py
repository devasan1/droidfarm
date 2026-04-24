"""Cron-style scheduled actions.

Endpoints:
    GET    /api/schedules             list
    POST   /api/schedules             create
    GET    /api/schedules/{id}        get one
    PATCH  /api/schedules/{id}        update (name, cron, action, targets,
                                              params, enabled)
    POST   /api/schedules/{id}/run    trigger immediately (manual fire)
    DELETE /api/schedules/{id}        delete
    GET    /api/schedules/actions     list supported action names
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from droidfarm.core.scheduler import (
    ACTIONS,
    _resolve_target_phones,
    _run_action,
    compute_next_run,
    validate_cron,
)
from droidfarm.db import Schedule, session_scope

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/schedules", tags=["schedules"])


class ScheduleIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    cron: str
    action: str
    target_phone_ids: list[int] = Field(default_factory=list)
    params: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class SchedulePatch(BaseModel):
    name: str | None = None
    cron: str | None = None
    action: str | None = None
    target_phone_ids: list[int] | None = None
    params: dict[str, Any] | None = None
    enabled: bool | None = None


class ScheduleOut(BaseModel):
    id: int
    name: str
    cron: str
    action: str
    target_phone_ids: list[int]
    params: dict[str, Any]
    enabled: bool
    created_at: datetime
    last_run_at: datetime | None
    next_run_at: datetime | None
    last_status: str | None
    last_error: str | None


def _to_out(s: Schedule) -> ScheduleOut:
    return ScheduleOut(
        id=s.id,
        name=s.name,
        cron=s.cron,
        action=s.action,
        target_phone_ids=list(s.target_phone_ids or []),
        params=dict(s.params or {}),
        enabled=s.enabled,
        created_at=s.created_at,
        last_run_at=s.last_run_at,
        next_run_at=s.next_run_at,
        last_status=s.last_status,
        last_error=s.last_error,
    )


def _validate(sched_in: ScheduleIn | SchedulePatch, *, required: bool) -> None:
    if required or sched_in.cron is not None:
        assert sched_in.cron is not None
        validate_cron(sched_in.cron)
    if required or sched_in.action is not None:
        if sched_in.action not in ACTIONS:
            raise HTTPException(
                status_code=422,
                detail=f"unknown action {sched_in.action!r}; allowed: {sorted(ACTIONS)}",
            )


@router.get("/actions")
def list_actions() -> dict:
    """Surface supported actions + the params each one expects. Used
    by the frontend to build the 'New schedule' form dynamically."""
    return {
        "actions": [
            {"name": "start", "params": []},
            {"name": "stop", "params": []},
            {"name": "wipe", "params": []},
            {
                "name": "rotate_gps",
                "params": [
                    {"name": "delta_deg", "type": "number", "default": 0.002},
                ],
            },
            {
                "name": "launch_package",
                "params": [{"name": "package", "type": "string", "required": True}],
            },
            {
                "name": "force_stop_package",
                "params": [{"name": "package", "type": "string", "required": True}],
            },
            {
                "name": "shell",
                "params": [{"name": "cmd", "type": "string", "required": True}],
            },
        ],
    }


@router.get("", response_model=list[ScheduleOut])
def list_schedules() -> list[ScheduleOut]:
    with session_scope() as s:
        rows = s.execute(select(Schedule).order_by(Schedule.id)).scalars().all()
        return [_to_out(r) for r in rows]


@router.post("", response_model=ScheduleOut, status_code=201)
def create_schedule(payload: ScheduleIn) -> ScheduleOut:
    try:
        _validate(payload, required=True)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    next_run = compute_next_run(payload.cron) if payload.enabled else None
    with session_scope() as s:
        existing = s.execute(
            select(Schedule).where(Schedule.name == payload.name)
        ).scalar_one_or_none()
        if existing is not None:
            raise HTTPException(
                status_code=409,
                detail=f"schedule named {payload.name!r} already exists",
            )
        sched = Schedule(
            name=payload.name,
            cron=payload.cron,
            action=payload.action,
            target_phone_ids=list(payload.target_phone_ids),
            params=dict(payload.params),
            enabled=payload.enabled,
            next_run_at=next_run,
        )
        s.add(sched)
        s.flush()
        return _to_out(sched)


@router.get("/{schedule_id}", response_model=ScheduleOut)
def get_schedule(schedule_id: int) -> ScheduleOut:
    with session_scope() as s:
        sched = s.get(Schedule, schedule_id)
        if sched is None:
            raise HTTPException(status_code=404, detail="schedule not found")
        return _to_out(sched)


@router.patch("/{schedule_id}", response_model=ScheduleOut)
def patch_schedule(schedule_id: int, payload: SchedulePatch) -> ScheduleOut:
    try:
        _validate(payload, required=False)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    with session_scope() as s:
        sched = s.get(Schedule, schedule_id)
        if sched is None:
            raise HTTPException(status_code=404, detail="schedule not found")
        if payload.name is not None:
            sched.name = payload.name
        if payload.cron is not None:
            sched.cron = payload.cron
        if payload.action is not None:
            sched.action = payload.action
        if payload.target_phone_ids is not None:
            sched.target_phone_ids = list(payload.target_phone_ids)
        if payload.params is not None:
            sched.params = dict(payload.params)
        if payload.enabled is not None:
            sched.enabled = payload.enabled
        # Re-compute next_run whenever cron or enabled flag changes.
        if sched.enabled:
            try:
                sched.next_run_at = compute_next_run(sched.cron)
            except Exception as e:
                raise HTTPException(status_code=422, detail=str(e)) from e
        else:
            sched.next_run_at = None
        return _to_out(sched)


@router.post("/{schedule_id}/run", response_model=ScheduleOut)
def run_now(schedule_id: int) -> ScheduleOut:
    """Fire a schedule immediately without waiting for its cron tick.
    Does NOT change ``next_run_at`` — the schedule still fires on its
    normal cadence after. Useful for testing a new schedule."""
    with session_scope() as s:
        sched = s.get(Schedule, schedule_id)
        if sched is None:
            raise HTTPException(status_code=404, detail="schedule not found")
        phones = _resolve_target_phones(s, sched)
        errors: list[str] = []
        for ph in phones:
            try:
                _run_action(sched, ph)
            except Exception as e:
                errors.append(f"{ph.name}: {e}")
        sched.last_run_at = datetime.utcnow()
        if errors:
            sched.last_status = "error"
            sched.last_error = "; ".join(errors)[:500]
        else:
            sched.last_status = "ok" if phones else "no-targets"
            sched.last_error = None
        return _to_out(sched)


@router.delete("/{schedule_id}", status_code=204)
def delete_schedule(schedule_id: int) -> None:
    with session_scope() as s:
        sched = s.get(Schedule, schedule_id)
        if sched is None:
            raise HTTPException(status_code=404, detail="schedule not found")
        s.delete(sched)
