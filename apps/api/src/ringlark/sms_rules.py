"""One decision for every text message. The in call tool, the follow up that is queued after a call and the follow up that is sent later all ask here,
so a person who said stop (on the call, by text, or by being added to the do not call list) is never texted by a path that forgot to look."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from ringlark import suppression
from ringlark.models import Target
from ringlark.util import aware, normalize_phone, zone


@dataclass(frozen=True)
class SmsDecision:
    allowed: bool
    reason: str  # ok, suppressed, sms_revoked, no_sms_consent, sms_no_timezone, sms_quiet_hours
    later: bool = False  # True when waiting would help (quiet hours), False when the answer will not change by itself

    def __bool__(self) -> bool:
        return self.allowed


def consent_decision(session: Session, phone: str, target: Target | None) -> SmsDecision:
    """The permanent checks: do not call list, a withdrawn text consent, and a yes (a text START or the consent column of the import)."""
    p = normalize_phone(phone)
    if not p:
        return SmsDecision(False, "bad_number")
    if suppression.is_suppressed(session, p):
        return SmsDecision(False, "suppressed")
    latest = suppression.latest_consent(session, p, "sms")
    if latest == "revoked":
        return SmsDecision(False, "sms_revoked")
    if latest != "granted" and not (target is not None and target.sms_consent):
        return SmsDecision(False, "no_sms_consent")
    return SmsDecision(True, "ok")


def sms_decision(session: Session, settings, phone: str, target: Target | None, now: datetime, *, check_hours: bool = True) -> SmsDecision:
    """May this number be texted right now? An unknown time zone means no: a text must never arrive at night because a column was empty."""
    base = consent_decision(session, phone, target)
    if not base or not check_hours:
        return base
    z = zone(target.timezone) if target is not None and target.timezone else None
    if z is None:
        return SmsDecision(False, "sms_no_timezone")
    if not (settings.sms_window_start <= aware(now).astimezone(z).hour < settings.sms_window_end):
        return SmsDecision(False, "sms_quiet_hours", later=True)
    return SmsDecision(True, "ok")
