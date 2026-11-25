"""Small, well tested helpers: email and phone checks, time zones, safe text."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}$")
E164_RE = re.compile(r"^\+[1-9]\d{6,14}$")
ROLE_LOCALPARTS = {
    "info", "sales", "admin", "office", "support", "hello", "contact", "team", "billing", "help",
    "marketing", "hr", "jobs", "careers", "noreply", "no-reply", "enquiries", "inquiries", "accounts",
}
FREE_MAIL_DOMAINS = {"gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "icloud.com", "proton.me", "gmail.example.test"}


def normalize_email(value: str) -> str:
    return (value or "").strip().lower()


def is_valid_email(value: str) -> bool:
    v = normalize_email(value)
    return len(v) <= 254 and bool(EMAIL_RE.match(v)) and ".." not in v


def email_domain(value: str) -> str:
    v = normalize_email(value)
    return v.rsplit("@", 1)[1] if "@" in v else ""


def is_role_based(value: str) -> bool:
    v = normalize_email(value)
    return "@" in v and v.split("@", 1)[0] in ROLE_LOCALPARTS


def is_free_mail(value: str) -> bool:
    return email_domain(value) in FREE_MAIL_DOMAINS


def _nanp_ok(number: str) -> bool:
    """A +1 number is +1 and exactly ten more digits, and the area code does not start with 0 or 1. Anything else with +1 in front is a typo, an extension or a trap."""
    return not number.startswith("+1") or (len(number) == 12 and number[2] not in "01")


def is_e164(value: str) -> bool:
    v = (value or "").strip()
    return bool(E164_RE.match(v)) and _nanp_ok(v)


def zone(name: str) -> ZoneInfo | None:
    if not name:
        return None
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        return None


def aware(dt: datetime | None) -> datetime | None:
    """SQLite returns naive datetimes. Everything in Ringlark is UTC, so a naive value is read as UTC."""
    if dt is None:
        return None
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


def clean_header(value: str) -> str:
    """Remove line breaks so a value can never add a mail header."""
    return re.sub(r"[\r\n]+", " ", value or "").strip()


PHONE_TEXT_RE = re.compile(r"^\+?[0-9 ()\-.]+$")


def normalize_phone(value: str) -> str:
    """Keep a leading plus and digits only. Returns an empty string when the result is not E.164, when the text holds anything but digits and the usual separators
    (a word like "ext", an "x" or a "#" means an extension: "+1 415 555 0100 ext 22" must never become +1415555010022), or when a +1 number is not ten digits long."""
    v = (value or "").strip()
    if not PHONE_TEXT_RE.match(v):
        return ""
    out = ("+" if v.startswith("+") else "") + re.sub(r"\D", "", v)
    return out if E164_RE.match(out) and _nanp_ok(out) else ""
