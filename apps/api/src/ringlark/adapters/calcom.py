"""Cal.com v2 booking. Written from the public docs (UNVERIFIED live). The `cal-api-version` values are settings, because the docs pages disagree."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx

from ringlark.adapters.base import BadReply, Booking, UnknownOutcome, dig, reply_json, safe_base_url
from sendora_core.adapters import AdapterError
from sendora_core.safety import write_action


def aware_utc(d: datetime) -> datetime:
    return d.replace(tzinfo=UTC) if d.tzinfo is None else d.astimezone(UTC)


def _iso(d: datetime) -> str:
    return d.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class CalcomCalendar:
    def __init__(self, settings, client: httpx.Client | None = None):
        self.settings = settings
        if client is not None:
            self.client = client
        else:
            if not settings.calcom_api_key or not settings.calcom_event_type_id:
                raise AdapterError("CALCOM_API_KEY and CALCOM_EVENT_TYPE_ID must both be set.")
            self.client = httpx.Client(base_url=safe_base_url(settings.calcom_base_url), timeout=15, headers={"Authorization": f"Bearer {settings.calcom_api_key}"})

    def _check(self, r: httpx.Response, what: str) -> dict:
        if r.status_code == 401:
            raise AdapterError("Cal.com rejected the API key.")
        if r.status_code >= 500:
            raise UnknownOutcome(f"Cal.com could not {what}: it answered {r.status_code}, so the result is not known.")  # it may have saved the booking before it failed
        if r.status_code >= 400:
            raise AdapterError(f"Cal.com could not {what}: {self._message(r)}")
        return reply_json(r, "Cal.com")

    @staticmethod
    def _message(r: httpx.Response):
        try:
            err = r.json().get("error")
            return err.get("message", r.status_code) if isinstance(err, dict) else r.status_code
        except (ValueError, AttributeError):
            return r.status_code

    def slots(self, start: datetime, end: datetime) -> list[datetime]:
        r = self.client.get("/v2/slots", params={"eventTypeId": self.settings.calcom_event_type_id, "start": _iso(start), "end": _iso(end)},
                            headers={"cal-api-version": self.settings.calcom_slots_version})
        data = dig(self._check(r, "list open times"), "data", who="Cal.com")
        try:
            out = [datetime.fromisoformat(s["start"].replace("Z", "+00:00")) for day in data.values() for s in day]
            return sorted(aware_utc(x) for x in out)[:6]
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise BadReply("Cal.com sent open times in a shape that could not be read.") from exc

    @write_action("calendar.book")
    def book(self, *, start: datetime, name: str, email: str, timezone: str) -> Booking:
        body = {"start": _iso(start), "eventTypeId": self.settings.calcom_event_type_id, "attendee": {"name": name, "email": email, "timeZone": timezone}}
        r = self.client.post("/v2/bookings", json=body, headers={"cal-api-version": self.settings.calcom_bookings_version})
        b = dig(self._check(r, "book the call"), "data", who="Cal.com")
        try:
            s = datetime.fromisoformat(b["start"].replace("Z", "+00:00"))
            e = datetime.fromisoformat(b["end"].replace("Z", "+00:00")) if b.get("end") else s + timedelta(minutes=30)
            ref = b.get("uid") or b.get("id")
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise BadReply("Cal.com answered the booking in a shape that could not be read, so it is not known whether the booking was made.") from exc
        if not ref:
            raise BadReply("Cal.com answered the booking without a booking reference, so it is not known whether the booking was made.")
        return Booking(str(ref), s, e)

    def healthcheck(self) -> tuple[bool, str]:
        try:
            now = datetime.now(UTC)
            self.slots(now, now + timedelta(days=3))
            return True, "Cal.com answered and the event type exists."
        except AdapterError as exc:
            return False, str(exc)
        except httpx.HTTPError as exc:
            return False, f"Could not reach Cal.com: {type(exc).__name__}."
