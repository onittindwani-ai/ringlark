"""Handling the live events that come from Telnyx and Ultravox. Every handler can run twice on the same event and give the same result."""

from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from ringlark import suppression
from ringlark.adapters.base import VoiceCall
from ringlark.adapters.telnyx import decode_state, encode_state
from ringlark.adapters.ultravox import tool_definitions
from ringlark.compliance import voicemail_allowed
from ringlark.disclosure import build_greeting
from ringlark.models import Agent, Call, Campaign, ConsentRecord, Disposition, Number, PromptVersion
from ringlark.toolauth import tool_token
from ringlark.util import normalize_phone
from sendora_core.audit import record_audit
from sendora_core.events import record_event
from sendora_core.jobs import enqueue
from sendora_core.safety import SafetyError, guard_write

STOP_WORDS = re.compile(r"^\s*(stop|stopall|unsubscribe|cancel|end|quit)\s*[.!]?\s*$", re.I)
START_WORDS = re.compile(r"^\s*(start|unstop|yes)\s*[.!]?\s*$", re.I)


def inbound_greeting(agent: Agent) -> str:
    return agent.greeting or f"Thanks for calling {agent.company or 'us'}. This is {agent.name}, an AI assistant. This call may be recorded and transcribed. How can I help?"


def _find(session: Session, payload: dict) -> Call | None:
    state = decode_state(payload.get("client_state"))
    if state.get("call"):
        return session.get(Call, int(state["call"]))
    cid = payload.get("call_control_id")
    return session.scalars(select(Call).where(Call.telnyx_call_id == cid)).first() if cid else None


def _stream(ctx, call: Call, join_url: str) -> None:
    if join_url:
        ctx.adapters.telephony.start_stream(call.telnyx_call_id, join_url)


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
        _stream(ctx, call, decode_state(payload.get("client_state")).get("join", ""))
        return "streaming"
    if event_type == "call.hangup":
        if call.status in ("placed", "in_progress"):
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


def handle_inbound(session: Session, ctx, settings, payload: dict) -> str:
    to, frm = normalize_phone(payload.get("to", "")), normalize_phone(payload.get("from", ""))
    num = session.scalars(select(Number).where(Number.e164 == to)).first()
    cid = payload.get("call_control_id", "")
    if num is None or num.agent_id is None or session.scalars(select(Call).where(Call.telnyx_call_id == cid)).first():
        return "ignored"
    agent = session.get(Agent, num.agent_id)
    version = session.get(PromptVersion, agent.active_version_id) if agent.active_version_id else None
    call = Call(agent_id=agent.id, prompt_version_id=version.id if version else None, direction="inbound", peer_phone=frm, status="placed", telnyx_call_id=cid, started_at=ctx.now(session), answered_by="human", disclosure_played=True)
    session.add(call)
    session.flush()
    from sendora_core.safety import guard_write

    guard_write(settings, "call.answer")
    vc: VoiceCall = ctx.adapters.voice.create_call(system_prompt=version.body if version else "", voice=agent.voice, first_message=inbound_greeting(agent),
                                                    tools=tool_definitions(settings.public_base_url or "https://example.test", call.id, tool_token(settings.session_secret, call.id)), max_seconds=600)
    call.external_id = vc.call_id
    ctx.adapters.telephony.answer(cid)
    _stream(ctx, call, vc.join_url)
    record_event(session, "call.inbound", "call", str(call.id), {})
    return "answered"


def handle_sms(session: Session, payload: dict) -> str:
    frm = normalize_phone(payload.get("from", {}).get("phone_number", "")) if isinstance(payload.get("from"), dict) else ""
    text = payload.get("text", "")
    if not frm:
        return "ignored"
    if STOP_WORDS.match(text):
        session.add(ConsentRecord(phone=frm, kind="sms", status="revoked", source="inbound STOP"))
        record_audit(session, "webhook", "sms.opt_out", f"phone:{frm[-4:]}", {})
        return "sms_opt_out"
    if START_WORDS.match(text):
        session.add(ConsentRecord(phone=frm, kind="sms", status="granted", source="inbound START"))
        return "sms_opt_in"
    return "ignored"


def handle_ultravox_event(session: Session, event: str, call_obj: dict) -> str:
    cid = call_obj.get("callId") or call_obj.get("id")
    call = session.scalars(select(Call).where(Call.external_id == cid)).first() if cid else None
    if call is None:
        return "unknown_call"
    if event == "call.ended" and call.status in ("placed", "in_progress"):
        call.status = "in_progress"
        enqueue(session, "postcall")
        return "queued_postcall"
    return "ignored"
