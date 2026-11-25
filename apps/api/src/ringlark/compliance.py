"""The calling rules, as one pure function. No database, no network, so it can be property tested with random worlds.

Order of checks matters: the first reason that fails is the one reported.
This is software, not legal advice. Rules differ by country and state. See docs/13 and the compliance checklist page.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

from ringlark.util import aware, is_e164, zone


# Number ranges that cost the caller or the callee money or are never a person to sell to (not complete, see docs/13): US 900 and 976, UK 09, and the
# shared international ranges. They are refused whatever countries are allowed.
PREMIUM_PREFIXES = ("+1900", "+1976", "+449", "+882", "+883", "+979", "+870")
# Caribbean numbers share the +1 country code with the US and Canada, but they are other countries, and several are known for one ring and call back toll fraud. Because
# "+1" would allow them all, they are refused unless ALLOWED_CALLING_COUNTRIES names the exact area code (for example "+1,+1876" or "+1242"). Puerto Rico, Guam and the other
# US territories are not on this list.
CARIBBEAN_NANP = tuple(f"+1{n}" for n in (242, 246, 264, 268, 284, 345, 441, 473, 649, 664, 721, 758, 767, 784, 809, 829, 849, 868, 869, 876))


def premium_rate(phone: str) -> bool:
    return phone.startswith(PREMIUM_PREFIXES)


def country_allowed(phone: str, codes: tuple[str, ...]) -> bool:
    """An empty list means no country limit (the pure rules are tested without one); the dialer always passes ALLOWED_CALLING_COUNTRIES."""
    if not codes:
        return True
    if not phone.startswith(codes):
        return False
    if phone.startswith(CARIBBEAN_NANP):
        return any(len(c) > 2 and phone.startswith(c) for c in codes)  # only an entry as exact as the area code lets a Caribbean number through
    return True


@dataclass(frozen=True)
class Rules:
    window_start_hour: int = 9
    window_end_hour: int = 17
    weekdays_only: bool = True
    daily_cap: int = 50
    max_attempts: int = 3
    retry_gap_days: int = 1
    require_prior_consent: bool = False  # the pure rules start open; every campaign passes its own value, and a new campaign defaults to True


@dataclass(frozen=True)
class DialRequest:
    phone: str
    timezone: str
    now_utc: datetime
    rules: Rules
    kill_switch: bool = False
    draft_mode: bool = False
    greeting_has_disclosure: bool = True
    greeting_has_recording_notice: bool = True  # False when recording notices are required and the greeting has none
    on_dnc_list: bool = False
    call_consent: str | None = None  # granted, revoked or None
    calls_today: int = 0
    attempts_before: int = 0
    last_attempt_local_dates: tuple[str, ...] = field(default_factory=tuple)  # callee local dates of earlier attempts, YYYY-MM-DD
    last_attempt_utc: datetime | None = None
    in_flight: bool = False
    awaiting_review: bool = False  # the last call ended as needs_review and no person has read it yet, so nobody redials until they have
    allowed_codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str  # "ok", "draft_mode" or the failing rule

    def __bool__(self) -> bool:
        return self.allowed


def local_view(now_utc: datetime, tz_name: str):
    z = zone(tz_name)
    return None if z is None else aware(now_utc).astimezone(z)


def in_calling_window(now_utc: datetime, tz_name: str, rules: Rules) -> bool:
    loc = local_view(now_utc, tz_name)
    if loc is None:
        return False
    if rules.weekdays_only and loc.weekday() >= 5:
        return False
    return rules.window_start_hour <= loc.hour < rules.window_end_hour and (loc.hour + loc.minute / 60) < rules.window_end_hour


def evaluate(req: DialRequest) -> Decision:
    r = req.rules
    if req.kill_switch:
        return Decision(False, "kill_switch")
    if not req.greeting_has_disclosure:
        return Decision(False, "no_ai_disclosure")
    if not req.greeting_has_recording_notice:
        return Decision(False, "no_recording_notice")
    if not is_e164(req.phone):
        return Decision(False, "bad_number")
    if premium_rate(req.phone):
        return Decision(False, "premium_rate_number")
    if not country_allowed(req.phone, req.allowed_codes):
        return Decision(False, "country_not_allowed")
    if req.on_dnc_list:
        return Decision(False, "do_not_call")
    if req.call_consent == "revoked":
        return Decision(False, "consent_revoked")
    if r.require_prior_consent and req.call_consent != "granted":
        return Decision(False, "no_consent_on_file")
    if zone(req.timezone) is None:
        return Decision(False, "unknown_timezone")
    if not in_calling_window(req.now_utc, req.timezone, r):
        return Decision(False, "outside_hours")
    if req.in_flight:
        return Decision(False, "call_in_progress")
    if req.awaiting_review:
        return Decision(False, "awaiting_review")
    if req.calls_today >= r.daily_cap:
        return Decision(False, "daily_cap")
    if req.attempts_before >= r.max_attempts:
        return Decision(False, "max_attempts")
    loc = local_view(req.now_utc, req.timezone)
    if loc is not None and loc.date().isoformat() in req.last_attempt_local_dates:
        return Decision(False, "retry_same_day")
    if req.last_attempt_utc is not None:
        gap = (aware(req.now_utc) - aware(req.last_attempt_utc)).total_seconds() / 86400
        if gap < r.retry_gap_days:
            return Decision(False, "retry_too_soon")
    if req.draft_mode:
        return Decision(False, "draft_mode")
    return Decision(True, "ok")


def voicemail_allowed(allow_voicemail: bool, text: str) -> tuple[bool, str]:
    """A voicemail is left only when the campaign allows it and the message says it is an AI, who is calling and why."""
    from ringlark.disclosure import has_disclosure

    if not allow_voicemail:
        return False, "voicemail_off"
    t = (text or "").strip()
    if len(t.split()) < 8 or not has_disclosure(t) or not re.search(r"\b(about|regarding|calling for|calling from)\b", t, re.I):
        return False, "voicemail_text_incomplete"
    return True, "ok"
