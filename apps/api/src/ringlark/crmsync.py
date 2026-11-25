"""Writing a booked call to the CRM, without letting a slow CRM hold anything else up.

Post call processing saves everything that matters first (the transcript read, a stop request, the do not call list, the outcome) and only then asks the CRM.
A call that ended as booked is queued here and written in a short pass at the end of the run, with a hard time budget: the first timeout or server error ends
the pass, because the CRM that is hanging would hang for every other call too. What was not written stays queued and is tried again by the `crm_sync` job, up to
three times, so a hung CRM costs a few seconds and a delayed note, never a stop request that waits."""

from __future__ import annotations

import time

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ringlark.adapters.base import UNKNOWN_OUTCOME, PersonRecord
from ringlark.context import set_state
from ringlark.models import Call, State, Target
from sendora_core.adapters import AdapterError
from sendora_core.events import record_event
from sendora_core.safety import SafetyError, guard_write

PENDING = "crm_pending:"
RUN_BUDGET_S = 20.0  # all CRM writes of one run together
MAX_TRIES = 3


def queue(session: Session, call: Call) -> None:
    set_state(session, f"{PENDING}{call.id}", "0")


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


def flush(session: Session, ctx, budget_s: float = RUN_BUDGET_S, clock=time.monotonic) -> dict:
    """Write the queued calls, in the order they were queued, until the budget is used or the CRM shows it is hung. Saves after every call."""
    out = {"written": 0, "left": 0, "gave_up": 0}
    started = clock()
    rows = list(session.scalars(select(State).where(State.key.startswith(PENDING, autoescape=True)).order_by(State.key)))
    for i, row in enumerate(rows):
        if clock() - started > budget_s:
            out["left"] += len(rows) - i
            break
        call_id = int(row.key[len(PENDING):])
        call = session.get(Call, call_id)
        target = session.get(Target, call.target_id) if call is not None and call.target_id else None
        if call is None or target is None:
            session.delete(row)
            session.commit()
            continue
        try:
            guard_write(ctx.effective(session), "crm.upsert")
            ctx.adapters.crm.upsert_person(_person(call, target))
        except SafetyError:  # the kill switch or draft mode: nothing is written, everything stays queued
            out["left"] += len(rows) - i
            break
        except UNKNOWN_OUTCOME as exc:  # slow, hung or failing: the next call would wait just as long, so the pass ends here
            out["left"] += len(rows) - i - (1 if _failed(session, row, call_id, type(exc).__name__, out) else 0)
            session.commit()
            break
        except AdapterError as exc:  # a refusal for this one person only: go on with the others
            out["left"] += 0 if _failed(session, row, call_id, type(exc).__name__, out) else 1
            session.commit()
            continue
        session.execute(delete(State).where(State.key == row.key))
        session.commit()
        out["written"] += 1
    return out


def _failed(session: Session, row: State, call_id: int, why: str, out: dict) -> bool:
    """Count one failed try. True when this call has used its tries and was dropped from the queue (an event says so)."""
    tries = int(row.value or 0) + 1
    if tries >= MAX_TRIES:
        session.execute(delete(State).where(State.key == row.key))
        record_event(session, "crm.write_gave_up", "call", str(call_id), {"why": why})
        out["gave_up"] += 1
        return True
    row.value = str(tries)
    return False
