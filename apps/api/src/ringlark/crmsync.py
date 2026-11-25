"""Writing a booked call to the CRM, without letting a slow CRM hold anything else up.

Post call processing saves everything that matters first (the transcript read, a stop request, the do not call list, the outcome) and only then asks the CRM.
A call that ended as booked is queued here and written in a short pass at the end of the run, with a hard time budget: the first timeout or server error ends
the pass, because the CRM that is hanging would hang for every other call too. What was not written stays queued and is tried again by the `crm_sync` job.

An outage does not use up a note's tries: a CRM that is hung or unreachable costs a delay, never a note. Only an answer about this one note counts as a try (a refusal, or a
reply that cannot be read), three of them move it to the dead letter list, and so does a note that has waited more than MAX_AGE_DAYS days. Dead letters are kept, are shown on
the Overview and in `GET /api/crm/dead-letters`, and the owner can put one back in the queue. The queue is worked in the order the calls were saved (by call number)."""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ringlark.adapters.base import UNKNOWN_OUTCOME, BadReply, PersonRecord
from ringlark.context import set_state
from ringlark.models import Call, State, Target
from sendora_core.adapters import AdapterError
from sendora_core.events import record_event
from sendora_core.safety import SafetyError, guard_write

PENDING = "crm_pending:"
DEAD = "crm_dead:"
RUN_BUDGET_S = 20.0  # all CRM writes of one run together
MAX_TRIES = 3  # answers about this one note that were not a success (an outage is not one)
MAX_AGE_DAYS = 7  # a note that has waited this long is moved to the dead letter list


def _now() -> datetime:
    return datetime.now(UTC)


def queue(session: Session, call: Call) -> None:
    set_state(session, f"{PENDING}{call.id}", f"0|{_now().isoformat()}")


def _read(row: State) -> tuple[int, datetime | None]:
    """(tries, when it was queued). A row made before the queue time was stored has none."""
    tries_text, _, when_text = (row.value or "0").partition("|")
    try:
        when = datetime.fromisoformat(when_text) if when_text else None
    except ValueError:
        when = None
    return (int(tries_text) if tries_text.isdigit() else 0), when


def _person(call: Call, target: Target) -> PersonRecord:
    return PersonRecord(first_name=target.first_name, last_name=target.last_name, phone=call.peer_phone, extra={"note": call.summary})


def write_now(session: Session, ctx, call: Call, target: Target) -> bool:
    """One try, right now. True when the CRM took it. The kill switch and "draft only" set in the app stop this write too, whatever MODE says."""
    try:
        guard_write(ctx.effective(session), "crm.upsert")
        ctx.adapters.crm.upsert_person(_person(call, target))
        return True
    except (SafetyError, AdapterError, *UNKNOWN_OUTCOME):
        return False


def _call_number(row: State) -> int:
    return int(row.key[len(PENDING):])


def flush(session: Session, ctx, budget_s: float = RUN_BUDGET_S, clock=time.monotonic) -> dict:
    """Write the queued calls, in the order they were saved, until the budget is used or the CRM shows it is hung. Saves after every call."""
    out = {"written": 0, "left": 0, "gave_up": 0}
    started = clock()
    rows = sorted((r for r in session.scalars(select(State).where(State.key.startswith(PENDING, autoescape=True))) if r.key[len(PENDING):].isdigit()), key=_call_number)
    for i, row in enumerate(rows):
        if clock() - started > budget_s:
            out["left"] += len(rows) - i
            break
        call_id = _call_number(row)
        call = session.get(Call, call_id)
        target = session.get(Target, call.target_id) if call is not None and call.target_id else None
        if call is None or target is None:
            session.delete(row)
            session.commit()
            continue
        tries, queued = _read(row)
        if queued is None:
            row.value = f"{tries}|{_now().isoformat()}"  # an older row: its age starts counting now
        elif _now() - queued > timedelta(days=MAX_AGE_DAYS):
            _dead(session, row, call_id, "waited_too_long", out)
            continue
        try:
            guard_write(ctx.effective(session), "crm.upsert")
            ctx.adapters.crm.upsert_person(_person(call, target))
        except SafetyError:  # the kill switch or draft mode: nothing is written, everything stays queued
            out["left"] += len(rows) - i
            session.commit()
            break
        except BadReply as exc:  # this one note got an answer nobody can read: that is about the note, not an outage, so it counts and the others go on
            out["left"] += 0 if _count_try(session, row, call_id, tries, type(exc).__name__, out) else 1
            session.commit()
            continue
        except UNKNOWN_OUTCOME:  # slow, hung or failing: an outage costs time, never a try, and the next call would wait just as long, so the pass ends here
            out["left"] += len(rows) - i
            session.commit()
            break
        except AdapterError as exc:  # a refusal for this one person only: go on with the others
            out["left"] += 0 if _count_try(session, row, call_id, tries, type(exc).__name__, out) else 1
            session.commit()
            continue
        session.execute(delete(State).where(State.key == row.key))
        session.commit()
        out["written"] += 1
    return out


def _count_try(session: Session, row: State, call_id: int, tries: int, why: str, out: dict) -> bool:
    """Count one answer that was not a success. True when this note has used its tries and went to the dead letter list."""
    tries += 1
    if tries >= MAX_TRIES:
        _dead(session, row, call_id, why, out)
        return True
    queued = _read(row)[1] or _now()
    row.value = f"{tries}|{queued.isoformat()}"
    return False


def _dead(session: Session, row: State, call_id: int, why: str, out: dict) -> None:
    session.execute(delete(State).where(State.key == row.key))
    set_state(session, f"{DEAD}{call_id}", f"{_now().isoformat()}|{why}")
    record_event(session, "crm.write_gave_up", "call", str(call_id), {"why": why})
    out["gave_up"] += 1
    session.commit()


def dead_letters(session: Session) -> list[dict]:
    """The notes that could not be written, newest first: the call number, when it was given up and why."""
    out = []
    for r in session.scalars(select(State).where(State.key.startswith(DEAD, autoescape=True))):
        when, _, why = (r.value or "").partition("|")
        if r.key[len(DEAD):].isdigit():
            out.append({"call_id": int(r.key[len(DEAD):]), "given_up_at": when, "why": why})
    return sorted(out, key=lambda d: d["call_id"], reverse=True)


def retry_dead(session: Session, call_id: int) -> bool:
    """Put one dead note back in the queue with fresh tries. False when there is no such dead letter."""
    row = session.get(State, f"{DEAD}{call_id}")
    if row is None:
        return False
    session.delete(row)
    set_state(session, f"{PENDING}{call_id}", f"0|{_now().isoformat()}")
    session.flush()
    return True
