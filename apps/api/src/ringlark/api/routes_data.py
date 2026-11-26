from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ringlark import dialer, erasure, intake, prompts, qa as qamod, suppression, waveform
from ringlark.agent_offline import prompt_flags
from ringlark.api.deps import db, get_ctx, owner, writer
from ringlark.compliance import voicemail_allowed
from ringlark.disclosure import greeting_problems
from ringlark.api.serializers import agent_row, call_row, campaign_row, followup_row, iso, target_row
from ringlark.context import Ctx
from ringlark.datadir import persona_dir
from ringlark.demo import replay_events
from ringlark.models import Agent, Call, Campaign, FollowUp, Number, QAScore, Suppression, Target
from ringlark.agent_factory import backend_factory, engine_label
from ringlark.personas import load_personas, run_persona, run_suite
from ringlark.util import normalize_phone
from sendora_core.audit import record_audit
from sendora_core.events import record_event

router = APIRouter(prefix="/api", tags=["data"])
FINISHED_STATUSES = ("booked", "done", "suppressed")  # the dialer never calls these people again


# ---- calls
@router.get("/calls", summary="Call log")
def calls(status: str = "", disposition: str = "", q: str = "", limit: int = Query(200, ge=1, le=5000), s: Session = Depends(db, scope="function")):
    stmt = select(Call).where(Call.status != "blocked").order_by(Call.created_at.desc(), Call.id.desc()).limit(limit)
    if status:
        stmt = stmt.where(Call.status == status)
    if disposition:
        stmt = stmt.where(Call.disposition == disposition)
    if q:
        # A name or a number, written the way a person writes it: "Cleo", "+1415", "(415) 555-0102" all find the call.
        digits = re.sub(r"\D", "", q)
        by_name = select(Target.id).where((func.lower(Target.first_name) + " " + func.lower(Target.last_name)).contains(q.strip().lower(), autoescape=True))
        parts = [Call.peer_phone.contains(q.strip(), autoescape=True), Call.target_id.in_(by_name)]
        if digits:
            parts.append(Call.peer_phone.contains(digits, autoescape=True))
        stmt = stmt.where(or_(*parts))
    rows = list(s.scalars(stmt))
    agents = {a.id: a.name for a in s.scalars(select(Agent))}
    targets = {t.id: f"{t.first_name} {t.last_name}".strip() for t in s.scalars(select(Target).where(Target.id.in_({c.target_id for c in rows if c.target_id})))} if rows else {}
    qas = {x.call_id: x for x in s.scalars(select(QAScore).where(QAScore.call_id.in_([c.id for c in rows])))} if rows and len(rows) < 900 else {x.call_id: x for x in s.scalars(select(QAScore))}
    return [call_row(c, targets.get(c.target_id, ""), agents.get(c.agent_id, ""), qas.get(c.id)) for c in rows]


@router.get("/calls/{call_id}", summary="One call with its transcript, QA score and follow ups")
def call_detail(call_id: int, s: Session = Depends(db, scope="function")):
    c = s.get(Call, call_id)
    if c is None:
        raise HTTPException(404, "That call does not exist.")
    t = s.get(Target, c.target_id) if c.target_id else None
    q = s.scalar(select(QAScore).where(QAScore.call_id == c.id))
    turns = [{"position": x.position, "speaker": x.speaker, "text": x.text, "start_ms": x.start_ms, "end_ms": x.end_ms} for x in c.turns]
    dur = max(c.duration_ms, turns[-1]["end_ms"] if turns else 0)
    ver = s.get(__import__("ringlark.models", fromlist=["PromptVersion"]).PromptVersion, c.prompt_version_id) if c.prompt_version_id else None
    return {**call_row(c, f"{t.first_name} {t.last_name}".strip() if t else "", s.get(Agent, c.agent_id).name, q), "turns": turns, "duration_ms": dur, "waveform": waveform.build(turns, dur, seed=c.id),
            "prompt_version": ver.version if ver else None, "qa_checks": q.checks if q else {}, "qa_note": q.flag_note if q else "", "followups": [followup_row(f) for f in s.scalars(select(FollowUp).where(FollowUp.call_id == c.id))]}


