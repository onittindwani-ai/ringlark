"""Handling the live events that come from Telnyx and Ultravox. Every handler can run twice on the same event and give the same result."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ringlark import suppression, times
from ringlark.adapters.base import VoiceCall
from ringlark.adapters.telnyx import decode_state
from ringlark.adapters.ultravox import tool_definitions
from ringlark.caller_reader import asks_to_stop, revoked_consent
from ringlark.compliance import voicemail_allowed
from ringlark.context import set_state
from ringlark.disclosure import build_greeting, greeting_problems
from ringlark.live_prompt import live_system_prompt
from ringlark.models import Agent, Call, Campaign, ConsentRecord, Disposition, Number, PromptVersion, State
from ringlark.toolauth import secret_for, tool_base_url, tool_token
from ringlark.util import aware, normalize_phone
from sendora_core.adapters import AdapterError
from sendora_core.audit import record_audit
from sendora_core.events import record_event
from sendora_core.jobs import enqueue
from sendora_core.safety import SafetyError, guard_write

START_WORDS = re.compile(r"^\s*(start|unstop)\s*[.!]?\s*$", re.I)  # only the carrier word. A plain "yes" never gives consent
IN_FLIGHT = ("placing", "placed", "in_progress")
ANONYMOUS_NUMBERS = ("+266696687",)  # the number carriers show for a withheld caller ID (it spells ANONYMOUS on the keypad). Which one Telnyx sends is UNVERIFIED: anything that is not a number counts as withheld too
VOICEMAIL_WAIT = "vm_wait:"  # State key per call while a voicemail is being left: "beep|<time>" (waiting for the greeting to end), then "speaking|<time>"
BEEP_TIMEOUT_S = 60  # no end-of-greeting event this long after the machine was detected: hang up, nothing is said
SPEECH_TIMEOUT_S = 90  # the message was started but its end was never reported: hang up, and the call is not recorded as a message left


class CallNotFoundYet(LookupError):
    """An event names a call this app should have recorded already. The webhook answers 503, so the sender tries again instead of the event being lost."""


def inbound_greeting(agent: Agent, settings=None) -> str:
    """What the answering agent says first. A custom greeting is used only when it says it is an AI and (unless RECORDING_NOTICE_REQUIRED is off) that the call may be recorded;
    otherwise the standard greeting is used, so a greeting typed or imported without those words never reaches a caller."""
    company = (agent.company or (settings.company_name if settings is not None else "") or "us").strip()
    standard = f"Thanks for calling {company}. This is {agent.name}, an AI assistant. This call may be recorded and transcribed. How can I help?"
    if agent.greeting and not greeting_problems(agent.greeting, True if settings is None else settings.recording_notice_required):
        return agent.greeting
    return standard


def _find(session: Session, payload: dict) -> Call | None:
    state = decode_state(payload.get("client_state"))
    if state.get("call"):
        call = session.get(Call, int(state["call"]))
        if call is None:
            raise CallNotFoundYet(str(state["call"]))
        return call
    cid = payload.get("call_control_id")
    return session.scalars(select(Call).where(Call.telnyx_call_id == cid)).first() if cid else None


def _stream(ctx, settings, call: Call, join_url: str) -> bool:
    """Start the audio between the phone call and the voice engine. The kill switch and draft mode stop it, and then the call is hung up."""
    if not join_url:
        return True
    try:
        guard_write(settings, "call.stream")
    except SafetyError:
        try:
            ctx.adapters.telephony.hangup(call.telnyx_call_id)
        except (AdapterError, OSError):
            pass
        call.blocked_reason = "kill_switch_hangup"
        return False
    ctx.adapters.telephony.start_stream(call.telnyx_call_id, join_url)
    return True


def handle_telnyx_event(session: Session, ctx, settings, event_type: str, payload: dict) -> str:
    if event_type == "message.received":
        return handle_sms(session, payload)
    if event_type == "call.initiated" and payload.get("direction") == "incoming":
        return handle_inbound(session, ctx, settings, payload)
    call = _find(session, payload)
    if call is None:
        return "unknown_call"
    if event_type == "call.answered" and call.status == "placed" and call.direction == "outbound":
        # With answering machine detection on, wait for its result before the agent speaks.
        return "waiting_for_detection"
    if event_type == "call.machine.detection.ended":
        result = payload.get("result", "not_sure")
        if call.answered_by:
            return "already_handled"
        if result == "machine":
            return handle_machine(session, ctx, settings, call)
        call.answered_by = "human"
        if not _stream(ctx, settings, call, decode_state(payload.get("client_state")).get("join", "")):
            return "blocked_by_safety"
        return "streaming"
    if event_type == "call.machine.greeting.ended":  # the beep (event name UNVERIFIED against live Telnyx)
        return handle_beep(session, ctx, settings, call)
    if event_type == "call.speak.ended":
        return handle_speech_ended(session, ctx, call)
    if event_type == "call.hangup":
        if session.get(State, f"{VOICEMAIL_WAIT}{call.id}") is not None:
            return end_voicemail(session, ctx, call, "voicemail_no_message", "The line was closed before the message finished, so no message is recorded as left.")
        if call.status in ("placing", "placed", "in_progress"):
            call.status = "in_progress"
            enqueue(session, "postcall")
        return "hangup_seen"
    return "ignored"


def handle_machine(session: Session, ctx, settings, call: Call) -> str:
    """An answering machine picked up. A message is only left when the campaign allows it and the text says who and why, and it is NOT spoken now: the machine's own greeting is
    still playing, so the words would be cut off at the start. The message waits for the end of the greeting (the beep, see handle_beep)."""
    camp = session.get(Campaign, call.campaign_id) if call.campaign_id else None
    call.answered_by = "machine"
    ok, why = voicemail_allowed(bool(camp and camp.allow_voicemail), camp.voicemail_text if camp else "")
    if not ok:
        return end_voicemail(session, ctx, call, "voicemail_no_message", why)
    try:
        guard_write(settings, "call.speak")  # the kill switch and draft mode stop a voicemail too
    except SafetyError:
        return end_voicemail(session, ctx, call, "voicemail_no_message", "Stopped by the kill switch or draft mode.")
    set_state(session, f"{VOICEMAIL_WAIT}{call.id}", f"beep|{datetime.now(UTC).isoformat()}")
    return "voicemail_waiting_for_beep"


def handle_beep(session: Session, ctx, settings, call: Call) -> str:
    """The machine's greeting ended: say the message now."""
    row = session.get(State, f"{VOICEMAIL_WAIT}{call.id}")
    if row is None or not (row.value or "").startswith("beep|"):
        return "ignored"
    camp = session.get(Campaign, call.campaign_id) if call.campaign_id else None
    try:
        guard_write(settings, "call.speak")
        ctx.adapters.telephony.speak(call.telnyx_call_id, camp.voicemail_text)
    except SafetyError:
        return end_voicemail(session, ctx, call, "voicemail_no_message", "Stopped by the kill switch or draft mode.")
    except (AdapterError, OSError) as exc:
        return end_voicemail(session, ctx, call, "voicemail_no_message", f"The phone company could not start the message ({type(exc).__name__}).")
    row.value = f"speaking|{datetime.now(UTC).isoformat()}"
    return "voicemail_speaking"


