"""The outbound dialer. Every call goes through compliance.evaluate first. Draft mode places nothing and the kill switch halts everything."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ringlark import compliance
from ringlark.adapters.telnyx import encode_state
from ringlark.adapters.ultravox import tool_definitions
from ringlark.compliance import DialRequest, Rules
from ringlark.disclosure import build_greeting, has_disclosure, has_recording_notice
from ringlark.live_prompt import live_system_prompt
from ringlark.messages import appointment
from ringlark.models import Agent, Call, Campaign, Number, PromptVersion, QAScore, State, Target
from ringlark.prompts import choose_version
from ringlark.suppression import is_suppressed, latest_consent
from ringlark.toolauth import secret_for, tool_base_url, tool_token
from ringlark.util import aware, normalize_phone, zone
from sendora_core.adapters import AdapterError
from sendora_core.events import record_event
from sendora_core.jobs import enqueue
from sendora_core.safety import SafetyError, guard_write, would_write

log = logging.getLogger("ringlark.dialer")
IN_FLIGHT = ("placing", "placed", "in_progress")
REAL = ("placing", "placed", "in_progress", "completed", "failed")
PERMANENT = {"do_not_call", "consent_revoked", "bad_number", "unknown_timezone", "max_attempts", "premium_rate_number"}
STALE_AFTER = timedelta(minutes=30)  # a call that has shown no sign of life this long after it was started is closed (a call lasts at most 10 minutes)


@dataclass
class DialResult:
    placed: int = 0
    drafted: int = 0
    blocked: int = 0
    halted: bool = False
    reasons: dict[str, int] = field(default_factory=dict)
    call_ids: list[int] = field(default_factory=list)

    def add(self, reason: str) -> None:
        self.reasons[reason] = self.reasons.get(reason, 0) + 1


def rules_for(c: Campaign, settings=None) -> Rules:
    """The campaign's rules. With settings, the calling window is held inside the legal bounds (08:00 to 21:00 callee local time unless ALLOW_EXTENDED_HOURS)."""
    lo, hi = settings.window_bounds if settings is not None else (0, 24)
    start, end = max(lo, c.window_start_hour), min(hi, c.window_end_hour)
    return Rules(start, end, c.weekdays_only, c.daily_cap, c.max_attempts, c.retry_gap_days, c.require_prior_consent)


def greeting_for(agent: Agent, settings=None) -> str:
    company = (agent.company or (settings.company_name if settings is not None else "") or "our team").strip()
    purpose = f"I'm calling about your next {appointment(settings)}." if settings is not None else "I'm calling about your next check up."
    return agent.greeting or build_greeting(agent.name, company, purpose, True)


def calls_today(session: Session, campaign_id: int, now: datetime) -> int:
    start = aware(now).replace(hour=0, minute=0, second=0, microsecond=0)
    return int(session.scalar(select(func.count()).select_from(Call).where(Call.campaign_id == campaign_id, Call.status.in_(REAL), Call.created_at >= start)) or 0)


def _calls_to(target: Target, outbound_only: bool = True):
    """Every call to this person, in any campaign: the same number in two campaigns is one person. A call this person made to us counts as in flight, not as an attempt."""
    phone = normalize_phone(target.phone) or target.phone
    mine = or_(Call.target_id == target.id, (Call.peer_phone == phone) & (Call.direction == "outbound")) if outbound_only else or_(Call.target_id == target.id, Call.peer_phone == phone)
    return mine


def history(session: Session, target: Target, tz: str):
    rows = list(session.scalars(select(Call).where(_calls_to(target), Call.status.in_(REAL)).order_by(Call.created_at)))
    z = zone(tz)
    dates = tuple(aware(r.created_at).astimezone(z).date().isoformat() for r in rows) if z else ()
    return len(rows), dates, (aware(rows[-1].created_at) if rows else None)


def awaiting_review(session: Session, target: Target) -> bool:
    """True when a call to this person ended as needs_review and no person has marked it as read. The only code that reads a call for a stop
    request is a pattern reader that misses some wording, so an unclear call is looked at by a human before the person is dialled again."""
    stmt = (select(func.count()).select_from(Call).join(QAScore, QAScore.call_id == Call.id)
            .where(_calls_to(target), Call.status == "completed", Call.disposition == "needs_review", QAScore.reviewed.is_(False)))
    return (session.scalar(stmt) or 0) > 0


