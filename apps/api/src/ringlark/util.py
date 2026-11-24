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


def is_e164(value: str) -> bool:
    return bool(E164_RE.match((value or "").strip()))


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


def normalize_phone(value: str) -> str:
    """Keep a leading plus and digits only. Returns an empty string when the result is not E.164."""
    v = (value or "").strip()
    out = ("+" if v.startswith("+") else "") + re.sub(r"\D", "", v)
    return out if E164_RE.match(out) else ""
