"""Importing targets (a CSV or a list). Bad rows are kept and flagged so the dialer can show why they are never called."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ringlark.models import ConsentRecord, Target
from ringlark.suppression import is_suppressed, latest_consent
from ringlark.util import is_valid_email, normalize_phone, zone
from sendora_core.audit import record_audit


@dataclass
class ImportReport:
    created: int = 0
    duplicates: int = 0
    consents: int = 0
    consent_updates: int = 0  # a row for a person already in the list that carried a consent: recorded, and audited one by one
    flagged: dict[str, int] = field(default_factory=dict)

    def flag(self, k: str) -> None:
        self.flagged[k] = self.flagged.get(k, 0) + 1


def consent_flag(value: object) -> bool:
    """Consent is only ever granted by a clear yes. bool("false") is True in Python, so a CSV cell of "false", "no" or "0" used to grant text consent."""
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "yes", "y", "1", "granted", "opted in"}


def wants_call_consent(rows: list[dict]) -> bool:
    """True when any row says a person agreed to be called. Only the owner may import that (see the route): it is what lets a campaign that requires consent call them."""
    return any(consent_flag(r.get("call_consent", False)) for r in rows)


def _consent_date(rep: ImportReport, raw: object) -> tuple[bool, datetime | None]:
    """(usable, the date the person agreed). Empty means "now". A date that cannot be read, or lies in the future, is not evidence of anything: the consent is not recorded."""
    text = str(raw or "").strip()
    if not text:
        rep.flag("consent_without_date")
        return True, None
    try:
        when = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        rep.flag("consent_bad_date")
        return False, None
    when = when.replace(tzinfo=UTC) if when.tzinfo is None else when.astimezone(UTC)
    if when > datetime.now(UTC) + timedelta(days=1):
        rep.flag("consent_future_date")
        return False, None
    return True, when


def _record_call_consent(session: Session, rep: ImportReport, phone: str, row: dict, actor: str, duplicate: bool) -> None:
    """A `call_consent` column that says yes writes a granted call consent for that number, which a campaign with require_prior_consent needs. It keeps the date the person
    agreed (`consent_date`), where (`consent_source`) and a note (`consent_note`), so the record is evidence and not just a flag. It never overrides a refusal: a number on the
    do not call list or with a later revoked consent stays refused, and the row is flagged. A row for a person already in the list updates the consent and is audited."""
    if not phone or not consent_flag(row.get("call_consent", False)):
        return
    if is_suppressed(session, phone) or latest_consent(session, phone, "call") == "revoked":
        rep.flag("consent_not_recorded_refused_before")
        return
    usable, when = _consent_date(rep, row.get("consent_date"))
    if not usable:
        return
    source = str(row.get("consent_source") or "").strip()[:48]
    if not source:
        rep.flag("consent_without_source")
    stamp = {"created_at": when} if when else {}
    session.add(ConsentRecord(phone=phone, kind="call", status="granted", source=f"import:{source}" if source else "import:call_consent", note=str(row.get("consent_note") or "").strip()[:300], **stamp))
    rep.consents += 1
    if duplicate:
        rep.consent_updates += 1
        record_audit(session, actor, "consent.imported", f"phone:{phone[-4:]}", {"kind": "call", "already_in_list": True, "source": source, "date": when.date().isoformat() if when else "import time"})


def import_targets(session: Session, campaign_id: int, rows: list[dict], actor: str = "import") -> ImportReport:
    rep = ImportReport()
    # One person is one number across every campaign, so the same number is not added to a second campaign and called twice by two of them.
    seen = {normalize_phone(p) or p for p in session.scalars(select(Target.phone))}
    for r in rows:
        raw = str(r.get("phone", "")).strip()
        norm = normalize_phone(raw)
        key = norm or raw
        if key in seen:
            rep.duplicates += 1
            _update_duplicate(session, rep, norm, r, actor)  # a duplicate row may still carry a consent, and it is not dropped silently
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
        _record_call_consent(session, rep, norm, r, actor, duplicate=False)
    session.flush()
    return rep


def _update_duplicate(session: Session, rep: ImportReport, norm: str, row: dict, actor: str) -> None:
    if not norm:
        return
    _record_call_consent(session, rep, norm, row, actor, duplicate=True)
    if consent_flag(row.get("sms_consent", False)) and not is_suppressed(session, norm) and latest_consent(session, norm, "sms") != "revoked":
        t = session.scalars(select(Target).where(Target.phone == norm)).first()
        if t is not None and not t.sms_consent:
            t.sms_consent = True
            rep.consent_updates += 1
            record_audit(session, actor, "consent.imported", f"phone:{norm[-4:]}", {"kind": "sms", "already_in_list": True})
