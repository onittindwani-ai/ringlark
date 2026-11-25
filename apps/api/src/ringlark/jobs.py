"""The five background jobs and the little scheduler that keeps them running."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ringlark import crmsync, demo, dialer, followups, metrics, model_tasks, retention
from ringlark.context import Ctx, set_state
from ringlark.models import Call
from ringlark.postcall import process_call
from sendora_core.events import record_event
from sendora_core.jobs import Handler, enqueue

INTERVALS = {"dial_tick": 60, "postcall": 30, "followups": 60, "crm_sync": 600, "report": 7 * 24 * 3600, "retention": 24 * 3600}


def job_dial_tick(session: Session, ctx: Ctx) -> dict:
    r = dialer.dial_tick(session, ctx.effective(session), ctx.adapters, ctx.now(session))
    set_state(session, "last_dial_at", datetime.now(UTC).isoformat())
    set_state(session, "last_dial", json.dumps({"placed": r.placed, "drafted": r.drafted, "reasons": r.reasons}))
    return {"placed": r.placed, "drafted": r.drafted, "blocked": r.blocked, "halted": r.halted, "reasons": r.reasons}


def job_postcall(session: Session, ctx: Ctx) -> dict:
    n = 0
    # The calls are read first and the work is saved after each one: a stop request found in one call is on disk before the next call is looked at, and a failure
    # on a later call cannot undo it. The CRM notes come last, in a short pass with a time limit (crmsync.py).
    calls = list(session.scalars(select(Call).where(Call.processed.is_(False), Call.status.in_(("in_progress", "placed")), Call.direction.in_(("outbound", "inbound")))))
    for call in calls:
        if call.turns or call.external_id:
            if not ctx.settings.demo_mode and call.status == "placed":
                continue  # a live call is processed when the voice engine says it ended
            r = process_call(session, ctx, call, defer_crm=True)
            session.commit()
            n += 0 if r.get("skipped") else 1
    return {"processed": n, "crm": crmsync.flush(session, ctx)}


def job_followups(session: Session, ctx: Ctx) -> dict:
    return followups.send_due(session, ctx.effective(session), ctx.adapters, ctx.now(session))


def job_crm_sync(session: Session, ctx: Ctx) -> dict:
    return crmsync.flush(session, ctx)  # the notes that could not be written at the end of a post call run, tried again


def job_retention(session: Session, ctx: Ctx) -> dict:
    return retention.run(session, ctx)


def job_report(session: Session, ctx: Ctx) -> dict:
    ov = metrics.overview(session, ctx.now(session))
    numbers = {k: v for k, v in ov.items() if k in ("calls", "booked", "avg_qa", "flagged")}
    summary = model_tasks.summarise_week(ctx.llm(session), numbers, "No narrative today. See the numbers above.")
    set_state(session, "weekly_report", f"# Weekly report\n\nCalls {ov['calls']}, booked {ov['booked']}, average QA {ov['avg_qa']}.\n\n{summary}\n")
    return {"ok": True}


JOBS = {"dial_tick": job_dial_tick, "postcall": job_postcall, "followups": job_followups, "crm_sync": job_crm_sync, "report": job_report, "retention": job_retention}


def make_handlers(ctx: Ctx) -> dict[str, Handler]:
    return {kind: (lambda session, payload, fn=fn: fn(session, ctx)) for kind, fn in JOBS.items()}


def schedule_due(session: Session, ctx: Ctx) -> int:
    from sendora_core.db import utcnow
    from sendora_core.models import Job

    n, now = 0, utcnow()
    for kind, secs in INTERVALS.items():
        last = session.scalars(select(Job).where(Job.kind == kind).order_by(Job.id.desc())).first()
        if last is None:
            enqueue(session, kind); n += 1
        elif last.status in {"done", "failed"} and last.finished_at is not None and (now - last.finished_at.replace(tzinfo=now.tzinfo)).total_seconds() >= secs:
            enqueue(session, kind); n += 1
    return n


def run_cycle(session: Session, ctx: Ctx) -> dict:
    """Everything once, in order. The demo's Run button and the tests use this."""
    out = {"dial": job_dial_tick(session, ctx)}
    if ctx.settings.demo_mode:
        out["answered"] = demo.simulate_placed(session, ctx)
    out["postcall"] = job_postcall(session, ctx)
    out["followups"] = job_followups(session, ctx)
    record_event(session, "cycle.ran", None, None, {"placed": out["dial"]["placed"], "answered": out.get("answered", 0)})
    return out