@router.get("/calls/{call_id}/replay", summary="A recorded call as timed events, for the live console demo")
def replay(call_id: int, s: Session = Depends(db, scope="function")):
    c = s.get(Call, call_id)
    if c is None:
        raise HTTPException(404, "That call does not exist.")
    return {"call_id": c.id, "synthetic_waveform": True, "events": replay_events(c)}


class TransferIn(BaseModel):
    reason: str = Field(default="", max_length=200)


def _is_live(c: Call, ctx: Ctx) -> bool:
    """Only a call that is in progress can be taken over or sent to a person. In demo mode the Live console replays finished calls,
    so there the buttons are a practice run that touches nothing. Outside demo mode a finished call is refused."""
    if c.status == "in_progress":
        return True
    if ctx.settings.demo_mode:
        return False
    raise HTTPException(409, "That call has already ended, so there is nothing to take over.")


@router.post("/calls/{call_id}/take-over", summary="A person takes over the call (owner or approver)")
def take_over(call_id: int, s: Session = Depends(db, scope="function"), ctx: Ctx = Depends(get_ctx), u: dict = Depends(writer)):
    c = s.get(Call, call_id)
    if c is None:
        raise HTTPException(404, "That call does not exist.")
    live = _is_live(c, ctx)
    if live:
        c.taken_over = True
    record_audit(s, u["user"], "call.taken_over" if live else "call.taken_over_practice", f"call:{c.id}", {})
    return {"ok": True, "live": live}


@router.post("/calls/{call_id}/transfer", summary="Send the live call to the agent's human number (owner or approver)")
def transfer(call_id: int, body: TransferIn, s: Session = Depends(db, scope="function"), ctx: Ctx = Depends(get_ctx), u: dict = Depends(writer)):
    from ringlark.tools import ToolService

    c = s.get(Call, call_id)
    if c is None:
        raise HTTPException(404, "That call does not exist.")
    if not _is_live(c, ctx):
        record_audit(s, u["user"], "call.transfer_practice", f"call:{c.id}", {})
        return {"ok": True, "live": False}
    out = ToolService(s, ctx, c).run("transfer_to_human", {"reason": body.reason or f"by {u['user']}"})
    if not out.get("ok"):
        raise HTTPException(409, out.get("say", "The transfer was not done."))
    return {"ok": True, "live": True}


# ---- campaigns and targets
@router.get("/campaigns", summary="Campaigns with target counts")
def campaigns(s: Session = Depends(db, scope="function"), ctx: Ctx = Depends(get_ctx)):
    out = []
    for c in s.scalars(select(Campaign).order_by(Campaign.id)):
        counts = {k: v for k, v in s.execute(select(Target.status, __import__("sqlalchemy").func.count()).where(Target.campaign_id == c.id).group_by(Target.status)).all()}
        out.append({**campaign_row(c), "agent": s.get(Agent, c.agent_id).name, "targets": counts, "calls_today": dialer.calls_today(s, c.id, ctx.now(s), ctx.settings.office_timezone),
                    "timezone_warnings": 0 if ctx.settings.demo_mode else len(intake.timezone_mismatches(s, c.id))})  # the sample demo list is not checked, as at start
    return out


class CampaignIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    agent_id: int
    number_id: int | None = None
    # None means "use the default from settings" (DEFAULT_WINDOW_START, DEFAULT_WINDOW_END, DEFAULT_DAILY_CAP)
    window_start_hour: int | None = Field(default=None, ge=0, le=23)
    window_end_hour: int | None = Field(default=None, ge=1, le=24)
    daily_cap: int | None = Field(default=None, ge=1, le=5000)
    max_attempts: int = Field(default=3, ge=1, le=5)
    retry_gap_days: int = Field(default=1, ge=1, le=14)
    allow_voicemail: bool = False
    voicemail_text: str = Field(default="", max_length=600)
    ivr_policy: str = Field(default="hangup", pattern="^(hangup|press_once)$")
    ivr_extension: str = Field(default="", max_length=4)
    require_prior_consent: bool = True  # True (the default): only people with a granted call consent on file are called. False needs the owner (see create_campaign).


