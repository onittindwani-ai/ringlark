"""Demo mode: fill the history, play the conversations of placed calls offline, move the clock, replay a call as a live stream.

Everything here uses fictional people and the offline stand in agent. It places no real call.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ringlark import clock
from ringlark.agent_offline import OfflineAgent
from ringlark.datadir import persona_dir
from ringlark.models import Agent, Call, Campaign, PromptVersion, Target
from ringlark.personas import DEFAULT_CTX, load_personas
from ringlark.postcall import process_call, store_turns
from ringlark.seeding import load_seed, read_seed
from ringlark.tools import ToolService
from sendora_core.events import record_event

def demo_start(real_now: datetime) -> datetime:
    """The next weekday at 17:00 UTC: lunchtime in New York and morning in Los Angeles, so some people can be called and some must wait."""
    t = real_now.astimezone(UTC).replace(hour=17, minute=0, second=0, microsecond=0)
    if t <= real_now:
        t += timedelta(days=1)
    while t.weekday() >= 5:
        t += timedelta(days=1)
    return t


def _slots(ctx, session: Session, now: datetime) -> tuple[list[str], dict[str, datetime]]:
    got = ctx.adapters.calendar.slots(now, now + timedelta(days=7))[:2]
    labels = {f"{d.strftime('%A')} at {d.strftime('%-I %p').lower()}": d for d in got}
    return list(labels), labels


def play_call(session: Session, ctx, call: Call, persona: dict) -> None:
    """Run one persona against the call's agent prompt, through the real tool code, and store the turns."""
    now = ctx.now(session)
    labels, slot_map = _slots(ctx, session, now)
    version = session.get(PromptVersion, call.prompt_version_id or session.get(Agent, call.agent_id).active_version_id)
    cmp = session.get(Campaign, call.campaign_id) if call.campaign_id else None
    setup = persona.get("setup", {})
    c = {**DEFAULT_CTX, "slots": labels or DEFAULT_CTX["slots"], "allow_voicemail": bool(cmp and cmp.allow_voicemail and setup.get("answered_by") == "machine") or setup.get("campaign_allows_voicemail", False),
         "voicemail_text": (cmp.voicemail_text if cmp else "") or setup.get("voicemail_text", ""), "ivr_policy": cmp.ivr_policy if cmp else "hangup"}
    tools = ToolService(session, ctx, call, slot_map)
    agent = OfflineAgent(version.body if version else "", c, tools)
    pairs: list[tuple[str, str]] = []

    def play(turns):
        for t in turns:
            if t.text:
                pairs.append(("agent", t.text))
            if t.tool:
                tools.run(t.tool, t.args)

    lines = list(persona["caller"])
    if setup.get("answered_by") in ("machine", "ivr"):
        pairs.append(("caller", lines[0]))
        first = agent.first_contact(lines[0])
        if first is not None:
            play(first)
            lines = []
        call.answered_by = setup["answered_by"]
    else:
        call.answered_by = "human"
        play(agent.open())
    for line in lines:
        if agent.done:
            break
        pairs.append(("caller", line))
        play(agent.reply(line))
    if not agent.done and lines:
        pairs.append(("caller", "Okay, bye."))
        play(agent.reply("Okay, bye."))
    call.disclosure_played = True
    store_turns(session, call, pairs)
    call.status = "in_progress"
    session.flush()


def simulate_placed(session: Session, ctx) -> int:
    """After the dialer placed calls, let the fictional people answer. Each target has a persona that decides how the call goes."""
    personas = {p["id"]: p for p in load_personas("dev", persona_dir(ctx.settings))}
    n = 0
    for call in session.scalars(select(Call).where(Call.status == "placed", Call.direction == "outbound").order_by(Call.id)):
        t = session.get(Target, call.target_id) if call.target_id else None
        p = personas.get(t.demo_persona if t else "", personas["D13"])
        play_call(session, ctx, call, p)
        n += 1
    return n


def reset(session: Session, ctx) -> dict:
    from sendora_core.db import Base

    session.rollback()
    session.close()
    # Empty the tables and load the seed in ONE transaction. Dropping and recreating the tables left a moment with no tables,
    # and any page that refreshed during it (the live stream does this on every event) got a 500 "no such table".
    with ctx.factory() as s:
        for table in reversed(Base.metadata.sorted_tables):
            s.execute(table.delete())
        start = demo_start(datetime.now(UTC))
        clock.set_offset(s, (start - datetime.now(UTC)).total_seconds() / 3600)
        s.flush()
        now = clock.now(s, True)
        info = load_seed(s, read_seed(Path(ctx.settings.seed_dir) if ctx.settings.seed_dir else None), now)
        seed_history(s, ctx, info, now)
        s.commit()
        return {"targets_imported": info["import"].created, "clock": now.isoformat()}


def seed_history(session: Session, ctx, info: dict, now: datetime) -> int:
    """Past calls for the call log, QA review and metrics: the dev personas, played on earlier days, through the real post call code."""
    seed = read_seed(Path(ctx.settings.seed_dir) if ctx.settings.seed_dir else None)
    personas = {p["id"]: p for p in load_personas("dev", persona_dir(ctx.settings))}
    camp = session.get(Campaign, info["campaign_id"])
    targets = list(session.scalars(select(Target).where(Target.campaign_id == camp.id, Target.status == "new").order_by(Target.id)))
    agent = session.get(Agent, camp.agent_id)
    n = 0
    for i, h in enumerate(seed["history"]):
        t = targets[(i * 2 + 1) % len(targets)] if targets else None
        when = now - timedelta(days=h["days_ago"], hours=3 + i % 5)
        call = Call(campaign_id=camp.id, target_id=t.id if t else None, agent_id=agent.id, prompt_version_id=agent.active_version_id if h["days_ago"] <= 14 else None, direction="outbound",
                    peer_phone=t.phone if t else "+14155550100", status="placed", started_at=when, created_at=when)
        session.add(call); session.flush()
        play_call(session, ctx, call, personas[h["persona"]])
        process_call(session, ctx, call)
        call.created_at = when
        n += 1
    return n


def replay_events(call: Call) -> list[dict]:
    """A recorded call as a stream of timed events, for the live console. The browser plays it back at real speed."""
    ev: list[dict] = [{"t": 0, "type": "state", "state": "ringing"}, {"t": 700, "type": "state", "state": "connected"}]
    for t in call.turns:
        if not t.text:
            continue
        who = "speaking" if t.speaker == "agent" else "listening"
        ev.append({"t": t.start_ms, "type": "state", "state": who if t.speaker == "agent" else "listening"})
        words = t.text.split()
        span = max(t.end_ms - t.start_ms, 1)
        for i, w in enumerate(words):
            ev.append({"t": t.start_ms + int(span * i / max(len(words), 1)), "type": "word", "speaker": t.speaker, "turn": t.position, "word": w})
        if t.tool:
            ev.append({"t": t.end_ms, "type": "tool", "tool": t.tool})
    end = call.turns[-1].end_ms if call.turns else 1500
    ev.append({"t": end + 400, "type": "state", "state": "ended", "disposition": call.disposition})
    return sorted(ev, key=lambda e: e["t"])
