"""The do not call list. A phone number on it is never dialled or texted again.

A person who was erased (`erasure.py`) stays on the list as a salted hash, not as a number: the stop survives, the number does not. The salt is a random value kept in
the database (`rm_state`, key `erase_salt`). A phone number has few possible values, so anyone who has the whole database can still test a guess against a hash: the
hash hides a number from someone reading a screen or an export, it is not a lock. Treat the database and its backups as private either way."""
from __future__ import annotations

import hashlib
import hmac
import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from ringlark.models import ConsentRecord, State, Suppression
from ringlark.util import normalize_phone
from sendora_core.audit import record_audit

HASH_PREFIX = "sha:"
SALT_KEY = "erase_salt"


def _salt(session: Session, create: bool = False) -> str:
    row = session.get(State, SALT_KEY)
    if row is not None and row.value:
        return row.value
    if not create:
        return ""
    value = secrets.token_hex(16)
    if row is None:
        session.add(State(key=SALT_KEY, value=value))
    else:
        row.value = value
    session.flush()
    return value


def hashed_phone(session: Session, phone: str, create: bool = False) -> str:
    """The stored form of an erased person's number, or "" when no one was ever erased here (no salt yet) and `create` is off. 32 characters at most."""
    p, salt = normalize_phone(phone), _salt(session, create)
    if not p or not salt:
        return ""
    return HASH_PREFIX + hmac.new(salt.encode(), p.encode(), hashlib.sha256).hexdigest()[:28]


def phone_keys(session: Session, phone: str) -> list[str]:
    """Every way this number can be stored: as itself and, once someone has been erased, as its hash."""
    p = normalize_phone(phone)
    if not p:
        return [p]
    h = hashed_phone(session, p)
    return [p, h] if h else [p]


def is_suppressed(session: Session, phone: str) -> bool:
    return session.scalars(select(Suppression).where(Suppression.phone.in_(phone_keys(session, phone)))).first() is not None


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
    row = session.scalars(select(ConsentRecord).where(ConsentRecord.phone.in_(phone_keys(session, phone)), ConsentRecord.kind == kind).order_by(ConsentRecord.created_at.desc(), ConsentRecord.id.desc())).first()
    return row.status if row else None


def remove_suppression(session: Session, suppression_id: int, actor: str, note: str = "") -> bool:
    """Take a number off the list (owner only, see the route). Every stop record for that number goes with it, because without that the number would still be refused
    as "consent revoked". Nothing is granted: a campaign that requires prior consent still needs a consent on file before the number can be called again.
    This is for a number put on the list by mistake or by someone who spoofed the caller ID; the audit log keeps who did it and why."""
    row = session.get(Suppression, suppression_id)
    if row is None:
        return False
    for rec in session.scalars(select(ConsentRecord).where(ConsentRecord.phone == row.phone, ConsentRecord.status == "revoked")):
        session.delete(rec)
    label = row.phone[-4:] if not row.phone.startswith(HASH_PREFIX) else "erased"
    detail = {"reason": row.reason, "source": row.source, "note": note[:200]}
    session.delete(row)
    session.flush()
    record_audit(session, actor, "suppression.removed", f"phone:{label}", detail)
    return True
