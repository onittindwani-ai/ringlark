"""Sending approved follow ups. A follow up is sent only if approved, the person is not on the do not call list, texts are inside the texting window, and the mode is live."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ringlark import suppression
from ringlark.models import Call, FollowUp, Target
from ringlark.util import aware, zone
from sendora_core.models import Approval
from sendora_core.safety import DraftModeError, SafetyError, guard_write


def send_due(session: Session, settings, adapters, now) -> dict:
    out = {"sent": 0, "drafted": 0, "blocked": 0, "rejected": 0, "waiting": 0}
    for fu in session.scalars(select(FollowUp).where(FollowUp.status == "pending").order_by(FollowUp.id)):
        ap = session.get(Approval, fu.approval_id) if fu.approval_id else None
        if settings.follow_ups_need_approval and (ap is None or ap.status == "pending"):
            out["waiting"] += 1
            continue
        if ap is not None and ap.status == "rejected":
            fu.status = "rejected"; out["rejected"] += 1
            continue
        call = session.get(Call, fu.call_id)
        if fu.channel == "sms":
            if suppression.is_suppressed(session, fu.to):
                fu.status, fu.blocked_reason = "blocked", "suppressed"; out["blocked"] += 1; continue
            t = session.get(Target, call.target_id) if call.target_id else None
            z = zone(t.timezone) if t else None
            if z and not (settings.sms_window_start <= aware(now).astimezone(z).hour < settings.sms_window_end):
                out["waiting"] += 1  # try again when it is daytime for them
                continue
        try:
            guard_write(settings, "followup.send")
            if fu.channel == "sms":
                adapters.sms.send(to=fu.to, text=fu.body)
            else:
                adapters.email.send(from_addr=settings.email_from, to=fu.to, subject=fu.subject, body=fu.body)
            fu.status = "sent"; out["sent"] += 1
        except DraftModeError:
            fu.status = "drafted"; out["drafted"] += 1
        except SafetyError:
            out["waiting"] += 1
            break
    return out
