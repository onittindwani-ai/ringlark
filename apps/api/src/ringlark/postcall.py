"""After a call ends: transcript, disposition, summary, QA score, follow ups, CRM note. Safe to run twice on the same call (it skips a processed call)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ringlark import intents as I
from ringlark import messages, model_tasks, qa, sms_rules, suppression
from ringlark.caller_reader import asks_to_stop, revoked_consent
from ringlark.adapters.base import PersonRecord
from ringlark.context import set_state
from ringlark.models import Agent, Call, Disposition, FollowUp, QAScore, State, Target, Turn
from ringlark.tools import happened
from ringlark.util import aware, is_valid_email
from ringlark.waveform import timing
from sendora_core.adapters import AdapterError
from sendora_core.approvals import request_approval
from sendora_core.audit import record_audit
from sendora_core.events import record_event
from sendora_core.safety import SafetyError, guard_write


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
    """Queue the texts and emails to approve after a call. The same rules that decide at send time are asked here, so a person who said
    "do not text me" on this very call, or who is on the do not call list, never gets a follow up queued."""
    if target is None or code not in ("booked", "interested_callback"):
        return 0
    settings, agent = ctx.settings, session.get(Agent, call.agent_id)
    n = 0
    if sms_rules.consent_decision(session, call.peer_phone, target):
        kind = "confirmation" if code == "booked" else "callback"
        body = messages.sms_text(settings, agent, kind)
        if body and not _already_waiting(session, "sms", call.peer_phone, body):
            session.add(FollowUp(call_id=call.id, channel="sms", to=call.peer_phone, body=body, status="pending")); n += 1
    if target.email and code == "booked" and is_valid_email(target.email) and not suppression.is_suppressed(session, call.peer_phone):
        subject, email_body = messages.booked_email(settings, agent)
        if not _already_waiting(session, "email", target.email, email_body):
            session.add(FollowUp(call_id=call.id, channel="email", to=target.email, subject=subject, body=email_body, status="pending")); n += 1
    session.flush()
    if ctx.settings.follow_ups_need_approval:
        for fu in session.scalars(select(FollowUp).where(FollowUp.call_id == call.id, FollowUp.status == "pending", FollowUp.approval_id.is_(None))):
            a = request_approval(session, "followup.send", f"Send {'a text message' if fu.channel == 'sms' else 'an email'} follow up", {"followup_id": fu.id}, "low", "postcall")
            fu.approval_id = a.id
    return n


EMPTY_TRANSCRIPT_WAIT = timedelta(minutes=3)  # how long an answered call may show no transcript before a person is asked to look at it


def _empty_transcript_wait(session: Session, ctx, call: Call) -> bool:
    """A live call a person answered must have words in it. A transcript that is empty right after the call ended may just not be ready, so the call is
    left unprocessed and read again on the next runs. Returns True while that wait lasts and False once it is over (then the call goes to a person)."""
    now = ctx.now(session)
    key = f"postcall_empty:{call.id}"
    row = session.get(State, key)
    if row is None:
        set_state(session, key, now.isoformat())
        session.flush()
        return True
    try:
        first = aware(datetime.fromisoformat(row.value))
    except ValueError:
        return False
    return aware(now) - first < EMPTY_TRANSCRIPT_WAIT


def process_call(session: Session, ctx, call: Call) -> dict:
    if call.processed:
        return {"skipped": True}
    try:
        fill_turns_from_voice(session, ctx, call)
    except Exception:  # the voice engine may be down: leave the call unprocessed and retry on the next run
        return {"skipped": True, "reason": "transcript_unavailable"}
    no_words = False
    if not call.turns and call.answered_by == "human" and call.external_id and not ctx.settings.demo_mode and session.scalar(select(Disposition.id).where(Disposition.call_id == call.id)) is None:
        if _empty_transcript_wait(session, ctx, call):
            return {"skipped": True, "reason": "transcript_empty"}
        no_words = True  # the wait is over and still nothing: it is not "no answer", a person looks at it
    turns = [{"speaker": t.speaker, "text": t.text, "start_ms": t.start_ms, "end_ms": t.end_ms} for t in call.turns]
    target = session.get(Target, call.target_id) if call.target_id else None
    row = session.scalar(select(Disposition).where(Disposition.call_id == call.id))
    code = row.code if row else ("needs_review" if no_words else rule_disposition(turns))
    if row is None:
        session.add(Disposition(call_id=call.id, code=code, note="No transcript came back from the voice engine, so nothing could be checked for a request to stop. Read the call before calling again." if no_words else "Set by rules from the transcript", set_by="rules"))
    elif code == "booked" and row.set_by == "agent" and not happened(session, call.id, "meeting.booked"):
        code, row.code = "needs_review", "needs_review"  # an older row or another path said booked with no booking behind it
        row.note = ("Said booked but no booking was made on this call. " + row.note).strip()[:300]
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
    if no_words:
        s["flagged"], s["flag_note"] = True, "No transcript came back, so a request to stop could not be checked. A person should read this call."
    if session.scalar(select(QAScore).where(QAScore.call_id == call.id)) is None:
        # A call that ended as needs_review is always queued for a person (the dialer holds the person until it is read).
        session.add(QAScore(call_id=call.id, score=s["score"], checks=s["checks"], flagged=s["flagged"], flag_note=s["flag_note"], sampled=s["flagged"] or code == "needs_review" or qa.sampled(call.id)))
    n = _followups(session, ctx, call, target, code)
    if target and code in ("booked",) :
        target.status = "booked"
    elif target and code in ("not_interested", "hostile_ended", "interested_callback", "transferred") and target.status != "suppressed":
        target.status = "done" if code != "interested_callback" else "contacted"
    if target and code == "booked":
        try:
            guard_write(ctx.effective(session), "crm.upsert")  # the kill switch and "draft only" set in the app stop this write too, whatever MODE says
            ctx.adapters.crm.upsert_person(PersonRecord(first_name=target.first_name, last_name=target.last_name, phone=call.peer_phone, extra={"note": call.summary}))
        except (SafetyError, AdapterError):
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
