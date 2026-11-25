"""Erasing one person: every copy this app holds of their calls, words and messages, for a request to delete their data.

Deleted: their calls with the transcript, summary, outcome, QA score and one time action rows, their follow ups (texts and emails), their entry in every campaign list, their
consent records and plain do not call entry, and the events recorded for those calls. Kept: a salted hash of the number on the do not call list (and a stop record under that
hash), so a person who asked to be left alone is not imported and called again. The audit log keeps only the last four digits and counts, and cannot be edited.

Not deleted, because this app does not hold them: copies in the CRM, at Telnyx, Ultravox, Cal.com and the mail server, and in backups made earlier (docs 11 and 13)."""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ringlark import suppression
from ringlark.models import Call, CallAction, ConsentRecord, Disposition, FollowUp, QAScore, State, Suppression, Target, Turn
from ringlark.util import normalize_phone
from sendora_core.audit import record_audit
from sendora_core.models import Event


def erase_person(session: Session, phone: str, actor: str, keep_do_not_call: bool = True) -> dict:
    p = normalize_phone(phone)
    if not p:
        raise ValueError("Use a full number with the country code, for example +14155550100.")
    was_listed = suppression.is_suppressed(session, p)
    latest = {kind: suppression.latest_consent(session, p, kind) for kind in ("call", "sms")}
    plain = [p]
    target_ids = list(session.scalars(select(Target.id).where(Target.phone == p)))
    call_ids = list(session.scalars(select(Call.id).where((Call.peer_phone == p) | (Call.target_id.in_(target_ids)) if target_ids else Call.peer_phone == p)))
    counts = {"calls": len(call_ids), "people": len(target_ids)}
    if call_ids:
        ids = [str(i) for i in call_ids]
        session.execute(delete(CallAction).where(CallAction.call_id.in_(call_ids)))
        counts["turns"] = session.execute(delete(Turn).where(Turn.call_id.in_(call_ids))).rowcount or 0
        counts["followups"] = session.execute(delete(FollowUp).where(FollowUp.call_id.in_(call_ids))).rowcount or 0
        session.execute(delete(QAScore).where(QAScore.call_id.in_(call_ids)))
        session.execute(delete(Disposition).where(Disposition.call_id.in_(call_ids)))
        session.execute(delete(Event).where(Event.entity_type == "call", Event.entity_id.in_(ids)))
        for prefix in ("postcall_empty:", "crm_pending:"):
            session.execute(delete(State).where(State.key.in_([f"{prefix}{i}" for i in call_ids])))
        session.execute(delete(Call).where(Call.id.in_(call_ids)))
    counts["followups"] = counts.get("followups", 0) + (session.execute(delete(FollowUp).where(FollowUp.to == p)).rowcount or 0)
    if target_ids:
        session.execute(delete(Target).where(Target.id.in_(target_ids)))
    session.execute(delete(ConsentRecord).where(ConsentRecord.phone.in_(plain)))
    session.execute(delete(Suppression).where(Suppression.phone.in_(plain)))
    keep = keep_do_not_call or was_listed
    kept = "none"
    if keep:
        h = suppression.hashed_phone(session, p, create=True)
        if not session.scalar(select(Suppression.id).where(Suppression.phone == h)):
            session.add(Suppression(phone=h, reason="Erased on request", source="erase"))
        for kind in ("call", "sms"):
            session.add(ConsentRecord(phone=h, kind=kind, status="revoked", source="erase"))
        kept = "do_not_call_hash"
    else:
        for kind, status in latest.items():  # a stop that was on record is never forgotten, even when the owner chose not to keep the person on the list
            if status == "revoked":
                session.add(ConsentRecord(phone=suppression.hashed_phone(session, p, create=True), kind=kind, status="revoked", source="erase"))
                kept = "stop_hash"
    session.flush()
    counts["kept"] = kept
    record_audit(session, actor, "person.erased", f"phone:{p[-4:]}", counts)
    return counts