@router.post("/campaigns", summary="Create a campaign (starts as a draft, never running)")
def create_campaign(b: CampaignIn, s: Session = Depends(db, scope="function"), u: dict = Depends(writer), ctx: Ctx = Depends(get_ctx)):
    st = ctx.settings
    values = b.model_dump()
    values["window_start_hour"] = b.window_start_hour if b.window_start_hour is not None else st.default_window_start
    values["window_end_hour"] = b.window_end_hour if b.window_end_hour is not None else st.default_window_end
    values["daily_cap"] = b.daily_cap if b.daily_cap is not None else st.default_daily_cap
    if values["window_end_hour"] <= values["window_start_hour"]:
        raise HTTPException(422, "The calling window must end after it starts.")
    lo, hi = st.window_bounds
    if values["window_start_hour"] < lo or values["window_end_hour"] > hi:
        raise HTTPException(422, f"Calls may only be made between {lo:02d}:00 and {hi:02d}:00 where the person is. The owner can set ALLOW_EXTENDED_HOURS=true to change that.")
    if st.allow_extended_hours and (values["window_start_hour"] < 8 or values["window_end_hour"] > 21):
        record_audit(s, u["user"], "campaign.extended_hours", None, {"start": values["window_start_hour"], "end": values["window_end_hour"]})
    if s.get(Agent, b.agent_id) is None:
        raise HTTPException(404, "That agent does not exist.")
    if b.allow_voicemail and not voicemail_allowed(True, b.voicemail_text)[0]:
        raise HTTPException(422, "A voicemail message must say it is an AI, who is calling and why (for example: \"this is Casey, an AI assistant, calling for Harbor Light Dental about your check up\"). Add that or turn voicemail off.")
    if b.ivr_policy == "press_once" and not re.fullmatch(r"[0-9*#]", b.ivr_extension):
        raise HTTPException(422, "Press once needs the single key to press (0 to 9, star or pound). Choose hang up if there is no such key.")
    if not b.require_prior_consent:
        if u["role"] != "owner":
            raise HTTPException(403, "Only the owner can create a campaign that calls people with no call consent on file.")
        record_audit(s, u["user"], "campaign.consent_not_required", None, {"name": b.name})
    c = Campaign(**values, status="draft")
    s.add(c); s.flush()
    record_audit(s, u["user"], "campaign.created", f"campaign:{c.id}", {"name": c.name})
    return campaign_row(c)


class StartIn(BaseModel):
    acknowledge_timezone_warnings: bool = False  # "I looked at the people whose time zone does not fit their area code" (see GET /campaigns/{id}/timezone-warnings)


def _campaign_action(s: Session, u: dict, cid: int, action: str, ctx: Ctx | None = None, ack: bool = False):
    c = s.get(Campaign, cid)
    if c is None:
        raise HTTPException(404, "That campaign does not exist.")
    if action == "start":
        if u["role"] != "owner":
            raise HTTPException(403, "Only the owner can start a campaign.")
        if not s.get(Agent, c.agent_id).active_version_id:
            raise HTTPException(409, "The agent has no active prompt version.")
        odd = intake.timezone_mismatches(s, c.id) if ctx is not None and not ctx.settings.demo_mode else []  # the sample demo list is not checked
        if odd and not ack:
            raise HTTPException(409, f"{len(odd)} people have a time zone that does not fit the area code of their number (for example {odd[0]['phone']} with {odd[0]['timezone']}). A wrong zone means "
                                     "a call at the wrong hour. Look at them under 'Time zone warnings' (GET /api/campaigns/{id}/timezone-warnings), fix the zones in your list, or start again "
                                     "with acknowledge_timezone_warnings set to true.")
        if odd:
            record_audit(s, u["user"], "campaign.timezone_warnings_acknowledged", f"campaign:{c.id}", {"people": len(odd)})
        c.status = "running"
    else:
        c.status = "paused"
    record_audit(s, u["user"], f"campaign.{action}", f"campaign:{c.id}", {})
    return campaign_row(c)


@router.post("/campaigns/{cid}/start", summary="Start a campaign (owner only). People whose time zone does not fit their area code need acknowledge_timezone_warnings.")
def campaign_start(cid: int, b: StartIn | None = None, s: Session = Depends(db, scope="function"), u: dict = Depends(writer), ctx: Ctx = Depends(get_ctx)):
    return _campaign_action(s, u, cid, "start", ctx, bool(b and b.acknowledge_timezone_warnings))


