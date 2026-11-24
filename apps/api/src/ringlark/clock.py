"""The clock. In demo mode a stored offset lets the demo move time forward. Outside demo mode the offset is ignored."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from ringlark.models import State


def now(session: Session, demo_mode: bool) -> datetime:
    if not demo_mode:
        return datetime.now(UTC)
    row = session.get(State, "clock_offset_hours")
    hours = float(row.value) if row and row.value else 0.0
    return datetime.now(UTC) + timedelta(hours=hours)


def set_offset(session: Session, hours: float) -> None:
    row = session.get(State, "clock_offset_hours")
    if row is None:
        session.add(State(key="clock_offset_hours", value=str(hours)))
    else:
        row.value = str(hours)


def advance(session: Session, hours: float) -> datetime:
    row = session.get(State, "clock_offset_hours")
    cur = float(row.value) if row and row.value else 0.0
    set_offset(session, cur + hours)
    session.flush()
    return now(session, True)