def handle_speech_ended(session: Session, ctx, call: Call) -> str:
    """The phone company says the message has been spoken to the end: only now is it recorded as left."""
    row = session.get(State, f"{VOICEMAIL_WAIT}{call.id}")
    if row is None or not (row.value or "").startswith("speaking|"):
        return "ignored"
    return end_voicemail(session, ctx, call, "voicemail_left", "")


def end_voicemail(session: Session, ctx, call: Call, code: str, note: str) -> str:
    """Hang up, record how the machine call ended (once) and hand it to post call processing."""
    _hang_up(ctx, call.telnyx_call_id)
    row = session.get(State, f"{VOICEMAIL_WAIT}{call.id}")
    if row is not None:
        session.delete(row)
    if session.scalar(select(Disposition).where(Disposition.call_id == call.id)) is None:
        session.add(Disposition(call_id=call.id, code=code, note=note, set_by="rules"))
    call.disposition, call.status = code, "in_progress"
    enqueue(session, "postcall")
    return code


def settle_voicemail_waits(session: Session, ctx, now: datetime) -> int:
    """Close a voicemail that never finished: no end-of-greeting event (nothing is said), or a message started whose end was never reported (not recorded as left).
    Run by the dialer job, so a lost event cannot leave a line open or a call recorded as a message that may not have played."""
    n = 0
    for row in list(session.scalars(select(State).where(State.key.startswith(VOICEMAIL_WAIT, autoescape=True)))):
        phase, _, when = (row.value or "").partition("|")
        try:
            age = (aware(now) - aware(datetime.fromisoformat(when))).total_seconds()
        except ValueError:
            age = 10**9
        limit = BEEP_TIMEOUT_S if phase == "beep" else SPEECH_TIMEOUT_S
        call = session.get(Call, int(row.key[len(VOICEMAIL_WAIT):])) if row.key[len(VOICEMAIL_WAIT):].isdigit() else None
        if call is None:
            session.delete(row)
        elif age >= limit:
            end_voicemail(session, ctx, call, "voicemail_no_message", "No end of greeting was heard, so nothing was said." if phase == "beep" else "The message was started but its end was never confirmed, so it is not recorded as left.")
            n += 1
    session.flush()
    return n


