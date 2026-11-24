"""Fake Cal.com v2 API for slots and bookings, written from the public docs (UNVERIFIED against the real service).

GET /v2/slots?eventTypeId&start&end and POST /v2/bookings need `Authorization: Bearer` and a `cal-api-version` header.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse


class CalcomMock:
    def __init__(self, api_key: str = "mock-cal-key", event_type_id: int = 1001):
        self.api_key, self.event_type_id = api_key, event_type_id
        self.bookings: dict[str, dict] = {}
        self.app = self._build()

    def _auth(self, authorization: str | None, version: str | None):
        if authorization != f"Bearer {self.api_key}":
            return JSONResponse({"status": "error", "error": {"message": "Invalid API key"}}, 401)
        if not version:
            return JSONResponse({"status": "error", "error": {"message": "cal-api-version header is required"}}, 400)
        return None

    def _build(self) -> FastAPI:
        app = FastAPI(title="Cal.com mock")

        @app.get("/v2/slots")
        def slots(eventTypeId: int, start: str, end: str, authorization: str | None = Header(default=None), cal_api_version: str | None = Header(default=None)):
            bad = self._auth(authorization, cal_api_version)
            if bad:
                return bad
            if eventTypeId != self.event_type_id:
                return JSONResponse({"status": "error", "error": {"message": "event type not found"}}, 404)
            day0 = datetime.fromisoformat(start.replace("Z", "+00:00")).astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
            day1 = datetime.fromisoformat(end.replace("Z", "+00:00")).astimezone(UTC)
            data: dict[str, list[dict]] = {}
            d = day0
            while d <= day1 and len(data) < 7:
                if d.weekday() < 5:
                    data[d.date().isoformat()] = [{"start": (d + timedelta(hours=h)).isoformat().replace("+00:00", "Z")} for h in (15, 16, 17)
                                                   if not any(b["start"] == (d + timedelta(hours=h)).isoformat().replace("+00:00", "Z") for b in self.bookings.values())]
                d += timedelta(days=1)
            return {"status": "success", "data": data}

        @app.post("/v2/bookings", status_code=201)
        async def book(request: Request, authorization: str | None = Header(default=None), cal_api_version: str | None = Header(default=None)):
            bad = self._auth(authorization, cal_api_version)
            if bad:
                return bad
            body = await request.json()
            att = body.get("attendee") or {}
            if not body.get("start") or not att.get("name") or not att.get("timeZone"):
                return JSONResponse({"status": "error", "error": {"message": "start, attendee.name and attendee.timeZone are required"}}, 400)
            if body.get("eventTypeId") != self.event_type_id:
                return JSONResponse({"status": "error", "error": {"message": "event type not found"}}, 404)
            start = body["start"]
            if any(b["start"] == start for b in self.bookings.values()):
                return JSONResponse({"status": "error", "error": {"message": "slot is already booked"}}, 409)
            end = (datetime.fromisoformat(start.replace("Z", "+00:00")) + timedelta(minutes=30)).isoformat().replace("+00:00", "Z")
            b = {"id": len(self.bookings) + 1, "uid": uuid.uuid4().hex[:12], "status": "accepted", "start": start, "end": end, "duration": 30,
                 "eventTypeId": self.event_type_id, "attendees": [att]}
            self.bookings[b["uid"]] = b
            return {"status": "success", "data": b}

        return app
