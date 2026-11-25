"""Handling the live events that come from Telnyx and Ultravox. Every handler can run twice on the same event and give the same result."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ringlark import suppression
from ringlark.adapters.base import VoiceCall
from ringlark.adapters.telnyx import decode_state
from ringlark.adapters.ultravox import tool_definitions
from ringlark.caller_reader import asks_to_stop, revoked_consent
from ringlark.compliance import voicemail_allowed
from ringlark.context import set_state
from ringlark.disclosure import build_greeting
from ringlark.live_prompt import live_system_prompt
from ringlark.models import Agent, Call, Campaign, ConsentRecord, Disposition, Number, PromptVersion
from ringlark.toolauth import secret_for, tool_base_url, tool_token
from ringlark.util import aware, normalize_phone
from sendora_core.adapters import AdapterError
from sendora_core.audit import record_audit
from sendora_core.events import record_event
from sendora_core.jobs import enqueue
from sendora_core.safety import SafetyError, guard_write

START_WORDS = re.compile(r"^\s*(start|unstop)\s*[.!]?\s*$", re.I)  # only the carrier word. A plain "yes" never gives consent
IN_FLIGHT = ("placing", "placed", "in_progress")


class CallNotFoundYet(LookupError):
    """An event names a call this app should have recorded already. The webhook answers 503, so the sender tries again instead of the event being lost."""


def inbound_greeting(agent: Agent, settings=None) -> str:
    company = (agent.company or (settings.company_name if settings is not None else "") or "us").strip()
    return agent.greeting or f"Thanks for calling {company}. This is {agent.name}, an AI assistant. This call may be recorded and transcribed. How can I help?"


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
    if event_type == "call.hangup":
        if call.status in ("placing", "placed", "in_progress"):
            call.status = "in_progress"
            enqueue(session, "postcall")
        return "hangup_seen"
    return "ignored"


def handle_machine(session: Session, ctx, settings, call: Call) -> str:
    camp = session.get(Campaign, call.campaign_id) if call.campaign_id else None
    call.answered_by = "machine"
    ok, why = voicemail_allowed(bool(camp and camp.allow_voicemail), camp.voicemail_text if camp else "")
    code = "voicemail_no_message"
    if ok:
        try:
            guard_write(settings, "call.speak")  # the kill switch and draft mode stop a voicemail too
            ctx.adapters.telephony.speak(call.telnyx_call_id, camp.voicemail_text)
            code = "voicemail_left"
        except SafetyError:
            code = "voicemail_no_message"
    try:
        ctx.adapters.telephony.hangup(call.telnyx_call_id)
    except SafetyError:
        pass
    if session.scalar(select(Disposition).where(Disposition.call_id == call.id)) is None:
        session.add(Disposition(call_id=call.id, code=code, note=why, set_by="rules"))
    call.disposition, call.status = code, "in_progress"
    enqueue(session, "postcall")
    return code


def _inbound_refusal(session: Session, settings, frm: str) -> str:
    """Who may be answered right now: at most MAX_INBOUND_CALLS at the same time and MAX_INBOUND_PER_NUMBER_HOUR from one number. Each answered call is billed voice time."""
    now = datetime.now(UTC)  # inbound rows are stamped with the real clock
    live = session.scalar(select(func.count()).select_from(Call).where(Call.direction == "inbound", Call.status.in_(IN_FLIGHT), Call.created_at >= now - timedelta(minutes=30))) or 0
    if live >= settings.max_inbound_calls:
        return "busy"
    recent = session.scalar(select(func.count()).select_from(Call).where(Call.direction == "inbound", Call.peer_phone == frm, Call.created_at >= now - timedelta(hours=1))) or 0
    return "rate_limited" if recent >= settings.max_inbound_per_number_hour else ""


def _hang_up(ctx, cid: str) -> None:
    try:
        ctx.adapters.telephony.hangup(cid)
    except (AdapterError, OSError, SafetyError):
        pass


def handle_inbound(session: Session, ctx, settings, payload: dict) -> str:
    to, frm = normalize_phone(payload.get("to", "")), normalize_phone(payload.get("from", ""))
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
        vc: VoiceCall = ctx.adapters.voice.create_call(system_prompt=live_system_prompt(version.body if version else ""), voice=agent.voice, first_message=inbound_greeting(agent, settings),
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
