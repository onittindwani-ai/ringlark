"""The tools the agent can use during a call. The same code serves the HTTP tool endpoints and the offline demo.

Safety by design: a tool can only act on the person on this call (the text goes to their number, the transfer goes to the agent's own configured number),
nothing a caller says can widen that, and every write goes through the draft mode and kill switch guards.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from ringlark import messages, sms_rules, suppression
from ringlark.models import DISPOSITIONS, Agent, Call, ConsentRecord, Disposition, FollowUp, Target
from ringlark.util import aware, is_valid_email, normalize_phone
from sendora_core.adapters import AdapterError
from sendora_core.models import Event
from sendora_core.audit import record_audit
from sendora_core.events import record_event
from sendora_core.safety import SafetyError, guard_write

STOP_LINE = messages.STOP_LINE
BOOK_AHEAD = timedelta(days=14)  # the agent may only book a time the calendar itself offers inside this window


class ToolService:
    def __init__(self, session: Session, ctx, call: Call, slot_map: dict[str, datetime] | None = None):
        self.s, self.ctx, self.call = session, ctx, call
        self.settings = ctx.effective(session)
        self.slot_map = slot_map or {}
        self.agent = session.get(Agent, call.agent_id)
        self.target = session.get(Target, call.target_id) if call.target_id else None
        self.now = ctx.now(session)

    def run(self, tool: str, args: dict) -> dict:
        fn = getattr(self, f"t_{tool}", None)
        if fn is None:
            return {"ok": False, "error": "unknown_tool"}
        try:
            out = fn(args or {})
        except SafetyError as exc:
            record_event(self.s, "tool.blocked", "call", str(self.call.id), {"tool": tool, "why": type(exc).__name__})
            return {"ok": False, "blocked": True, "say": "I have noted that, and someone will follow up with you."}
        record_event(self.s, "tool.used", "call", str(self.call.id), {"tool": tool, "ok": bool(out.get("ok"))})
        return out

    # ---- the six tools
    def t_book_meeting(self, a: dict) -> dict:
        name, slot = str(a.get("name") or "").strip(), str(a.get("slot") or "")
        if not name:
            return {"ok": False, "say": "I need a name to book."}
        when = self.slot_map.get(slot)
        if when is None:
            try:
                when = datetime.fromisoformat(slot.replace("Z", "+00:00"))
            except ValueError:
                return {"ok": False, "say": "I did not catch which time you want."}
        email = (a.get("email") or (self.target.email if self.target else "") or "").strip()
        if not email or not is_valid_email(email):
            return {"ok": False, "say": "I need one email address to send the booking to."}
        guard_write(self.settings, "calendar.book")  # first: draft mode and the kill switch answer before anything else
        if self._happened("meeting.booked"):
            return {"ok": False, "say": "This call already has a booking."}
        if slot not in self.slot_map and not self._offered(when):
            return {"ok": False, "say": "That time is not one I can book. I will offer the times that are open."}
        b = self.ctx.adapters.calendar.book(start=when, name=name, email=email, timezone=(self.target.timezone if self.target else "") or "UTC")
        record_event(self.s, "meeting.booked", "call", str(self.call.id), {"at": aware(b.starts_at).isoformat()})
        return {"ok": True, "booking_id": b.external_id, "starts_at": aware(b.starts_at).isoformat()}

    def _happened(self, kind: str) -> bool:
        """True when this tool already did its one job for this call (kind is the event it records)."""
        return self.s.scalar(select(Event.id).where(Event.kind == kind, Event.entity_id == str(self.call.id)).limit(1)) is not None

    def _offered(self, when: datetime) -> bool:
        """Is this time one the calendar offers? The prompt only asks the agent to use offered times, so the code checks it."""
        try:
            slots = self.ctx.adapters.calendar.slots(self.now, self.now + BOOK_AHEAD)
        except AdapterError:
            return False
        return any(aware(x) == aware(when) for x in slots)

    def t_lookup_crm(self, a: dict) -> dict:
        if self.call.direction == "inbound":
            # An inbound caller is whoever the caller ID says, and caller ID can be faked: no name is read back to them.
            return {"ok": True, "found": False, "first_name": "", "last_name": ""}
        p = self.ctx.adapters.crm.find_by_phone(self.call.peer_phone)
        if p is None and self.target is not None:
            return {"ok": True, "found": True, "first_name": self.target.first_name, "last_name": self.target.last_name}
        return {"ok": True, "found": p is not None, "first_name": p.first_name if p else "", "last_name": p.last_name if p else ""}

    def _office_open(self) -> bool:
        start, end = self.settings.human_transfer_hours.split("-")
        loc = aware(self.now).astimezone(ZoneInfo(self.settings.office_timezone))
        hm = loc.strftime("%H:%M")
        return loc.weekday() < 5 and start <= hm < end

    def t_transfer_to_human(self, a: dict) -> dict:
        number = normalize_phone(self.agent.transfer_number)
        if not number:
            return {"ok": False, "say": "No one is set up to take transfers, so I will arrange a call back."}
        if not self._office_open():
            return {"ok": False, "say": "The office is closed right now, so I will arrange a call back."}
        if self.call.taken_over:
            return {"ok": False, "say": "The call is already being handed over."}
        guard_write(self.settings, "call.transfer")
        self.ctx.adapters.telephony.transfer(self.call.telnyx_call_id, number)  # the only number it can ever go to
        self.call.taken_over = True
        record_audit(self.s, "agent", "call.transferred", f"call:{self.call.id}", {"reason": str(a.get("reason", ""))[:120]})
        return {"ok": True}

    def _sms_allowed(self) -> tuple[bool, str]:
        d = sms_rules.sms_decision(self.s, self.settings, self.call.peer_phone, self.target, self.now)
        return d.allowed, d.reason

    def t_send_sms(self, a: dict) -> dict:
        kind = str(a.get("kind") or "")
        if kind not in messages.SMS_KINDS:
            return {"ok": False, "say": "I can send a booking link, a confirmation or a callback note."}
        text = messages.sms_text(self.settings, self.agent, kind)
        if text is None:
            return {"ok": False, "say": "I do not have a link to send, so someone will follow up."}
        if self.s.scalar(select(FollowUp.id).where(FollowUp.call_id == self.call.id, FollowUp.channel == "sms", FollowUp.body == text, FollowUp.status.in_(("sent", "pending", "drafted"))).limit(1)):
            return {"ok": False, "say": "I have already sent that text."}  # one text of each kind per call, however often the model asks
        ok, why = self._sms_allowed()
        fu = FollowUp(call_id=self.call.id, channel="sms", to=self.call.peer_phone, body=text, status="blocked" if not ok else "pending", blocked_reason="" if ok else why)
        self.s.add(fu)
        self.s.flush()
        if not ok:
            return {"ok": False, "say": "I will not text you unless you have agreed to texts."}
        guard_write(self.settings, "sms.send")
        self.ctx.adapters.sms.send(to=self.call.peer_phone, text=text)
        fu.status = "sent"
        return {"ok": True}

    def t_press_digit(self, a: dict) -> dict:
        from ringlark.models import Campaign

        c = self.s.get(Campaign, self.call.campaign_id) if self.call.campaign_id else None
        digit = str(a.get("digit") or "")
        if not c or c.ivr_policy != "press_once" or not c.ivr_extension or digit != c.ivr_extension:
            return {"ok": False, "say": "Not allowed."}
        from sendora_core.models import Event

        if self.s.scalar(select(Event.id).where(Event.kind == "call.dtmf", Event.entity_id == str(self.call.id))):
            return {"ok": False, "say": "Already pressed once."}
        guard_write(self.settings, "call.dtmf")
        self.ctx.adapters.telephony.send_dtmf(self.call.telnyx_call_id, digit)
        record_event(self.s, "call.dtmf", "call", str(self.call.id), {"digit": digit})
        return {"ok": True}

    def t_end_call(self, a: dict) -> dict:
        code = str(a.get("disposition") or "")
        if code not in DISPOSITIONS:
            code = "needs_review"
        row = self.s.scalar(select(Disposition).where(Disposition.call_id == self.call.id))
        if row is None:
            self.s.add(Disposition(call_id=self.call.id, code=code, note=str(a.get("note") or "")[:300], set_by="agent"))
        self.call.disposition = code
        if code in ("do_not_call", "wrong_number"):
            suppression.add_suppression(self.s, self.call.peer_phone, "Said so on the call" if code == "do_not_call" else "Wrong number", f"call:{self.call.id}", actor="agent")
            if self.target:
                self.target.status = "suppressed"
        if self.call.telnyx_call_id:
            try:
                self.ctx.adapters.telephony.hangup(self.call.telnyx_call_id)
            except SafetyError:
                pass
        self.s.flush()
        return {"ok": True, "disposition": code}


def revoke_sms(session: Session, phone: str, source: str) -> None:
    p = normalize_phone(phone)
    session.add(ConsentRecord(phone=p, kind="sms", status="revoked", source=source))
    session.flush()