def _inbound_refusal(session: Session, settings, frm: str) -> str:
    """Who may be answered right now: at most MAX_INBOUND_CALLS at the same time, MAX_INBOUND_PER_NUMBER_HOUR from one number, and for callers who withhold their number a limit
    of their own (MAX_INBOUND_ANONYMOUS_HOUR in all). They cannot share a single per number bucket: six withheld calls would then lock out every other private caller.
    Each answered call is billed voice time."""
    now = datetime.now(UTC)  # inbound rows are stamped with the real clock
    live = session.scalar(select(func.count()).select_from(Call).where(Call.direction == "inbound", Call.status.in_(IN_FLIGHT), Call.created_at >= now - timedelta(minutes=30))) or 0
    if live >= settings.max_inbound_calls:
        return "busy"
    recent = session.scalar(select(func.count()).select_from(Call).where(Call.direction == "inbound", Call.peer_phone == frm, Call.created_at >= now - timedelta(hours=1))) or 0
    limit = settings.max_inbound_per_number_hour if frm else settings.max_inbound_anonymous_hour
    return "rate_limited" if recent >= limit else ""


def caller_number(raw: str) -> str:
    """The caller's number, or "" when it is withheld, a word like "anonymous", or the carriers' placeholder number."""
    n = normalize_phone(raw)
    return "" if n in ANONYMOUS_NUMBERS else n


def _hang_up(ctx, cid: str) -> None:
    try:
        ctx.adapters.telephony.hangup(cid)
    except (AdapterError, OSError, SafetyError):
        pass


def handle_inbound(session: Session, ctx, settings, payload: dict) -> str:
    to, frm = normalize_phone(payload.get("to", "")), caller_number(payload.get("from", ""))
    num = session.scalars(select(Number).where(Number.e164 == to)).first()
    cid = payload.get("call_control_id", "")
    if num is None or num.agent_id is None or session.scalars(select(Call).where(Call.telnyx_call_id == cid)).first():
        return "ignored"
    guard_write(settings, "call.answer")  # before anything is recorded: a refused call leaves no row behind
    refusal = _inbound_refusal(session, settings, frm)
    if refusal:
        _hang_up(ctx, cid)
        record_event(session, "call.inbound_refused", "call", cid[:40], {"why": refusal})
        return refusal
    agent = session.get(Agent, num.agent_id)
    version = session.get(PromptVersion, agent.active_version_id) if agent.active_version_id else None
    call = Call(agent_id=agent.id, prompt_version_id=version.id if version else None, direction="inbound", peer_phone=frm, status="placing", telnyx_call_id=cid, started_at=ctx.now(session), answered_by="human", disclosure_played=True)
    session.add(call)
    session.flush()
    call_id = call.id
    session.commit()  # saved before the voice engine or the phone company is told, like an outbound call
    try:
        offered = times.safe_slots(ctx.adapters, ctx.now(session))
        shown = None if offered is None else times.offer(offered, settings.office_timezone)  # an inbound caller's own time zone is not known: times are said in the office's
        vc: VoiceCall = ctx.adapters.voice.create_call(system_prompt=live_system_prompt(version.body if version else "", None, shown), voice=agent.voice, first_message=inbound_greeting(agent, settings),
                                                        tools=tool_definitions(tool_base_url(settings), call_id, tool_token(secret_for(settings), call_id)), max_seconds=600)
        call.external_id = vc.call_id
        session.commit()
        ctx.adapters.telephony.answer(cid)
        call.status = "placed"
        _stream(ctx, settings, call, vc.join_url)
        record_event(session, "call.inbound", "call", str(call_id), {})
        session.commit()
    except Exception as exc:  # a failure at the voice engine or the phone company: the call ends as failed, never half saved
        session.rollback()
        row = session.get(Call, call_id)
        if row is not None:
            row.status, row.blocked_reason = "failed", "answer_failed"
            record_event(session, "call.failed", "call", str(call_id), {"why": "answer_failed", "detail": type(exc).__name__})
        session.commit()
        _hang_up(ctx, cid)
        return "failed"
    return "answered"