@router.get("/campaigns/{cid}/timezone-warnings", summary="People whose time zone does not fit the area code of their number")
def timezone_warnings(cid: int, s: Session = Depends(db, scope="function")):
    if s.get(Campaign, cid) is None:
        raise HTTPException(404, "That campaign does not exist.")
    return intake.timezone_mismatches(s, cid)[:500]


class RestoreIn(BaseModel):
    target_ids: list[int] | None = Field(default=None, max_length=5000)  # None: every person who can come back


@router.post("/campaigns/{cid}/targets/restore", summary="Put people who were held back by failed tries back in the list (owner only). Never anyone on the do not call list.")
def restore_targets(cid: int, b: RestoreIn, s: Session = Depends(db, scope="function"), u: dict = Depends(owner)):
    c = s.get(Campaign, cid)
    if c is None:
        raise HTTPException(404, "That campaign does not exist.")
    stmt = select(Target).where(Target.campaign_id == cid, Target.status == "suppressed")
    if b.target_ids is not None:
        stmt = stmt.where(Target.id.in_(b.target_ids))
    restored, skipped = [], {}
    for t in s.scalars(stmt.order_by(Target.id)):
        why = dialer.restore_problem(s, c, t)
        if why:
            skipped[why] = skipped.get(why, 0) + 1
            continue
        t.status = "new"
        restored.append(t.id)
    record_audit(s, u["user"], "targets.restored", f"campaign:{cid}", {"restored": len(restored), "skipped": skipped})
    return {"restored": restored, "skipped": skipped}


@router.post("/campaigns/{cid}/pause", summary="Pause a campaign")
def campaign_pause(cid: int, s: Session = Depends(db, scope="function"), u: dict = Depends(writer)):
    return _campaign_action(s, u, cid, "pause")


@router.get("/campaigns/{cid}/targets", summary="Targets of a campaign, with the reason each one can or cannot be called right now")
def targets(cid: int, s: Session = Depends(db, scope="function"), ctx: Ctx = Depends(get_ctx), limit: int = Query(500, ge=1, le=5000)):
    c = s.get(Campaign, cid)
    if c is None:
        raise HTTPException(404, "That campaign does not exist.")
    agent, now, eff = s.get(Agent, c.agent_id), ctx.now(s), ctx.effective(s)
    today = dialer.calls_today(s, c.id, now, ctx.settings.office_timezone)
    out = []
    for t in s.scalars(select(Target).where(Target.campaign_id == cid).order_by(Target.id).limit(limit)):
        d = dialer.decide(s, eff, c, agent, t, now, today)
        allowed, reason = d.allowed, d.reason
        # The dialer only picks up people who are new, queued or contacted, and only in a running campaign. Say so, so "can be called now" is true.
        if t.status in FINISHED_STATUSES and allowed:
            allowed, reason = False, f"person_{t.status}"
        elif allowed and c.status != "running":
            allowed, reason = False, "campaign_not_running"
        out.append({**target_row(t), "can_call_now": allowed, "why": reason})
    return out


class TargetsIn(BaseModel):
    rows: list[dict] = Field(max_length=5000)


@router.post("/campaigns/{cid}/targets", summary="Import targets (a list of rows with phone and timezone)")
def import_targets(cid: int, b: TargetsIn, s: Session = Depends(db, scope="function"), u: dict = Depends(writer)):
    camp = s.get(Campaign, cid)
    if camp is None:
        raise HTTPException(404, "That campaign does not exist.")
    if camp.status == "running" and u["role"] != "owner":
        # Only the owner starts a campaign, so only the owner may add people to one that is already calling.
        raise HTTPException(403, "Only the owner can add people to a running campaign. Ask the owner, or pause the campaign first.")
    if u["role"] != "owner" and intake.wants_call_consent(b.rows):
        # A call consent is what lets a campaign that requires consent dial a number. It is the owner's statement that the person agreed, so an approver may not make it.
        raise HTTPException(403, "Only the owner can import call consents. Remove the call_consent column, or ask the owner to import this list.")
    rep = intake.import_targets(s, cid, b.rows, actor=u["user"])
    record_audit(s, u["user"], "targets.imported", f"campaign:{cid}", {"created": rep.created, "duplicates": rep.duplicates, "call_consents": rep.consents, "consent_updates": rep.consent_updates})
    return {"created": rep.created, "duplicates": rep.duplicates, "call_consents": rep.consents, "consent_updates": rep.consent_updates, "flagged": rep.flagged, "warnings": rep.warnings[:200]}