def decide(session: Session, settings, c: Campaign, agent: Agent, t: Target, now: datetime, today: int) -> compliance.Decision:
    n, dates, last = history(session, t, t.timezone)
    phone = normalize_phone(t.phone) or t.phone
    consent = latest_consent(session, phone, "call")
    in_flight = session.scalar(select(func.count()).select_from(Call).where(_calls_to(t, False), Call.status.in_(IN_FLIGHT))) > 0
    greeting = greeting_for(agent, settings)
    return compliance.evaluate(DialRequest(
        phone=phone, timezone=t.timezone, now_utc=now, rules=rules_for(c, settings), kill_switch=settings.kill_switch, draft_mode=not would_write(settings) and not settings.kill_switch,
        greeting_has_disclosure=has_disclosure(greeting), greeting_has_recording_notice=has_recording_notice(greeting) or not settings.recording_notice_required, on_dnc_list=is_suppressed(session, phone), call_consent=consent, calls_today=today, attempts_before=n,
        last_attempt_local_dates=dates, last_attempt_utc=last, in_flight=in_flight, awaiting_review=awaiting_review(session, t), allowed_codes=settings.calling_codes))


def place(session: Session, settings, adapters, c: Campaign, agent: Agent, t: Target, number: Number | None, now: datetime, attempt: int) -> Call:
    """Record the call, then ring. The caller has already passed compliance.

    The row is saved (status placing) BEFORE the voice engine or the phone company hears of it, so every webhook that comes back finds it,
    a crash cannot leave a ringing phone with no record (the next tick would dial the same person again), and a failure ends as a failed call, never an orphan."""
    guard_write(settings, "call.place")  # nothing is recorded when the kill switch or draft mode forbids the call
    vid = choose_version(agent, f"{c.id}:{t.id}:{attempt}")
    version = session.get(PromptVersion, vid) if vid else None
    call = Call(campaign_id=c.id, target_id=t.id, agent_id=agent.id, prompt_version_id=vid, direction="outbound", peer_phone=normalize_phone(t.phone), status="placing", attempt=attempt, started_at=now,
                disclosure_played=True, created_at=now)
    session.add(call)
    session.flush()
    call_id = call.id
    session.commit()
    try:
        vc = adapters.voice.create_call(system_prompt=live_system_prompt(version.body if version else "", t.first_name), voice=agent.voice, first_message=greeting_for(agent, settings),
                                        tools=tool_definitions(tool_base_url(settings), call_id, tool_token(secret_for(settings), call_id)), max_seconds=600)
        call.external_id = vc.call_id
        session.commit()  # an event from the voice engine can now find this call by its id
        if _early_end_seen(session, vc.call_id):
            call.status = "in_progress"
            enqueue(session, "postcall")
            session.commit()
            return call
        placed = adapters.telephony.place_call(to=call.peer_phone, from_number=number.e164 if number else settings.telnyx_from_number, client_state=encode_state({"call": call_id, "join": vc.join_url}), amd=True)
        call.telnyx_call_id, call.status = placed.call_control_id, "placed"
        t.status = "contacted"
        record_event(session, "call.placed", "call", str(call_id), {"campaign": c.id, "attempt": attempt})
        session.commit()
    except Exception as exc:  # any failure at a vendor (a refused call, a network error, a bad answer) ends this call as failed and lets the tick go on
        session.rollback()
        _mark_failed(session, call_id, "place_failed", type(exc).__name__)
        log.warning("call %s could not be placed: %s", call_id, type(exc).__name__, exc_info=not isinstance(exc, (AdapterError, SafetyError, OSError)))
        return session.get(Call, call_id)
    return call


def _mark_failed(session: Session, call_id: int, reason: str, detail: str = "") -> None:
    row = session.get(Call, call_id)
    if row is not None and row.status in ("placing", "placed"):
        row.status, row.blocked_reason = "failed", reason
        record_event(session, "call.failed", "call", str(call_id), {"why": reason, "detail": detail})
    session.commit()


def _early_end_seen(session: Session, external_id: str) -> bool:
    """The voice engine said the call ended before this app had saved its id (see live.handle_ultravox_event). The marker is used once."""
    row = session.get(State, f"early_end:{external_id[:60]}")
    if row is None:
        return False
    session.delete(row)
    session.flush()
    return True


