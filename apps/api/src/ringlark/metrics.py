"""Numbers for the dashboard. All of them are counts read from the database, nothing is estimated by a model."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

import json

from ringlark.models import Call, Campaign, FollowUp, QAScore, State, Suppression, Target
from ringlark.util import aware
from sendora_core.models import Approval

REAL = ("placed", "in_progress", "completed", "failed")


def overview(session: Session, now: datetime) -> dict:
    cnt = lambda *w: int(session.scalar(select(func.count()).select_from(Call).where(*w)) or 0)  # noqa: E731
    total = cnt(Call.status.in_(REAL))
    done = cnt(Call.status == "completed")
    day0 = aware(now).replace(hour=0, minute=0, second=0, microsecond=0)
    disp = dict(session.execute(select(Call.disposition, func.count()).where(Call.status == "completed").group_by(Call.disposition)).all())
    blocked = dict(session.execute(select(Call.blocked_reason, func.count()).where(Call.status == "blocked").group_by(Call.blocked_reason)).all())
    talked = sum(v for k, v in disp.items() if k not in ("no_answer", "voicemail_no_message", "voicemail_left", "ivr_no_human", ""))
    series = []
    for i in range(6, -1, -1):
        a, b = day0 - timedelta(days=i), day0 - timedelta(days=i - 1)
        series.append({"day": a.date().isoformat(), "calls": cnt(Call.status.in_(REAL), Call.created_at >= a, Call.created_at < b), "booked": cnt(Call.disposition == "booked", Call.created_at >= a, Call.created_at < b)})
    avg_qa = session.scalar(select(func.avg(QAScore.score)))
    last = session.get(State, "last_dial")
    stamp = session.get(State, "last_dial_at")
    last_at = stamp.value if stamp and stamp.value else None
    age = int((datetime.now(UTC) - aware(datetime.fromisoformat(last_at))).total_seconds()) if last_at else None  # a quiet stop of the dialer shows up here
    held = dict(blocked)
    for k, v in (json.loads(last.value)["reasons"] if last and last.value else {}).items():
        if k not in held and k not in ("draft_mode",):
            held[k] = v
    return {"calls": total, "completed": done, "calls_today": cnt(Call.status.in_(REAL), Call.created_at >= day0), "booked": disp.get("booked", 0), "talk_rate": (talked / done) if done else 0.0,
            "book_rate": (disp.get("booked", 0) / done) if done else 0.0, "avg_qa": round(float(avg_qa), 1) if avg_qa is not None else None,
            "flagged": int(session.scalar(select(func.count()).select_from(QAScore).where(QAScore.flagged.is_(True), QAScore.reviewed.is_(False))) or 0),
            "dispositions": [{"code": k or "none", "count": v} for k, v in sorted(disp.items(), key=lambda kv: -kv[1])], "blocked": [{"reason": k, "count": v} for k, v in sorted(held.items(), key=lambda kv: -kv[1])],
            "drafted": cnt(Call.status == "drafted"), "suppressed": int(session.scalar(select(func.count()).select_from(Suppression)) or 0),
            "pending_approvals": int(session.scalar(select(func.count()).select_from(Approval).where(Approval.status == "pending")) or 0),
            "targets": {k: int(v) for k, v in session.execute(select(Target.status, func.count()).group_by(Target.status)).all()},
            "campaigns_running": int(session.scalar(select(func.count()).select_from(Campaign).where(Campaign.status == "running")) or 0), "series": series,
            "last_dial_at": last_at, "dial_tick_age_s": age, "followups_pending": int(session.scalar(select(func.count()).select_from(FollowUp).where(FollowUp.status == "pending")) or 0)}
