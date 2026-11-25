"""Importing targets (a CSV or a list). Bad rows are kept and flagged so the dialer can show why they are never called."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from ringlark.models import ConsentRecord, Target
from ringlark.suppression import is_suppressed, latest_consent
from ringlark.util import is_valid_email, normalize_phone, zone


@dataclass
class ImportReport:
    created: int = 0
    duplicates: int = 0
    consents: int = 0
    flagged: dict[str, int] = field(default_factory=dict)

    def flag(self, k: str) -> None:
        self.flagged[k] = self.flagged.get(k, 0) + 1


def consent_flag(value: object) -> bool:
    """Consent is only ever granted by a clear yes. bool("false") is True in Python, so a CSV cell of "false", "no" or "0" used to grant text consent."""
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "yes", "y", "1", "granted", "opted in"}


def _record_call_consent(session: Session, rep: ImportReport, phone: str, value: object) -> None:
    """A `call_consent` column that says yes writes a granted call consent for that number, which a campaign with require_prior_consent needs.
    It never overrides a refusal: a number on the do not call list or with a later revoked consent stays refused, and the row is flagged."""
    if not phone or not consent_flag(value):
        return
    if is_suppressed(session, phone) or latest_consent(session, phone, "call") == "revoked":
        rep.flag("consent_not_recorded_refused_before")
        return
    session.add(ConsentRecord(phone=phone, kind="call", status="granted", source="import:call_consent"))
    rep.consents += 1


def import_targets(session: Session, campaign_id: int, rows: list[dict]) -> ImportReport:
    rep = ImportReport()
    # One person is one number across every campaign, so the same number is not added to a second campaign and called twice by two of them.
    seen = {normalize_phone(p) or p for p in session.scalars(select(Target.phone))}
    for r in rows:
        raw = str(r.get("phone", "")).strip()
        norm = normalize_phone(raw)
        key = norm or raw
        if key in seen:
            rep.duplicates += 1
            continue
        seen.add(key)
        if not norm:
            rep.flag("bad_number")
        if not zone(str(r.get("timezone", ""))):
            rep.flag("unknown_timezone")
        email = str(r.get("email", "")).strip()
        if email and not is_valid_email(email):  # one plain address only: "a@x.com, b@y.com" would send one email to two people
            rep.flag("bad_email")
            email = ""
        session.add(Target(campaign_id=campaign_id, first_name=str(r.get("first_name", ""))[:80], last_name=str(r.get("last_name", ""))[:80], company=str(r.get("company", ""))[:120], phone=norm or raw[:32],
                           email=email, timezone=str(r.get("timezone", ""))[:64], sms_consent=consent_flag(r.get("sms_consent", False)), demo_persona=str(r.get("demo_persona", ""))[:40]))
        rep.created += 1
        _record_call_consent(session, rep, norm, r.get("call_consent", False))
    session.flush()
    return rep