# ---- agents and numbers: how a real install gets them (the demo loads them from seed.json)
class AgentIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    kind: str = Field(default="outbound", pattern="^(outbound|inbound)$")
    company: str = Field(default="", max_length=120)  # empty means COMPANY_NAME
    voice: str = Field(default="", max_length=80)
    greeting: str = Field(default="", max_length=600)
    transfer_number: str = Field(default="", max_length=32)
    prompt: str = Field(min_length=40, max_length=20000)  # the first prompt version, see docs/PROMPT-WRITING-GUIDE.md


@router.post("/agents", summary="Create an agent with its first prompt version (owner only). The version is saved, not activated.")
def create_agent(b: AgentIn, s: Session = Depends(db, scope="function"), u: dict = Depends(owner), ctx: Ctx = Depends(get_ctx)):
    if s.scalar(select(Agent.id).where(Agent.name == b.name.strip())):
        raise HTTPException(409, "An agent with that name exists.")
    transfer = normalize_phone(b.transfer_number) if b.transfer_number else ""
    if b.transfer_number and not transfer:
        raise HTTPException(422, "The transfer number needs the country code, for example +14155550100.")
    if b.greeting.strip() and (problems := greeting_problems(b.greeting, ctx.settings.recording_notice_required)):
        raise HTTPException(422, "The greeting is not allowed as written. " + " ".join(problems) + " Leave it empty to use the standard greeting.")
    a = Agent(name=b.name.strip(), kind=b.kind, company=(b.company or ctx.settings.company_name).strip(), voice=b.voice, greeting=b.greeting, transfer_number=transfer)
    s.add(a); s.flush()
    try:
        prompts.add_version(s, a, b.prompt, "First version", u["user"])
    except prompts.PromptError as exc:
        raise HTTPException(422, str(exc)) from exc
    record_audit(s, u["user"], "agent.created", f"agent:{a.id}", {"name": a.name})
    return agent_row(a)


class NumberIn(BaseModel):
    e164: str = Field(max_length=32)
    label: str = Field(default="", max_length=80)
    direction: str = Field(default="both", pattern="^(outbound|inbound|both)$")
    agent_id: int | None = None
    country: str = Field(default="US", min_length=2, max_length=2)


@router.post("/numbers", summary="Add a phone number you own (owner only). Its compliance checklist starts empty.")
def create_number(b: NumberIn, s: Session = Depends(db, scope="function"), u: dict = Depends(owner)):
    e164 = normalize_phone(b.e164)
    if not e164:
        raise HTTPException(422, "Use a full number with the country code, for example +14155550100.")
    if s.scalar(select(Number.id).where(Number.e164 == e164)):
        raise HTTPException(409, "That number is already added.")
    if b.agent_id is not None and s.get(Agent, b.agent_id) is None:
        raise HTTPException(404, "That agent does not exist.")
    n = Number(e164=e164, label=b.label, direction=b.direction, agent_id=b.agent_id, country=b.country.upper(),
               checklist={"caller_id_registered": False, "stir_shaken_attestation": False, "a2p_10dlc_brand": False, "a2p_10dlc_campaign": False, "recording_notice_reviewed": False})
    s.add(n); s.flush()
    record_audit(s, u["user"], "number.added", f"number:{n.id}", {"last4": e164[-4:]})
    return {"id": n.id, "e164": n.e164, "label": n.label, "direction": n.direction, "agent_id": n.agent_id, "country": n.country, "checklist": n.checklist}


def _agent_or_404(s: Session, aid: int) -> Agent:
    a = s.get(Agent, aid)
    if a is None:
        raise HTTPException(404, "That agent does not exist.")
    return a


