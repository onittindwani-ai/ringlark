"""After a call ends: transcript, disposition, summary, QA score, follow ups, CRM note. Safe to run twice on the same call (it skips a processed call)."""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from ringlark import intents as I
from ringlark import model_tasks, qa, suppression
from ringlark.caller_reader import asks_to_stop, revoked_consent
from ringlark.adapters.base import PersonRecord
from ringlark.models import Agent, Call, Disposition, FollowUp, QAScore, Target, Turn
from ringlark.waveform import timing
from sendora_core.approvals import request_approval
from sendora_core.audit import record_audit
from sendora_core.events import record_event
from sendora_core.safety import SafetyError


def fill_turns_from_voice(session: Session, ctx, call: Call) -> int:
    """Live path: read the transcript back from the voice engine (UNVERIFIED against the real service)."""
    if call.turns or not call.external_id:
        return len(call.turns)
    for i, t in enumerate(ctx.adapters.voice.transcript(call.external_id)):
        session.add(Turn(call_id=call.id, position=i, speaker=t["speaker"], text=t["text"], start_ms=t["start_ms"], end_ms=t["end_ms"]))
    session.flush()
    session.refresh(call)
    return len(call.turns)


def rule_disposition(turns: list[dict]) -> str:
    caller = [t["text"] for t in turns if t["speaker"] == "caller" and t["text"]]
    joined = " ".join(caller)
    if not caller:
        return "no_answer"
    if any(asks_to_stop(t) for t in caller):
        return "do_not_call"
    if I.any_match(I.WRONG, joined):
        return "wrong_number"
    return "needs_review"


def _already_waiting(session: Session, channel: str, to: str, body: str) -> bool:
    """The same message to the same person is already waiting to be approved or sent: a second copy would only make them get it twice."""
    return session.scalar(select(FollowUp.id).where(FollowUp.status == "pending", FollowUp.channel == channel, FollowUp.to == to, FollowUp.body == body).limit(1)) is not None


def _followups(session: Session, ctx, call: Call, target: Target | None, code: str) -> int:
    if target is None or code not in ("booked", "interested_callback"):
        return 0
    n = 0
    if target.sms_consent and not suppression.is_suppressed(session, call.peer_phone):
        body = "Harbor Light Dental: your check up is booked. We will see you then. Reply STOP to opt out." if code == "booked" else "Harbor Light Dental: sorry we caught you at a busy time. We will call you back at a better time. Reply STOP to opt out."
        if not _already_waiting(session, "sms", call.peer_phone, body):
            session.add(FollowUp(call_id=call.id, channel="sms", to=call.peer_phone, body=body, status="pending")); n += 1
    if target.email and code == "booked":
        email_body = "Hello,\n\nYour check up is booked. Reply to this email if you need to change it.\n\nHarbor Light Dental (a fictional practice)"
        if not _already_waiting(session, "email", target.email, email_body):
            session.add(FollowUp(call_id=call.id, channel="email", to=target.email, subject="Your check up at Harbor Light Dental", body=email_body, status="pending")); n += 1
    session.flush()
    if ctx.settings.follow_ups_need_approval:
        for fu in session.scalars(select(FollowUp).where(FollowUp.call_id == call.id, FollowUp.status == "pending", FollowUp.approval_id.is_(None))):
            a = request_approval(session, "followup.send", f"Send {'a text message' if fu.channel == 'sms' else 'an email'} follow up", {"followup_id": fu.id}, "low", "postcall")
            fu.approval_id = a.id
    return n


