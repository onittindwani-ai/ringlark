"""Offline seed adapters. Nothing here touches a network. They are what demo mode and the tests use.

The seed inbox lives in the database (table rm_state) so the API and the worker, which are separate processes, see the same mail.
"""

from __future__ import annotations

import fcntl
import json
import uuid
from pathlib import Path
from datetime import UTC, datetime, timedelta

from ringlark.adapters.base import Booking, InboundEmail, PersonRecord, PlacedCall, VoiceCall
from sendora_core.safety import write_action
from sendora_core.settings import BaseAppSettings

def inbox_path(settings: BaseAppSettings) -> Path:
    return Path(getattr(settings, "handoff_dir", "./handoff")) / ".seed_inbox.json"


def _locked_update(path: Path, fn):
    """Read, change and write the inbox file under an exclusive lock, so the API and the worker can share it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a+") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        fh.seek(0)
        raw = fh.read()
        data = json.loads(raw) if raw.strip() else []
        data, out = fn(data)
        fh.seek(0)
        fh.truncate()
        fh.write(json.dumps(data))
        return out


def push_inbound_email(settings: BaseAppSettings, e: InboundEmail) -> None:
    """Used by the demo to drop a reply into the seed inbox. The reply poll job picks it up."""
    _locked_update(inbox_path(settings), lambda d: (d + [{"external_id": e.external_id, "from_addr": e.from_addr, "to_addr": e.to_addr, "subject": e.subject, "body": e.body}], None))


def clear_inbox(settings: BaseAppSettings) -> None:
    _locked_update(inbox_path(settings), lambda d: ([], None))


class SeedEmail:
    def __init__(self, settings: BaseAppSettings):
        self.settings = settings

    @write_action("email.send")
    def send(self, *, from_addr: str, to: str, subject: str, body: str) -> str:
        return f"seed-{uuid.uuid4().hex[:12]}"

    def fetch_replies(self) -> list[InboundEmail]:
        box = _locked_update(inbox_path(self.settings), lambda d: ([], d))
        return [InboundEmail(**m) for m in box]

    def healthcheck(self) -> tuple[bool, str]:
        return True, "Offline seed mailbox. Nothing leaves this machine."


class SeedSms:
    def __init__(self, settings: BaseAppSettings):
        self.settings = settings

    @write_action("sms.send")
    def send(self, *, to: str, text: str) -> str:
        return f"seed-sms-{uuid.uuid4().hex[:10]}"

    def healthcheck(self) -> tuple[bool, str]:
        return True, "Offline seed texting. Nothing is sent."


class SeedCalendar:
    def __init__(self, settings: BaseAppSettings):
        self.settings = settings

    def slots(self, start: datetime, end: datetime) -> list[datetime]:
        out, d = [], start.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        while d <= end and len(out) < 3:
            if d.weekday() < 5 and d >= start.replace(hour=0, minute=0, second=0, microsecond=0):
                for h in (15, 17):
                    t = d + timedelta(hours=h)
                    if t > start and len(out) < 3:
                        out.append(t)
            d += timedelta(days=1)
        return out

    @write_action("calendar.book")
    def book(self, *, start: datetime, name: str, email: str, timezone: str) -> Booking:
        return Booking(f"seed-booking-{uuid.uuid4().hex[:8]}", start, start + timedelta(minutes=30))

    def healthcheck(self) -> tuple[bool, str]:
        return True, "Offline seed calendar with fixed example times."


class SeedCrm:
    """The Ringlark database is the CRM. `people` is filled by tests and the demo to prove lookups."""

    def __init__(self, settings: BaseAppSettings):
        self.settings = settings
        self.people: dict[str, PersonRecord] = {}

    @write_action("crm.upsert")
    def upsert_person(self, person: PersonRecord) -> str:
        self.people[person.phone] = person
        return f"seed-crm-{abs(hash(person.phone or person.email)) % 10**8}"

    def find_by_phone(self, phone: str) -> PersonRecord | None:
        return self.people.get(phone)

    def healthcheck(self) -> tuple[bool, str]:
        return True, "Offline seed CRM (the database is the CRM)."


class SeedTelephony:
    """Offline telephony. It records what it was asked to do and touches no network."""

    def __init__(self, settings: BaseAppSettings):
        self.settings = settings
        self.log: list[tuple[str, str]] = []

    @write_action("call.place")
    def place_call(self, *, to: str, from_number: str, client_state: str, amd: bool) -> PlacedCall:
        cid = f"seed-cc-{uuid.uuid4().hex[:10]}"
        self.log.append(("place", to))
        return PlacedCall(cid, f"seed-sess-{uuid.uuid4().hex[:6]}")

    def answer(self, call_control_id: str) -> None:
        self.log.append(("answer", call_control_id))

    def start_stream(self, call_control_id: str, join_url: str) -> None:
        self.log.append(("stream", call_control_id))

    @write_action("call.transfer")
    def transfer(self, call_control_id: str, to: str) -> None:
        self.log.append(("transfer", to))

    def send_dtmf(self, call_control_id: str, digits: str) -> None:
        self.log.append(("dtmf", digits))

    def speak(self, call_control_id: str, text: str) -> None:
        self.log.append(("speak", text[:40]))

    def hangup(self, call_control_id: str) -> None:
        self.log.append(("hangup", call_control_id))

    def healthcheck(self) -> tuple[bool, str]:
        return True, "Offline seed telephony. No call is placed."


class SeedVoice:
    def __init__(self, settings: BaseAppSettings):
        self.settings = settings

    def create_call(self, *, system_prompt: str, voice: str, first_message: str, tools: list[dict], max_seconds: int, external_voice: dict | None = None) -> VoiceCall:
        return VoiceCall(f"seed-uv-{uuid.uuid4().hex[:10]}", "")

    def transcript(self, call_id: str) -> list[dict]:
        return []

    def healthcheck(self) -> tuple[bool, str]:
        return True, "Offline seed voice engine. No audio is made."
