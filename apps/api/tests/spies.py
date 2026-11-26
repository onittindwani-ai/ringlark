"""Small stand in adapters that remember what they were asked to do, for tests of the safety rules."""

from __future__ import annotations

from ringlark.adapters.base import VoiceCall
from sendora_core.adapters import AdapterError


class SpySms:
    def __init__(self, fail_for: set[str] | None = None):
        self.sent: list[tuple[str, str]] = []
        self.fail_for = fail_for or set()

    def send(self, *, to: str, text: str) -> str:
        if to in self.fail_for:
            raise AdapterError("Telnyx refused to send the text: landline")
        self.sent.append((to, text))
        return "spy-sms"

    def healthcheck(self):
        return True, "spy"


class SpyEmail:
    def __init__(self, fail_for: set[str] | None = None):
        self.sent: list[tuple[str, str, str]] = []
        self.fail_for = fail_for or set()

    def send(self, *, from_addr: str, to: str, subject: str, body: str) -> str:
        if to in self.fail_for:
            raise AdapterError("bounce")
        self.sent.append((to, subject, body))
        return "spy-mail"

    def fetch_replies(self):
        return []

    def healthcheck(self):
        return True, "spy"


class SpyCrm:
    def __init__(self):
        self.writes: list[object] = []

    def upsert_person(self, person):
        self.writes.append(person)
        return "spy-crm"

    def find_by_phone(self, phone):
        return None

    def healthcheck(self):
        return True, "spy"


class SpyVoice:
    """Records every system prompt and, when given a session factory, whether the call row was already saved when the voice engine was called."""

    def __init__(self, factory=None, fail: bool = False, transcripts: dict | None = None):
        self.transcripts = transcripts or {}
        self.prompts: list[str] = []
        self.rows_seen: list[str | None] = []
        self.factory, self.fail, self.n = factory, fail, 0

    def create_call(self, *, system_prompt: str, voice: str, first_message: str, tools: list[dict], max_seconds: int, external_voice=None) -> VoiceCall:
        self.prompts.append(system_prompt)
        self.n += 1
        if self.factory is not None:
            from sqlalchemy import select

            from ringlark.models import Call

            with self.factory() as other:  # a second connection: only committed rows are visible here
                row = other.scalars(select(Call).order_by(Call.id.desc())).first()
                self.rows_seen.append(row.status if row else None)
        if self.fail:
            raise AdapterError("Ultravox refused to create the call: 500")
        return VoiceCall(f"spy-uv-{self.n}", "wss://spy.invalid/join")

    def transcript(self, call_id):
        return list(self.transcripts.get(call_id, []))

    def healthcheck(self):
        return True, "spy"


class SpyTelephony:
    def __init__(self, fail: bool = False):
        self.log: list[tuple[str, str]] = []
        self.fail = fail

    def place_call(self, *, to, from_number, client_state, amd):
        if self.fail:
            raise AdapterError("Telnyx refused to place the call")
        from ringlark.adapters.base import PlacedCall

        self.log.append(("place", to))
        return PlacedCall(f"spy-cc-{len(self.log)}", "sess")

    def answer(self, cid):
        self.log.append(("answer", cid))

    def start_stream(self, cid, url):
        self.log.append(("stream", cid))

    def transfer(self, cid, to):
        self.log.append(("transfer", to))

    def send_dtmf(self, cid, digits):
        self.log.append(("dtmf", digits))

    def speak(self, cid, text):
        self.log.append(("speak", text[:20]))

    def hangup(self, cid):
        self.log.append(("hangup", cid))

    def healthcheck(self):
        return True, "spy"