# ---- agents, prompts, simulator
@router.get("/agents", summary="Agents with every prompt version")
def agents(s: Session = Depends(db, scope="function")):
    return [agent_row(a) for a in s.scalars(select(Agent).order_by(Agent.id))]


class VersionIn(BaseModel):
    body: str = Field(min_length=40, max_length=20000)
    note: str = Field(default="", max_length=200)


@router.post("/agents/{aid}/versions", summary="Save a new prompt version (never edits an old one)")
def add_version(aid: int, b: VersionIn, s: Session = Depends(db, scope="function"), u: dict = Depends(writer)):
    a = _agent_or_404(s, aid)
    try:
        v = prompts.add_version(s, a, b.body, b.note, u["user"])
    except prompts.PromptError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"id": v.id, "version": v.version}


class ActivateIn(BaseModel):
    version_id: int


@router.post("/agents/{aid}/activate", summary="Make a version the one used for new calls (owner only)")
def activate(aid: int, b: ActivateIn, s: Session = Depends(db, scope="function"), u: dict = Depends(owner)):
    a = _agent_or_404(s, aid)
    try:
        prompts.activate(s, a, b.version_id, u["user"])
    except prompts.PromptError as exc:
        raise HTTPException(422, str(exc)) from exc
    return agent_row(a)


class SplitIn(BaseModel):
    candidate_id: int | None = None
    share_b: float = Field(default=0.0, ge=0, le=0.5)


@router.post("/agents/{aid}/split", summary="Send a share of calls to a candidate version (owner only)")
def split(aid: int, b: SplitIn, s: Session = Depends(db, scope="function"), u: dict = Depends(owner)):
    a = _agent_or_404(s, aid)
    try:
        prompts.set_split(s, a, b.candidate_id, b.share_b, u["user"])
    except prompts.PromptError as exc:
        raise HTTPException(422, str(exc)) from exc
    return agent_row(a)


@router.get("/agents/{aid}/diff", summary="Line by line difference between two versions")
def diff(aid: int, a: int, b: int, s: Session = Depends(db, scope="function")):
    ag = _agent_or_404(s, aid)
    by = {v.id: v for v in ag.versions}
    if a not in by or b not in by:
        raise HTTPException(404, "Unknown version.")
    return {"lines": prompts.diff(by[a].body, by[b].body), "flags_a": prompt_flags(by[a].body), "flags_b": prompt_flags(by[b].body)}


@router.get("/personas", summary="The scripted callers of a persona set")
def personas(set: str = Query("dev", pattern="^(dev|heldout|heldout2)$"), ctx: Ctx = Depends(get_ctx)):
    return [{"id": p["id"], "category": p["category"], "title": p.get("title", ""), "caller": p["caller"], "expect": p["expect"], "setup": p.get("setup", {})} for p in load_personas(set, persona_dir(ctx.settings))]


class SimIn(BaseModel):
    version_id: int
    persona_id: str
    set: str = Field(default="dev", pattern="^(dev|heldout|heldout2)$")


@router.post("/agents/{aid}/simulate", summary="Run one scripted caller against a prompt version as text. No voice, no network.")
def simulate(aid: int, b: SimIn, s: Session = Depends(db, scope="function"), ctx: Ctx = Depends(get_ctx), u: dict = Depends(writer)):
    ag = _agent_or_404(s, aid)
    ver = next((v for v in ag.versions if v.id == b.version_id), None)
    per = next((p for p in load_personas(b.set, persona_dir(ctx.settings)) if p["id"] == b.persona_id), None)
    if ver is None or per is None:
        raise HTTPException(404, "Unknown version or persona.")
    from ringlark.personas import check_run

    run = run_persona(per, ver.body, backend_factory=backend_factory(ctx, s, ver.body))
    return {"engine": engine_label(ctx), "transcript": run.transcript, "disposition": run.tools.disposition, "tools": [{"tool": n, "args": a} for n, a in run.tools.calls], "checks": check_run(per, run)}


class SuiteIn(BaseModel):
    version_id: int
    set: str = Field(default="dev", pattern="^(dev|heldout|heldout2)$")


