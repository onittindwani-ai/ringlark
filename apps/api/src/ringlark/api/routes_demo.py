"""Demo mode only. These routes return 404 when DEMO_MODE is off."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ringlark import clock, demo
from ringlark.api.deps import db, demo_only, get_ctx, owner, writer
from ringlark.context import Ctx
from ringlark.jobs import run_cycle

router = APIRouter(prefix="/api/demo", tags=["demo"], dependencies=[Depends(demo_only)])


@router.get("/state", summary="The demo clock")
def state(s: Session = Depends(db, scope="function"), ctx: Ctx = Depends(get_ctx)):
    return {"now": ctx.now(s).isoformat()}


@router.post("/reset", summary="Reset to the seed data and a fresh clock")
def reset(s: Session = Depends(db, scope="function"), ctx: Ctx = Depends(get_ctx), u: dict = Depends(owner)):
    return demo.reset(s, ctx)


@router.post("/tick", summary="Run every job once, now")
def tick(s: Session = Depends(db, scope="function"), ctx: Ctx = Depends(get_ctx), u: dict = Depends(writer)):
    return run_cycle(s, ctx)


class AdvanceIn(BaseModel):
    hours: float = Field(ge=0, le=24 * 30)


@router.post("/advance", summary="Move the demo clock forward")
def advance(b: AdvanceIn, s: Session = Depends(db, scope="function"), ctx: Ctx = Depends(get_ctx), u: dict = Depends(writer)):
    return {"now": clock.advance(s, b.hours).isoformat()}


class StressIn(BaseModel):
    n: int = Field(ge=1, le=20000)


@router.post("/stress-calls", summary="Add many sample finished calls, to check that long tables stay fast")
def stress(b: StressIn, s: Session = Depends(db, scope="function"), ctx: Ctx = Depends(get_ctx), u: dict = Depends(owner)):
    from datetime import timedelta

    from ringlark.models import Agent, Call

    agent = s.query(Agent).first()
    now = ctx.now(s)
    s.bulk_insert_mappings(Call, [{"agent_id": agent.id, "direction": "outbound", "peer_phone": f"+1415555{i % 10000:04d}", "status": "completed", "disposition": ("booked", "not_interested", "no_answer", "interested_callback")[i % 4],
                                   "duration_ms": 20000 + (i % 50) * 1000, "started_at": now - timedelta(minutes=i), "created_at": now - timedelta(minutes=i), "attempt": 1, "summary": "Stress row."} for i in range(b.n)])
    return {"added": b.n}