def reap_stale_calls(session: Session, now: datetime) -> int:
    """Settle calls that showed no sign of life for 30 minutes (a lost webhook, a crash). A call the voice engine knows about (it has an
    external id) is NOT written off: it moves to in progress and the transcript is read back, because a "stop calling me" said on it must still be
    recorded before anyone is dialled again. A call that never reached the voice engine is closed as failed. Attempts still count either way."""
    cutoff = aware(now) - STALE_AFTER
    n = 0
    for call in session.scalars(select(Call).where(Call.status.in_(("placing", "placed")), Call.direction.in_(("outbound", "inbound")))):
        if aware(call.created_at) >= cutoff or call.processed or call.turns:
            continue
        if call.status == "placed" and call.external_id:
            call.status = "in_progress"
            record_event(session, "call.recovered", "call", str(call.id), {"why": "no_call_events"})
            enqueue(session, "postcall")
        else:
            call.status, call.blocked_reason = "failed", "no_call_events"
            record_event(session, "call.failed", "call", str(call.id), {"why": "no_call_events"})
        n += 1
    session.flush()
    return n


def halt_live_calls(session: Session, adapters) -> int:
    """The kill switch is on: hang up every call that is ringing or in progress, once. A call placed before the switch must not carry on."""
    n = 0
    for call in session.scalars(select(Call).where(Call.status.in_(("placed", "in_progress")), Call.telnyx_call_id != "", Call.blocked_reason != "kill_switch_hangup")):
        try:
            adapters.telephony.hangup(call.telnyx_call_id)
        except (AdapterError, OSError) as exc:
            log.warning("could not hang up call %s: %s", call.id, type(exc).__name__)
            continue
        call.blocked_reason = "kill_switch_hangup"
        record_event(session, "call.hung_up", "call", str(call.id), {"why": "kill_switch"})
        n += 1
    session.flush()
    return n


def dial_tick(session: Session, settings, adapters, now: datetime, limit: int = 40) -> DialResult:
    res = DialResult()
    if settings.kill_switch:
        res.halted = True
        res.add("kill_switch")
        if not settings.demo_mode:
            halt_live_calls(session, adapters)
        return res
    if not settings.demo_mode:
        reap_stale_calls(session, now)
    for c in list(session.scalars(select(Campaign).where(Campaign.status == "running").order_by(Campaign.id))):
        agent = session.get(Agent, c.agent_id)
        number = session.get(Number, c.number_id) if c.number_id else None
        today = calls_today(session, c.id, now)
        for t in list(session.scalars(select(Target).where(Target.campaign_id == c.id, Target.status.in_(("new", "queued", "contacted"))).order_by(Target.id))):
            if res.placed + res.drafted >= limit:
                break
            d = decide(session, settings, c, agent, t, now, today)
            if d.reason == "draft_mode":
                if session.scalar(select(func.count()).select_from(Call).where(Call.target_id == t.id, Call.status == "drafted")) == 0:
                    row = Call(campaign_id=c.id, target_id=t.id, agent_id=agent.id, direction="outbound", peer_phone=normalize_phone(t.phone), status="drafted", blocked_reason="draft_mode", created_at=now)
                    session.add(row); session.flush(); res.drafted += 1; res.call_ids.append(row.id)
                res.add("draft_mode")
                continue
            if not d.allowed:
                res.add(d.reason)
                res.blocked += 1
                if d.reason in PERMANENT and t.status != "suppressed":
                    t.status = "suppressed"
                    session.add(Call(campaign_id=c.id, target_id=t.id, agent_id=agent.id, direction="outbound", peer_phone=t.phone, status="blocked", blocked_reason=d.reason, created_at=now))
                continue
            attempt = history(session, t, t.timezone)[0] + 1
            try:
                call = place(session, settings, adapters, c, agent, t, number, now, attempt)
            except SafetyError:  # the kill switch or draft mode came on while the tick ran: stop, nothing was recorded
                res.halted = True
                res.add("stopped_by_safety")
                return res
            today += 1
            res.call_ids.append(call.id)
            if call.status == "failed":
                res.blocked += 1
                res.add("place_failed")
                continue
            res.placed += 1
    return res
