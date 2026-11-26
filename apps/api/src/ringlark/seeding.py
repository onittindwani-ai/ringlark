"""Load the seed data into a database. Used by the demo, the tests and tools/score_seed.py."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ringlark import datadir, intake
from ringlark.models import Agent, Call, Campaign, ConsentRecord, Flow, Number, PromptVersion, Target
from ringlark.suppression import add_suppression
from ringlark.util import normalize_phone

DEFAULT_DATA = datadir.CHECKOUT_DATA  # kept for tools/score_seed.py; the code below asks datadir each time


def read_seed(data_dir: Path | None = None) -> dict:
    return json.loads(((data_dir or datadir.CHECKOUT_DATA) / "seed.json").read_text())


def load_seed(session: Session, seed: dict, now: datetime, with_targets: bool = True) -> dict:
    agents: dict[str, Agent] = {}
    for a in seed["agents"]:
        ag = Agent(name=a["name"], kind=a["kind"], company="Harbor Light Dental", voice=a["voice"], voice_source=a["voice_source"], transfer_number=a["transfer_number"], ab_enabled=False)
        session.add(ag)
        session.flush()
        for i, v in enumerate(a["versions"], start=1):
            session.add(PromptVersion(agent_id=ag.id, version=i, body=v["body"], note=v["note"], created_by="seed", created_at=now - timedelta(days=30 - i)))
        session.flush()
        ag.active_version_id = session.scalars(select(PromptVersion).where(PromptVersion.agent_id == ag.id, PromptVersion.version == a["active_version"])).one().id
        session.add(Flow(agent_id=ag.id, name="Check up booking", stages=[{"id": "greet", "goal": "Say who is calling, that it is an AI, and ask if now is okay", "exit_when": "person agrees to talk"},
                                                                       {"id": "offer", "goal": "Offer two times", "exit_when": "person picks one"}, {"id": "book", "goal": "Book and confirm", "exit_when": "book_meeting succeeds"}]))
        agents[a["name"]] = ag
    numbers: dict[str, Number] = {}
    for n in seed["numbers"]:
        num = Number(e164=n["e164"], label=n["label"], direction=n["direction"], agent_id=agents[n["agent"]].id,
                     checklist={"caller_id_registered": False, "stir_shaken_attestation": False, "a2p_10dlc_brand": False, "a2p_10dlc_campaign": False, "recording_notice_reviewed": True})
        session.add(num); numbers[n["e164"]] = num
    session.flush()
    c = seed["campaign"]
    camp = Campaign(name=c["name"], agent_id=agents[c["agent"]].id, number_id=numbers[c["number"]].id, status=c["status"], window_start_hour=c["window_start_hour"], window_end_hour=c["window_end_hour"],
                    daily_cap=c["daily_cap"], max_attempts=c["max_attempts"], retry_gap_days=c["retry_gap_days"], allow_voicemail=c["allow_voicemail"], voicemail_text=c["voicemail_text"], require_prior_consent=bool(c.get("require_prior_consent", False)),  # the fictional demo practice has no consent column to import
                    created_at=now - timedelta(days=10))
    session.add(camp)
    session.flush()
    for s in seed["suppressions"]:
        add_suppression(session, s["phone"], s["reason"], s["source"], actor="seed")
    for k in seed["consent"]:
        session.add(ConsentRecord(phone=k["phone"], kind=k["kind"], status=k["status"], source=k["source"]))
    report = intake.import_targets(session, camp.id, seed["targets"]) if with_targets else None
    if with_targets:
        for a in seed["attempts"]:
            t = session.scalars(select(Target).where(Target.phone == normalize_phone(a["phone"]))).first()
            for d in a.get("days_ago", []):
                session.add(Call(campaign_id=camp.id, target_id=t.id, agent_id=camp.agent_id, peer_phone=t.phone, status="completed", disposition="no_answer", created_at=now - timedelta(days=d), started_at=now - timedelta(days=d)))
            for h in a.get("hours_ago", []):
                session.add(Call(campaign_id=camp.id, target_id=t.id, agent_id=camp.agent_id, peer_phone=t.phone, status="completed", disposition="no_answer", created_at=now - timedelta(hours=h), started_at=now - timedelta(hours=h)))
    session.flush()
    return {"campaign_id": camp.id, "agents": {k: v.id for k, v in agents.items()}, "import": report}