@router.post("/agents/{aid}/persona-suite", summary="Run a whole persona set against a prompt version and score it")
def persona_suite(aid: int, b: SuiteIn, s: Session = Depends(db, scope="function"), ctx: Ctx = Depends(get_ctx), u: dict = Depends(writer)):
    ag = _agent_or_404(s, aid)
    ver = next((v for v in ag.versions if v.id == b.version_id), None)
    if ver is None:
        raise HTTPException(404, "Unknown version.")
    factory = backend_factory(ctx, s, ver.body)
    r = run_suite(load_personas(b.set, persona_dir(ctx.settings)), ver.body, label=f"{ag.name} v{ver.version} on {b.set}", backend_factory=factory, engine=engine_label(ctx))
    note = "Scored by an offline rule based stand in, not a language model." if factory is None else "The checks are code. The caller is scripted. The agent is a model: " + engine_label(ctx) + "."
    return {**{k: v for k, v in r.items() if k != "results"}, "note": note}


# ---- numbers, qa, follow ups, suppressions
@router.get("/numbers", summary="Numbers and their compliance checklist")
def numbers(s: Session = Depends(db, scope="function")):
    return [{"id": n.id, "e164": n.e164, "label": n.label, "direction": n.direction, "agent": s.get(Agent, n.agent_id).name if n.agent_id else "", "country": n.country, "checklist": n.checklist} for n in s.scalars(select(Number))]


class ChecklistIn(BaseModel):
    step: str = Field(pattern="^(caller_id_registered|stir_shaken_attestation|a2p_10dlc_brand|a2p_10dlc_campaign|recording_notice_reviewed)$")
    done: bool


@router.post("/numbers/{nid}/checklist", summary="Tick a compliance step you did with your carrier (owner only). This records your word, it checks nothing with the carrier.")
def checklist(nid: int, b: ChecklistIn, s: Session = Depends(db, scope="function"), u: dict = Depends(owner)):
    n = s.get(Number, nid)
    if n is None:
        raise HTTPException(404, "That number does not exist.")
    n.checklist = {**n.checklist, b.step: b.done}
    record_audit(s, u["user"], "number.checklist", f"number:{n.id}", {"step": b.step, "done": b.done})
    return {"checklist": n.checklist}


@router.get("/qa", summary="Calls queued for a person to read, flagged first")
def qa_queue(show: str = Query("open", pattern="^(open|all)$"), limit: int = Query(200, ge=1, le=1000), offset: int = Query(0, ge=0), s: Session = Depends(db, scope="function")):
    # Paged, because a call held for review that sits beyond the first page could otherwise never be seen, and so never be marked as read, and its person would never be dialled again.
    stmt = select(QAScore).where(QAScore.sampled.is_(True)).order_by(QAScore.flagged.desc(), QAScore.score, QAScore.id.desc())
    if show == "open":
        stmt = stmt.where(QAScore.reviewed.is_(False))
    out = []
    for q in s.scalars(stmt.limit(limit).offset(offset)):
        c = s.get(Call, q.call_id)
        out.append({"call_id": c.id, "score": q.score, "flagged": q.flagged, "note": q.flag_note, "checks": q.checks, "reviewed": q.reviewed, "disposition": c.disposition, "phone": c.peer_phone, "started_at": iso(c.started_at or c.created_at)})
    return out


@router.post("/qa/{call_id}/review", summary="Mark a call as read")
def review(call_id: int, s: Session = Depends(db, scope="function"), u: dict = Depends(writer)):
    q = s.scalar(select(QAScore).where(QAScore.call_id == call_id))
    if q is None:
        raise HTTPException(404, "That call has no score.")
    q.reviewed = True
    record_audit(s, u["user"], "qa.reviewed", f"call:{call_id}", {})
    return {"ok": True}


@router.get("/followups", summary="Follow ups after calls")
def followups(s: Session = Depends(db, scope="function")):
    rows = list(s.scalars(select(FollowUp).order_by(FollowUp.id.desc()).limit(300)))
    people = {call_id: f"{first} {last}".strip() for call_id, first, last in s.execute(select(Call.id, Target.first_name, Target.last_name).join(Target, Target.id == Call.target_id).where(Call.id.in_({f.call_id for f in rows})))} if rows else {}
    return [{**followup_row(f), "name": people.get(f.call_id, "")} for f in rows]


class ResolveIn(BaseModel):
    sent: bool
    note: str = Field(default="", max_length=200)


