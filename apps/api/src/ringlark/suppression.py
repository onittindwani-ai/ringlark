"""The do not call list. A phone number on it is never dialled or texted again."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ringlark.models import ConsentRecord, Suppression
from ringlark.util import normalize_phone
from sendora_core.audit import record_audit


def is_suppressed(session: Session, phone: str) -> bool:
    return session.scalars(select(Suppression).where(Suppression.phone == normalize_phone(phone))).first() is not None


def add_suppression(session: Session, phone: str, reason: str, source: str, actor: str = "system") -> bool:
    p = normalize_phone(phone)
    if not p or is_suppressed(session, p):
        return False
    session.add(Suppression(phone=p, reason=reason, source=source))
    session.add(ConsentRecord(phone=p, kind="call", status="revoked", source=source))
    session.add(ConsentRecord(phone=p, kind="sms", status="revoked", source=source))
    session.flush()
    record_audit(session, actor, "suppression.added", f"phone:{p[-4:]}", {"reason": reason, "source": source})
    return True


def latest_consent(session: Session, phone: str, kind: str) -> str | None:
    """The newest answer by the time it was given (a text that arrives late but was sent earlier cannot undo a later STOP), then by arrival."""
    row = session.scalars(select(ConsentRecord).where(ConsentRecord.phone == normalize_phone(phone), ConsentRecord.kind == kind).order_by(ConsentRecord.created_at.desc(), ConsentRecord.id.desc())).first()
    return row.status if row else None
