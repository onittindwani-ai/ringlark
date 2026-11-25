from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ringlark import metrics
from ringlark.api.deps import db, get_ctx, owner, writer
from ringlark.api.serializers import iso
from ringlark.context import Ctx, set_state
from ringlark.models import FollowUp
from ringlark.registry import CATEGORIES, ENV_VARS
from sendora_core.approvals import ApprovalError, decide
from sendora_core.audit import record_audit, verify_audit_chain
from sendora_core.models import Approval, AuditEntry

router = APIRouter(prefix="/api", tags=["operations"])


@router.get("/overview", summary="Numbers for the overview page")
def overview(s: Session = Depends(db, scope="function"), ctx: Ctx = Depends(get_ctx)):
    return metrics.overview(s, ctx.now(s))


@router.get("/approvals", summary="Pending and recent approvals")
def approvals(s: Session = Depends(db, scope="function")):
    rows = list(s.scalars(select(Approval).order_by(Approval.id.desc()).limit(100)))
    return [{"id": a.id, "action": a.action, "summary": a.summary, "risk": a.risk, "status": a.status, "requested_by": a.requested_by, "decided_by": a.decided_by, "note": a.decision_note, "created_at": iso(a.created_at), "payload": a.payload} for a in rows]


class DecideIn(BaseModel):
    approve: bool
    note: str = Field(default="", max_length=500)


@router.post("/approvals/{approval_id}/decide", summary="Approve or reject")
def decide_approval(approval_id: int, body: DecideIn, s: Session = Depends(db, scope="function"), u: dict = Depends(writer)):
    try:
        a = decide(s, approval_id, body.approve, u["user"], u["role"], body.note or None)
    except ApprovalError as exc:
        raise HTTPException(409, str(exc)) from exc
    if a.action == "followup.send" and a.status == "rejected" and a.payload.get("followup_id"):
        fu = s.get(FollowUp, int(a.payload["followup_id"]))  # follows the decision that was really saved, not the request
        if fu and fu.status == "pending":
            fu.status = "rejected"
    return {"status": a.status}


@router.get("/audit", summary="Audit log, newest first")
def audit(limit: int = Query(100, ge=1, le=1000), s: Session = Depends(db, scope="function")):
    rows = s.scalars(select(AuditEntry).order_by(AuditEntry.id.desc()).limit(limit))
    return [{"id": e.id, "actor": e.actor, "action": e.action, "target": e.target, "detail": e.detail, "at": e.created_at} for e in rows]


@router.get("/audit/verify", summary="Check the audit chain has not been edited")
def audit_verify(s: Session = Depends(db, scope="function")):
    ok, bad = verify_audit_chain(s)
    return {"ok": ok, "first_bad_id": bad}


@router.get("/integrations", summary="Every adapter, which one is selected, and what it needs")
def integrations(ctx: Ctx = Depends(get_ctx)):
    st = ctx.settings
    chosen = {c: getattr(st, f"{c}_adapter") for c in CATEGORIES}
    out = []
    for row in ctx.registry.describe():
        env = ENV_VARS.get((row["category"], row["name"]), [])
        out.append({**row, "selected": chosen.get(row["category"]) == row["name"], "env_vars": env, "configured": all(bool(getattr(st, v.lower(), "")) for v in env) if env else True})
    return {"categories": list(CATEGORIES), "adapters": out, "demo_mode": st.demo_shortcuts}


@router.post("/integrations/{category}/test", summary="Test the selected adapter in a category")
def test_integration(category: str, ctx: Ctx = Depends(get_ctx), u: dict = Depends(writer)):
    if category not in CATEGORIES:
        raise HTTPException(404, "Unknown category.")
    ok, detail = getattr(ctx.adapters, category).healthcheck()
    return {"category": category, "ok": ok, "detail": detail}


@router.get("/settings", summary="Mode, kill switch and config problems")
def get_settings(s: Session = Depends(db, scope="function"), ctx: Ctx = Depends(get_ctx)):
    eff = ctx.effective(s)
    return {"mode": ctx.settings.mode.value, "effective_mode": eff.mode.value, "kill_switch": eff.kill_switch, "demo_mode": ctx.settings.demo_shortcuts, "problems": ctx.settings.problems(),
            "window": f"{ctx.settings.default_window_start:02d}:00 to {ctx.settings.default_window_end:02d}:00 callee local time", "follow_ups_need_approval": ctx.settings.follow_ups_need_approval,
            "llm": {"offline": "offline stand in", "fixture": "recorded answers"}.get(ctx.settings.effective_llm_backend.value, "live (UNVERIFIED)")}


class SettingsIn(BaseModel):
    kill_switch: bool | None = None
    force_draft: bool | None = None


@router.post("/settings", summary="Turn the kill switch or draft mode on or off (owner only). The app can never switch live calling on.")
def post_settings(body: SettingsIn, s: Session = Depends(db, scope="function"), ctx: Ctx = Depends(get_ctx), u: dict = Depends(owner)):
    if body.kill_switch is not None:
        set_state(s, "kill_switch", "1" if body.kill_switch else "0")
        record_audit(s, u["user"], "settings.kill_switch", None, {"on": body.kill_switch})
    if body.force_draft is not None:
        set_state(s, "force_draft", "1" if body.force_draft else "0")
        record_audit(s, u["user"], "settings.force_draft", None, {"on": body.force_draft})
    s.flush()
    return get_settings(s, ctx)


@router.get("/metrics/versions", summary="How each prompt version did: calls, booked share and average QA score")
def version_metrics(s: Session = Depends(db, scope="function")):
    from sqlalchemy import func

    from ringlark.models import Agent, Call, PromptVersion, QAScore

    out = []
    for v in s.scalars(select(PromptVersion).order_by(PromptVersion.agent_id, PromptVersion.version)):
        calls = list(s.scalars(select(Call).where(Call.prompt_version_id == v.id, Call.status == "completed")))
        booked = sum(1 for c in calls if c.disposition == "booked")
        qa = s.scalar(select(func.avg(QAScore.score)).join(Call, Call.id == QAScore.call_id).where(Call.prompt_version_id == v.id))
        out.append({"agent": s.get(Agent, v.agent_id).name, "version": v.version, "note": v.note, "calls": len(calls), "booked": booked, "book_rate": (booked / len(calls)) if calls else None, "avg_qa": round(float(qa), 1) if qa is not None else None})
    return out
