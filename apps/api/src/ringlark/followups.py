"""Sending approved follow ups. A follow up is sent only if approved, the person has not stopped contact (do not call list, a STOP text, "do not text me" on a call),
texts are inside the texting window in the person's time zone, and the mode is live. The checks run again at the moment of sending, because a STOP can arrive
after the approval. One follow up that cannot be sent never holds back the ones behind it."""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from ringlark import suppression
from ringlark.adapters.base import UNKNOWN_OUTCOME
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
    out = {"sent": 0, "drafted": 0, "blocked": 0, "rejected": 0, "waiting": 0, "failed": 0, "unconfirmed": 0}
    # Read the rows first and save after every one: a later failure (or a rollback of the whole run) must never put a text that was already sent back to "pending".
    for fu in list(session.scalars(select(FollowUp).where(FollowUp.status == "pending").order_by(FollowUp.id))):
        stop = _one(session, settings, adapters, now, fu, out)
        session.commit()
        if stop:
            break
    return out


def _one(session: Session, settings, adapters, now, fu: FollowUp, out: dict) -> bool:
    """Decide and send one follow up. Returns True when the run should stop (the kill switch is on, so nothing behind this one can be sent either)."""
    ap = session.get(Approval, fu.approval_id) if fu.approval_id else None
    if settings.follow_ups_need_approval and (ap is None or ap.status == "pending"):
        out["waiting"] += 1
        return False
    if ap is not None and ap.status == "rejected":
        fu.status = "rejected"; out["rejected"] += 1
        return False
    call = session.get(Call, fu.call_id)
    target = session.get(Target, call.target_id) if call is not None and call.target_id else None
    phone = call.peer_phone if call is not None else ""
    if not settings.demo_mode and has_demo_text(fu.body):
        _block(fu, out, "demo_text"); return False  # a body that still names the demo practice is never sent to a real person
    if fu.channel == "sms":
        if not is_e164(fu.to):
            _block(fu, out, "bad_recipient"); return False
        d = sms_decision(session, settings, fu.to, target, now)
        if not d:
            if d.later:
                out["waiting"] += 1  # try again when it is daytime for them
            else:
                _block(fu, out, d.reason)
            return False
        fu.body = ensure_stop_line(fu.body)
    else:
        if not is_valid_email(fu.to):
            _block(fu, out, "bad_recipient"); return False
        if phone and suppression.is_suppressed(session, phone):
            _block(fu, out, "suppressed"); return False  # someone who asked us to stop is not emailed either
        if phone and suppression.latest_consent(session, phone, "sms") == "revoked":
            _block(fu, out, "stop_requested"); return False  # the footer promises that a STOP text ends emails too
    try:
        guard_write(settings, "followup.send")
    except DraftModeError:
        fu.status = "drafted"; out["drafted"] += 1
        return False
    except SafetyError:
        out["waiting"] += 1
        return True
    fu.status = "sending"
    session.commit()  # saved BEFORE the vendor is asked: a crash or a timeout can then never lead to a second send of the same message
    try:
        if fu.channel == "sms":
            adapters.sms.send(to=fu.to, text=fu.body)
        else:
            adapters.email.send(from_addr=settings.email_from, to=fu.to, subject=fu.subject, body=fu.body)
    except UNKNOWN_OUTCOME as exc:  # a timeout, a dropped line or a server error: it may have gone out. A person looks (POST /api/followups/{id}/resolve); it is never sent again by itself
        fu.status, fu.blocked_reason = "blocked", "send_unconfirmed"
        out["unconfirmed"] += 1
        log.warning("follow up %s may or may not have been sent (%s)", fu.id, type(exc).__name__)
    except AdapterError as exc:  # a number the carrier refuses or a mailbox that bounces must not block the people behind it
        fu.status, fu.blocked_reason = "failed", f"send_failed: {str(exc)[:40]}"[:60]
        out["failed"] += 1
        log.warning("follow up %s could not be sent: %s", fu.id, type(exc).__name__)
    except DraftModeError:  # the adapter's own guard says draft mode: nothing went out
        fu.status = "drafted"; out["drafted"] += 1
    except SafetyError:  # the adapter's own guard says the kill switch is on: nothing went out, so it goes back to waiting and the run stops
        fu.status = "pending"
        out["waiting"] += 1
        return True
    else:
        fu.status = "sent"; out["sent"] += 1
    return False
