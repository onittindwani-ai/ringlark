"""Importing targets (a CSV or a list). Bad rows are kept and flagged so the dialer can show why they are never called."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from ringlark.models import Target
from ringlark.util import normalize_phone, zone


@dataclass
class ImportReport:
    created: int = 0
    duplicates: int = 0
    flagged: dict[str, int] = field(default_factory=dict)

    def flag(self, k: str) -> None:
        self.flagged[k] = self.flagged.get(k, 0) + 1


def consent_flag(value: object) -> bool:
    """Consent is only ever granted by a clear yes. bool("false") is True in Python, so a CSV cell of "false", "no" or "0" used to grant text consent."""
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "yes", "y", "1", "granted", "opted in"}


def import_targets(session: Session, campaign_id: int, rows: list[dict]) -> ImportReport:
    rep = ImportReport()
    seen = {normalize_phone(p) or p for p in session.scalars(select(Target.phone).where(Target.campaign_id == campaign_id))}
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
        session.add(Target(campaign_id=campaign_id, first_name=str(r.get("first_name", ""))[:80], last_name=str(r.get("last_name", ""))[:80], company=str(r.get("company", ""))[:120], phone=norm or raw[:32],
                           email=str(r.get("email", ""))[:254], timezone=str(r.get("timezone", ""))[:64], sms_consent=consent_flag(r.get("sms_consent", False)), demo_persona=str(r.get("demo_persona", ""))[:40]))
        rep.created += 1
    session.flush()
    return rep