def _event_time(payload: dict) -> datetime | None:
    raw = payload.get("received_at") or payload.get("sent_at") or payload.get("_occurred_at")
    try:
        return aware(datetime.fromisoformat(str(raw).replace("Z", "+00:00"))) if raw else None
    except ValueError:
        return None


def _seen_message(session: Session, phone: str, mid: str) -> bool:
    """The same text delivered twice (a retry, a replay inside the signature window) changes nothing the second time."""
    if not mid:
        return False
    sources = [f"{kind} {mid}"[:60] for kind in ("inbound STOP", "inbound START", "inbound DNC")]
    return session.scalar(select(ConsentRecord.id).where(ConsentRecord.phone == phone, ConsentRecord.source.in_(sources)).limit(1)) is not None


def handle_sms(session: Session, payload: dict) -> str:
    frm = normalize_phone(payload.get("from", {}).get("phone_number", "")) if isinstance(payload.get("from"), dict) else ""
    text = payload.get("text", "") or ""
    if not frm:
        return "ignored"
    mid = str(payload.get("id") or payload.get("_event_id") or "")[:40]
    if _seen_message(session, frm, mid):
        return "duplicate"
    when = _event_time(payload)  # consent is ordered by when the person sent the text, not by when it reached us
    stamp = {"created_at": when} if when else {}
    if asks_to_stop(text, "text"):
        session.add(ConsentRecord(phone=frm, kind="sms", status="revoked", source=f"inbound DNC {mid}"[:60], **stamp))
        suppression.add_suppression(session, frm, "Asked by text", f"sms:{mid}"[:60], actor="webhook")
        return "sms_do_not_call"
    if revoked_consent(text, "text"):
        session.add(ConsentRecord(phone=frm, kind="sms", status="revoked", source=f"inbound STOP {mid}"[:60], **stamp))
        record_audit(session, "webhook", "sms.opt_out", f"phone:{frm[-4:]}", {})
        return "sms_opt_out"
    if START_WORDS.match(text):
        # START only gives texting back to a number that had stopped it, and never to a number on the do not call list
        if suppression.latest_consent(session, frm, "sms") == "revoked" and not suppression.is_suppressed(session, frm):
            session.add(ConsentRecord(phone=frm, kind="sms", status="granted", source=f"inbound START {mid}"[:60], **stamp))
            return "sms_opt_in"
    return "ignored"


def handle_ultravox_event(session: Session, event: str, call_obj: dict) -> str:
    cid = call_obj.get("callId") or call_obj.get("id")
    call = session.scalars(select(Call).where(Call.external_id == cid)).first() if cid else None
    if call is None:
        if cid and event == "call.ended" and session.scalar(select(Call.id).where(Call.status == "placing").limit(1)) is not None:  # only while a call is being set up, so a stranger's events cannot fill the table
            set_state(session, f"early_end:{str(cid)[:60]}", "1")  # the end arrived before this app saved the id: place() reads this marker
            return "early_end_kept"
        return "unknown_call"
    if event == "call.ended" and call.status in ("placing", "placed", "in_progress"):
        call.status = "in_progress"
        enqueue(session, "postcall")
        return "queued_postcall"
    return "ignored"
