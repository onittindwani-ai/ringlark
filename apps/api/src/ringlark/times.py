"""The open times the voice agent may offer, and how they reach it.

A live call has no list of times in its head. Two things give it one: the next open times are written into the prompt when the call starts (where the calendar
can be reached), and the tool `list_times` returns them again on demand. Each time is passed to `book_meeting` as an ISO time WITH its UTC offset, so a time the
model writes without an offset is refused instead of being read as UTC.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx

from ringlark.util import aware, zone
from sendora_core.adapters import AdapterError

OFFER_AHEAD = timedelta(days=14)  # the agent may only book a time the calendar itself offers inside this window
MAX_OFFERED = 6
# What a calendar answer that cannot be used looks like: a refusal, a timeout, a dropped line, or a body of the wrong shape. None of these may stop a call from starting.
CALENDAR_ERRORS = (AdapterError, httpx.HTTPError, OSError, KeyError, ValueError, TypeError, AttributeError)


@dataclass(frozen=True)
class OfferedTime:
    slot: str  # ISO time with an offset: exactly what book_meeting takes
    say: str  # how it is said aloud, in the person's own time zone


def label(start: datetime, tz_name: str) -> str:
    z = zone(tz_name) or UTC
    local = aware(start).astimezone(z)
    return f"{local:%A %B} {local.day} at {local:%I:%M %p}".replace(" 0", " ") + f" {local:%Z}"


def fetch_slots(calendar, now: datetime) -> list[datetime]:
    """The next open times as the calendar gives them, soonest first, at most MAX_OFFERED. A calendar failure raises."""
    return sorted({aware(x) for x in calendar.slots(aware(now), aware(now) + OFFER_AHEAD)})[:MAX_OFFERED]


def offer(slots: list[datetime], tz_name: str) -> list[OfferedTime]:
    return [OfferedTime(x.isoformat(), label(x, tz_name)) for x in slots]


def open_times(calendar, now: datetime, tz_name: str) -> list[OfferedTime]:
    """The next open times, said in the given time zone. A calendar failure raises (the tool turns it into a plain answer)."""
    return offer(fetch_slots(calendar, now), tz_name)


def safe_slots(adapters, now: datetime) -> list[datetime] | None:
    """The same, for the moment a call is set up: None when the calendar cannot be reached (the prompt then tells the model to ask for the times)."""
    try:
        return fetch_slots(adapters.calendar, now)
    except CALENDAR_ERRORS:
        return None