def process_call(session: Session, ctx, call: Call) -> dict:
    if call.processed:
        return {"skipped": True}
    try:
        fill_turns_from_voice(session, ctx, call)
    except Exception:  # the voice engine may be down: leave the call unprocessed and retry on the next run
        return {"skipped": True, "reason": "transcript_unavailable"}
    turns = [{"speaker": t.speaker, "text": t.text, "start_ms": t.start_ms, "end_ms": t.end_ms} for t in call.turns]
    target = session.get(Target, call.target_id) if call.target_id else None
    row = session.scalar(select(Disposition).where(Disposition.call_id == call.id))
    code = row.code if row else rule_disposition(turns)
    if row is None:
        session.add(Disposition(call_id=call.id, code=code, note="Set by rules from the transcript", set_by="rules"))
    caller_text = " ".join(t["text"] for t in turns if t["speaker"] == "caller")
    caller_lines = [t["text"] for t in turns if t["speaker"] == "caller" and t["text"]]
    asked_stop = any(asks_to_stop(t) for t in caller_lines)
    missed_stop = asked_stop and code != "do_not_call"
    if any(revoked_consent(t) for t in caller_lines):  # "stop texting me" said on the call is recorded here, so a later text is blocked
        from ringlark.tools import revoke_sms

        revoke_sms(session, call.peer_phone, f"asked on call {call.id}")
    if asked_stop and not suppression.is_suppressed(session, call.peer_phone):
        suppression.add_suppression(session, call.peer_phone, "Asked on the call (found by post call rules)", f"call:{call.id}", actor="postcall")
        if target:
            target.status = "suppressed"
    call.disposition = code
    if turns:
        call.duration_ms = max(call.duration_ms, turns[-1]["end_ms"])
    facts = {"direction": call.direction, "turns": len(turns), "disposition": code, "tools": sorted({e.payload.get("tool") for e in _tool_events(session, call) if e.payload.get("tool")})}
    first_words = next((t["text"] for t in turns if t["speaker"] == "caller" and t["text"]), "")
    fallback = f"{call.direction.capitalize()} call, {len(turns)} turns, outcome {code.replace('_', ' ')}."
    call.summary = model_tasks.summarise_call(ctx.llm(session), facts, first_words, fallback)
    s = qa.score_call(turns, code, row.code if row is not None and row.set_by == "agent" else "")
    if missed_stop:
        s["flagged"], s["flag_note"] = True, (s["flag_note"] + " The person asked to stop and the agent did not record it; the rules did.").strip()
    if session.scalar(select(QAScore).where(QAScore.call_id == call.id)) is None:
        session.add(QAScore(call_id=call.id, score=s["score"], checks=s["checks"], flagged=s["flagged"], flag_note=s["flag_note"], sampled=s["flagged"] or qa.sampled(call.id)))
    n = _followups(session, ctx, call, target, code)
    if target and code in ("booked",) :
        target.status = "booked"
    elif target and code in ("not_interested", "hostile_ended", "interested_callback", "transferred") and target.status != "suppressed":
        target.status = "done" if code != "interested_callback" else "contacted"
    if target and code == "booked":
        try:
            ctx.adapters.crm.upsert_person(PersonRecord(first_name=target.first_name, last_name=target.last_name, phone=call.peer_phone, extra={"note": call.summary}))
        except SafetyError:
            pass
    call.status, call.processed = "completed", True
    record_audit(session, "postcall", "call.processed", f"call:{call.id}", {"disposition": code, "qa": s["score"], "followups": n})
    record_event(session, "call.processed", "call", str(call.id), {"disposition": code, "qa": s["score"]})
    session.flush()
    return {"disposition": code, "qa": s["score"], "followups": n}


def _tool_events(session: Session, call: Call):
    from sendora_core.models import Event

    return list(session.scalars(select(Event).where(Event.kind == "tool.used", Event.entity_id == str(call.id))))


def store_turns(session: Session, call: Call, pairs: list[tuple[str, str]]) -> None:
    for t in timing(pairs):
        session.add(Turn(call_id=call.id, position=t["position"], speaker=t["speaker"], text=t["text"], start_ms=t["start_ms"], end_ms=t["end_ms"]))
    session.flush()
    session.refresh(call)
