"""The tools the agent can use during a call. The same code serves the HTTP tool endpoints and the offline demo.

Safety by design: a tool can only act on the person on this call (the text goes to their number, the transfer goes to the agent's own configured number),
nothing a caller says can widen that, and every write goes through the draft mode and kill switch guards.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ringlark import messages, sms_rules, suppression, times
from ringlark.adapters.base import UNKNOWN_OUTCOME
from ringlark.models import DISPOSITIONS, Agent, Call, CallAction, ConsentRecord, Disposition, FollowUp, Target
from ringlark.util import aware, is_valid_email, normalize_phone
from sendora_core.adapters import AdapterError
from sendora_core.models import Event
from sendora_core.audit import record_audit
from sendora_core.events import record_event
from sendora_core.safety import SafetyError, guard_write

VENDOR_ERRORS = (AdapterError, httpx.HTTPError, OSError)  # a refused request, a timeout or a dropped connection at Cal.com, Telnyx, the CRM or Ultravox
STOP_LINE = messages.STOP_LINE
BOOK_AHEAD = times.OFFER_AHEAD


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
        except VENDOR_ERRORS as exc:
            # A vendor that is slow or down must not turn into a 500: the voice engine would retry the tool and could book or text twice.
            record_event(self.s, "tool.failed", "call", str(self.call.id), {"tool": tool, "why": type(exc).__name__})
            return {"ok": False, "failed": True, "say": "I could not finish that just now, and someone will follow up with you."}
        record_event(self.s, "tool.used", "call", str(self.call.id), {"tool": tool, "ok": bool(out.get("ok"))})
        return out

    def _claim(self, kind: str) -> bool:
        """Take the one time right to do `kind` on this call, and SAVE it before the vendor is asked. Two requests that arrive together both pass the "has it
        happened" check, because nothing is written until the vendor answers; this row is what stops the second one (a unique key on call and kind)."""
        try:
            self.s.add(CallAction(call_id=self.call.id, kind=kind))
            self.s.flush()
        except IntegrityError:
            self.s.rollback()  # nothing else is pending at this point: every caller claims before it writes anything of its own
            return False
        return True

    def _release(self, kind: str) -> None:
        """Give the right back after a vendor that definitely did nothing (a refusal), so the agent may try again. A timeout or a 5xx never comes here."""
        self.s.execute(delete(CallAction).where(CallAction.call_id == self.call.id, CallAction.kind == kind))
        self.s.commit()

    # ---- the seven tools
    def t_book_meeting(self, a: dict) -> dict:
        name, slot = a.get("name"), str(a.get("slot") or "")
        name = name.strip() if isinstance(name, str) else ""
        if not name:
            return {"ok": False, "say": "I need a name to book."}
        when = self.slot_map.get(slot)
        if when is None:
            try:
                when = datetime.fromisoformat(slot.replace("Z", "+00:00"))
            except ValueError:
                return self._times_answer("I did not catch which time you want.")
            if when.tzinfo is None:
                # A time with no offset would be read as UTC, which is the wrong hour for almost everyone. The offered times always carry their offset.
                return self._times_answer("I need the time exactly as it was offered, with its offset.")
        given = a.get("email")
        if given is not None and not isinstance(given, str):
            return {"ok": False, "say": "I need one email address to send the booking to."}  # a number or a list from the model is not an address, and must not become a 500
        email = (given or (self.target.email if self.target else "") or "").strip()
        if not email or not is_valid_email(email):
            return {"ok": False, "say": "I need one email address to send the booking to."}
        guard_write(self.settings, "calendar.book")  # first: draft mode and the kill switch answer before anything else
        if self._happened("meeting.booked"):
            return {"ok": False, "say": "This call already has a booking."}
        if self._happened("meeting.unconfirmed"):
            return {"ok": False, "say": "I could not confirm a booking on this call, so someone will follow up with you to be sure."}
        if slot not in self.slot_map and not self._offered(when):
            return self._times_answer("That time is not one I can book.")
        if not self._claim("book_meeting"):
            return {"ok": False, "say": "This call already has a booking."}  # another request for this call got there first
        self.s.commit()  # the right to book is saved BEFORE Cal.com is asked
        try:
            b = self.ctx.adapters.calendar.book(start=when, name=name, email=email, timezone=(self.target.timezone if self.target else "") or "UTC")
        except UNKNOWN_OUTCOME as exc:
            # Cal.com may have saved the booking before the answer was lost (a timeout, a dropped line or a 5xx). Booking again could book twice, so this call tries once and a person confirms.
            record_event(self.s, "meeting.unconfirmed", "call", str(self.call.id), {"why": type(exc).__name__})
            self.s.commit()
            return {"ok": False, "failed": True, "say": "I could not confirm that booking, so someone will follow up with you to be sure."}
        except (AdapterError, SafetyError):
            self._release("book_meeting")  # a refusal: nothing was booked, the agent may offer another time
            raise
        record_event(self.s, "meeting.booked", "call", str(self.call.id), {"at": aware(b.starts_at).isoformat()})
        self.s.commit()  # visible to the next request (end_call "booked") before this answer is sent
        return {"ok": True, "booking_id": b.external_id, "starts_at": aware(b.starts_at).isoformat()}

    def _zone_name(self) -> str:
        return (self.target.timezone if self.target and self.target.timezone else "") or self.settings.office_timezone

    def _times_answer(self, lead: str) -> dict:
        """A refusal that also carries the times that ARE open, so the model always has something true to offer next."""
        try:
            offered = times.open_times(self.ctx.adapters.calendar, self.now, self._zone_name())
        except times.CALENDAR_ERRORS:
            return {"ok": False, "say": f"{lead} Use list_times to get the open times."}
        spoken = "; ".join(t.say for t in offered)
        return {"ok": False, "say": f"{lead} The open times are: {spoken}." if offered else f"{lead} There are no open times in the next two weeks, so someone will follow up.",
                "times": [{"slot": t.slot, "say": t.say} for t in offered]}

    def t_list_times(self, a: dict) -> dict:
        """The open times the agent may offer. A read, so it needs no write guard; a calendar that is down is a plain answer from run()."""
        offered = times.open_times(self.ctx.adapters.calendar, self.now, self._zone_name())
        if not offered:
            return {"ok": True, "times": [], "say": "There are no open times in the next two weeks, so someone will follow up."}
        return {"ok": True, "times": [{"slot": t.slot, "say": t.say} for t in offered]}

    def _happened(self, kind: str) -> bool:
        """True when this tool already did its one job for this call (kind is the event it records)."""
        return happened(self.s, self.call.id, kind)

    def _offered(self, when: datetime) -> bool:
        """Is this time one the calendar offers? The prompt only asks the agent to use offered times, so the code checks it."""
        try:
            slots = self.ctx.adapters.calendar.slots(self.now, self.now + BOOK_AHEAD)
        except VENDOR_ERRORS:
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
        if not self._claim("transfer"):
            return {"ok": False, "say": "The call is already being handed over."}
        self.s.commit()
        try:
            self.ctx.adapters.telephony.transfer(self.call.telnyx_call_id, number)  # the only number it can ever go to
        except UNKNOWN_OUTCOME:
            raise  # it may have gone through: not tried again on this call
        except (AdapterError, SafetyError):
            self._release("transfer")
            raise
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
        same = (FollowUp.status.in_(("sent", "sending", "pending", "drafted"))) | (FollowUp.blocked_reason == "send_unconfirmed")
        if self.s.scalar(select(FollowUp.id).where(FollowUp.call_id == self.call.id, FollowUp.channel == "sms", FollowUp.body == text, same).limit(1)):
            return {"ok": False, "say": "I have already sent that text."}  # one text of each kind per call, however often the model asks
        ok, why = self._sms_allowed()
        if not ok:
            self.s.add(FollowUp(call_id=self.call.id, channel="sms", to=self.call.peer_phone, body=text, status="blocked", blocked_reason=why))
            self.s.flush()
            return {"ok": False, "say": "I will not text you unless you have agreed to texts."}
        guard_write(self.settings, "sms.send")
        if not self._claim(f"sms:{kind}"):
            return {"ok": False, "say": "I have already sent that text."}  # another request for this call got there first
        fu = FollowUp(call_id=self.call.id, channel="sms", to=self.call.peer_phone, body=text, status="sending")
        self.s.add(fu)
        self.s.commit()  # the claim and the row are saved BEFORE Telnyx is asked, so a second request sees them
        try:
            self.ctx.adapters.sms.send(to=self.call.peer_phone, text=text)
        except UNKNOWN_OUTCOME:
            fu.status, fu.blocked_reason = "blocked", "send_unconfirmed"  # it may have gone out: the same text is not tried again on this call
            self.s.commit()
            raise
        except (AdapterError, SafetyError):
            fu.status, fu.blocked_reason = "blocked", "send_failed"  # the vendor refused it: nothing went out
            self.s.commit()
            self._release(f"sms:{kind}")
            raise
        fu.status = "sent"
        self.s.commit()
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
        if not self._claim("dtmf"):
            return {"ok": False, "say": "Already pressed once."}
        self.s.commit()
        try:
            self.ctx.adapters.telephony.send_dtmf(self.call.telnyx_call_id, digit)
        except UNKNOWN_OUTCOME:
            raise
        except (AdapterError, SafetyError):
            self._release("dtmf")
            raise
        record_event(self.s, "call.dtmf", "call", str(self.call.id), {"digit": digit})
        return {"ok": True}

    def t_end_call(self, a: dict) -> dict:
        code, note = str(a.get("disposition") or ""), str(a.get("note") or "")[:300]
        if code not in DISPOSITIONS:
            code = "needs_review"
        if code == "booked" and not self._happened("meeting.booked"):
            # "Booked" is true only after a booking that passed the checks. A model error or a caller's push must not close the person, write the CRM or queue a
            # "your appointment is booked" text, so the call goes to a person to read instead.
            lead = ("A booking was tried and Cal.com's answer could not be confirmed: check the calendar before anything else. "
                    if self._happened("meeting.unconfirmed") else "Said booked but no booking was made on this call. ")
            code, note = "needs_review", (lead + note).strip()[:300]
            record_event(self.s, "tool.downgraded", "call", str(self.call.id), {"tool": "end_call", "from": "booked", "to": "needs_review"})
        row = self.s.scalar(select(Disposition).where(Disposition.call_id == self.call.id))
        if row is None:
            self.s.add(Disposition(call_id=self.call.id, code=code, note=note, set_by="agent"))
        self.call.disposition = code
        if code in ("do_not_call", "wrong_number"):
            suppression.add_suppression(self.s, self.call.peer_phone, "Said so on the call" if code == "do_not_call" else "Wrong number", f"call:{self.call.id}", actor="agent")
            if self.target:
                self.target.status = "suppressed"
        if self.call.telnyx_call_id:
            try:
                self.ctx.adapters.telephony.hangup(self.call.telnyx_call_id)
            except (SafetyError, *VENDOR_ERRORS):
                pass  # the outcome is saved either way; a call that is still up ends when the voice engine hangs up
        self.s.flush()
        return {"ok": True, "disposition": code}


def happened(session: Session, call_id: int, kind: str) -> bool:
    """True when an event of this kind was recorded for this call (for example `meeting.booked`, which only a booking that passed the checks writes)."""
    return session.scalar(select(Event.id).where(Event.kind == kind, Event.entity_id == str(call_id)).limit(1)) is not None


def revoke_sms(session: Session, phone: str, source: str) -> None:
    p = normalize_phone(phone)
    session.add(ConsentRecord(phone=p, kind="sms", status="revoked", source=source))
    session.flush()
