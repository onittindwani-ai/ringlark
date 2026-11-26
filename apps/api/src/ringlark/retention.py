"""How long call content is kept. Transcripts, summaries and follow up messages of finished calls older than RETENTION_DAYS (default 365) are deleted by a daily job.

What stays: the call row itself (when, how long, the outcome and the number, which the do not call and attempt rules need), the QA score and the do not call and consent
records. To remove a person completely, the owner uses the erase route (`erasure.py`). Backups made before a deletion still hold the old content until they roll off (docs 11 and 13)."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import delete, or_, select, update
from sqlalchemy.orm import Session

from ringlark.models import Call, FollowUp, Turn
from ringlark.util import aware
from sendora_core.audit import record_audit

SETTLED_FOLLOWUPS = ("sent", "drafted", "blocked", "failed", "rejected")  # a message still waiting for approval or being sent is left alone


def run(session: Session, ctx) -> dict:
    days = ctx.settings.retention_days
    if days <= 0:
        return {"skipped": "RETENTION_DAYS is 0, so nothing is deleted by age"}
    if ctx.settings.demo_mode:
        return {"skipped": "demo mode keeps the practice data"}
    cutoff = aware(ctx.now(session)) - timedelta(days=days)
    old = select(Call.id).where(Call.created_at < cutoff, or_(Call.processed.is_(True), Call.status.in_(("failed", "blocked", "drafted"))))
    turns = session.execute(delete(Turn).where(Turn.call_id.in_(old))).rowcount or 0
    summaries = session.execute(update(Call).where(Call.id.in_(old), Call.summary != "").values(summary="")).rowcount or 0
    followups = session.execute(delete(FollowUp).where(FollowUp.call_id.in_(old), FollowUp.status.in_(SETTLED_FOLLOWUPS))).rowcount or 0
    out = {"turns": turns, "summaries": summaries, "followups": followups}
    if turns or summaries or followups:
        record_audit(session, "retention", "retention.run", None, {**out, "older_than_days": days})
    return out