@router.post("/followups/{fid}/resolve", summary="Say whether a follow up that may or may not have been sent really went out (owner or approver)")
def resolve_followup(fid: int, b: ResolveIn, s: Session = Depends(db, scope="function"), u: dict = Depends(writer)):
    """A follow up whose send ended in a timeout or a server error is held as "send unconfirmed" and never sent again by itself. A person checks with the carrier or the mail
    server and records what happened here. Nothing is sent by this route; it only closes the row (sent, or failed so that a person can write to them by hand)."""
    f = s.get(FollowUp, fid)
    if f is None:
        raise HTTPException(404, "That follow up does not exist.")
    if not (f.status == "sending" or (f.status == "blocked" and f.blocked_reason == "send_unconfirmed")):
        raise HTTPException(409, "Only a follow up whose send could not be confirmed can be resolved.")
    f.status, f.blocked_reason = ("sent", "confirmed by a person") if b.sent else ("failed", "not delivered, confirmed by a person")
    record_audit(s, u["user"], "followup.resolved", f"followup:{f.id}", {"sent": b.sent, "note": b.note})
    return followup_row(f)


@router.get("/suppressions", summary="The do not call list")
def suppressions(s: Session = Depends(db, scope="function")):
    return [{"id": x.id, "phone": x.phone, "reason": x.reason, "source": x.source, "created_at": iso(x.created_at)} for x in s.scalars(select(Suppression).order_by(Suppression.id.desc()).limit(1000))]


class SuppIn(BaseModel):
    phone: str
    reason: str = Field(default="Added by the owner", max_length=80)


class SuppImportIn(BaseModel):
    rows: list[dict] = Field(max_length=5000)  # each row: phone, and an optional reason


@router.post("/suppressions/import", summary="Import a do not call list: rows with a phone and an optional reason")
def import_suppressions(b: SuppImportIn, s: Session = Depends(db, scope="function"), u: dict = Depends(writer)):
    added = skipped = bad = 0
    for r in b.rows:
        phone = str(r.get("phone", "")).strip()
        if not normalize_phone(phone):
            bad += 1
            continue
        if suppression.add_suppression(s, phone, str(r.get("reason") or "Imported list")[:80], "import", actor=u["user"]):
            added += 1
        else:
            skipped += 1
    record_audit(s, u["user"], "suppressions.imported", None, {"added": added, "already_listed": skipped, "bad": bad})
    return {"added": added, "already_listed": skipped, "bad_number": bad}


class RemoveSuppIn(BaseModel):
    note: str = Field(min_length=5, max_length=200)  # why: written to the audit log


@router.post("/suppressions/{sid}/remove", summary="Take a number off the do not call list (owner only, with a reason that is written to the audit log)")
def remove_suppression(sid: int, b: RemoveSuppIn, s: Session = Depends(db, scope="function"), u: dict = Depends(owner)):
    """For a number that was put on the list by mistake, or by someone who spoofed the caller ID and said "do not call". The stop records of the number go too. This grants
    nothing: a campaign that requires prior consent still needs a consent on file before the number is called again."""
    if not suppression.remove_suppression(s, sid, u["user"], b.note):
        raise HTTPException(404, "That entry does not exist.")
    return {"ok": True}


class EraseIn(BaseModel):
    phone: str = Field(max_length=32)
    keep_do_not_call: bool = True  # keep the person on the do not call list as a salted hash (the default: a person who asked to be erased asked to be left alone)


@router.post("/people/erase", summary="Erase one person: their calls, transcripts, summaries, follow ups and list entries (owner only)")
def erase_person(b: EraseIn, s: Session = Depends(db, scope="function"), u: dict = Depends(owner)):
    try:
        return erasure.erase_person(s, b.phone, u["user"], b.keep_do_not_call)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/suppressions", summary="Add a number to the do not call list")
def add_suppression(b: SuppIn, s: Session = Depends(db, scope="function"), u: dict = Depends(writer)):
    if not normalize_phone(b.phone):
        raise HTTPException(422, "Use a full number with the country code, for example +14155550100.")
    added = suppression.add_suppression(s, b.phone, b.reason, "owner", actor=u["user"])
    return {"added": added}
