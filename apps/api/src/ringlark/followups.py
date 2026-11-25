"""Sending approved follow ups. A follow up is sent only if approved, the person has not stopped contact (do not call list, a STOP text, "do not text me" on a call),
texts are inside the texting window in the person's time zone, and the mode is live. The checks run again at the moment of sending, because a STOP can arrive
after the approval. One follow up that cannot be sent never holds back the ones behind it."""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from ringlark import suppression
from ringlark.messages import ensure_stop_line, has_demo_text
from ringlark.models import Call, FollowUp, Target
from ringlark.sms_rules import sms_decision
from ringlark.util import is_e164, is_valid_email
from sendora_core.adapters import AdapterError
from sendora_core.models import Approval
from sendora_core.safety import DraftModeError, SafetyError, guard_write

log = logging.getLogger("ringlark.followups")


def _block(fu: FollowUp, out: dict, reason: str) -> None:
    fu.status, fu.blocked_reason = "blocked", reason[:60]
    out["blocked"] += 1


def send_due(session: Session, settings, adapters, now) -> dict:
    out = {"sent": 0, "drafted": 0, "blocked": 0, "rejected": 0, "waiting": 0, "failed": 0}
    for fu in session.scalars(select(FollowUp).where(FollowUp.status == "pending").order_by(FollowUp.id)):
        ap = session.get(Approval, fu.approval_id) if fu.approval_id else None
        if settings.follow_ups_need_approval and (ap is None or ap.status == "pending"):
            out["waiting"] += 1
            continue
        if ap is not None and ap.status == "rejected":
            fu.status = "rejected"; out["rejected"] += 1
            continue
        call = session.get(Call, fu.call_id)
        target = session.get(Target, call.target_id) if call is not None and call.target_id else None
        phone = call.peer_phone if call is not None else ""
        if not settings.demo_mode and has_demo_text(fu.body):
            _block(fu, out, "demo_text"); continue  # a body that still names the demo practice is never sent to a real person
        if fu.channel == "sms":
            if not is_e164(fu.to):
                _block(fu, out, "bad_recipient"); continue
            d = sms_decision(session, settings, fu.to, target, now)
            if not d:
                if d.later:
                    out["waiting"] += 1  # try again when it is daytime for them
                else:
                    _block(fu, out, d.reason)
                continue
            fu.body = ensure_stop_line(fu.body)
        else:
            if not is_valid_email(fu.to):
                _block(fu, out, "bad_recipient"); continue
            if phone and suppression.is_suppressed(session, phone):
                _block(fu, out, "suppressed"); continue  # someone who asked us to stop is not emailed either
            if phone and suppression.latest_consent(session, phone, "sms") == "revoked":
                _block(fu, out, "stop_requested"); continue  # the footer promises that a STOP text ends emails too
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
        except AdapterError as exc:  # a number the carrier refuses or a mailbox that bounces must not block the people behind it
            fu.status, fu.blocked_reason = "failed", f"send_failed: {str(exc)[:40]}"[:60]
            out["failed"] += 1
            log.warning("follow up %s could not be sent: %s", fu.id, type(exc).__name__)
    return out
