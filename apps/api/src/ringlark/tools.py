"""The tools the agent can use during a call. The same code serves the HTTP tool endpoints and the offline demo.

Safety by design: a tool can only act on the person on this call (the text goes to their number, the transfer goes to the agent's own configured number),
nothing a caller says can widen that, and every write goes through the draft mode and kill switch guards.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from ringlark import suppression
from ringlark.models import DISPOSITIONS, Agent, Call, ConsentRecord, Disposition, FollowUp, Target
from ringlark.util import aware, normalize_phone
from sendora_core.audit import record_audit
from sendora_core.events import record_event
from sendora_core.safety import SafetyError, guard_write

SMS_TEXT = {
    "booking_link": "Hi from Harbor Light Dental. Here is where to manage your booking: https://example.test/book (fictional demo link). Reply STOP to opt out.",
    "confirmation": "Harbor Light Dental: your check up is booked. We will see you then. Reply STOP to opt out.",
    "callback": "Harbor Light Dental: sorry we caught you at a busy time. We will call you back at a better time. Reply STOP to opt out.",
}
STOP_LINE = "Reply STOP to opt out."


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
            return {"ok": False, "blocked": True, "say": "I have noted that and someone from the practice will follow up."}
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
        if not email:
            return {"ok": False, "say": "I need an email address to send the booking to."}
        guard_write(self.settings, "calendar.book")
        b = self.ctx.adapters.calendar.book(start=when, name=name, email=email, timezone=(self.target.timezone if self.target else "") or "UTC")
        record_event(self.s, "meeting.booked", "call", str(self.call.id), {"at": aware(b.starts_at).isoformat()})
        return {"ok": True, "booking_id": b.external_id, "starts_at": aware(b.starts_at).isoformat()}

    def t_lookup_crm(self, a: dict) -> dict:
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
        guard_write(self.settings, "call.transfer")
        self.ctx.adapters.telephony.transfer(self.call.telnyx_call_id, number)  # the only number it can ever go to
        self.call.taken_over = True
        record_audit(self.s, "agent", "call.transferred", f"call:{self.call.id}", {"reason": str(a.get("reason", ""))[:120]})
        return {"ok": True}

    def _sms_allowed(self) -> tuple[bool, str]:
        phone = self.call.peer_phone
        if suppression.is_suppressed(self.s, phone):
            return False, "suppressed"
        latest = suppression.latest_consent(self.s, phone, "sms")
        if latest == "revoked":
            return False, "sms_revoked"
        if latest != "granted" and not (self.target and self.target.sms_consent):
            return False, "no_sms_consent"
        loc = aware(self.now).astimezone(ZoneInfo(self.target.timezone)) if self.target and self.target.timezone else None
        if loc is not None and not (self.settings.sms_window_start <= loc.hour < self.settings.sms_window_end):
            return False, "sms_quiet_hours"
        return True, "ok"

    def t_send_sms(self, a: dict) -> dict:
        kind = str(a.get("kind") or "")
        if kind not in SMS_TEXT:
            return {"ok": False, "say": "I can send a booking link, a confirmation or a callback note."}
        ok, why = self._sms_allowed()
        fu = FollowUp(call_id=self.call.id, channel="sms", to=self.call.peer_phone, body=SMS_TEXT[kind], status="blocked" if not ok else "pending", blocked_reason="" if ok else why)
        self.s.add(fu)
        self.s.flush()
        if not ok:
            return {"ok": False, "say": "I will not text you unless you have agreed to texts."}
        guard_write(self.settings, "sms.send")
        self.ctx.adapters.sms.send(to=self.call.peer_phone, text=SMS_TEXT[kind])
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
