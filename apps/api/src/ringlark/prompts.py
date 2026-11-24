"""The versioned prompt library: every change is a new version, a version is activated on purpose, and a split test sends a share of calls to a candidate."""

from __future__ import annotations

import difflib
import hashlib

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ringlark.models import Agent, PromptVersion
from sendora_core.audit import record_audit


class PromptError(ValueError):
    pass


def add_version(session: Session, agent: Agent, body: str, note: str = "", created_by: str = "system") -> PromptVersion:
    body = (body or "").strip()
    if len(body) < 40:
        raise PromptError("A prompt needs at least a few sentences (40 characters).")
    if len(body) > 20000:
        raise PromptError("A prompt may be at most 20,000 characters.")
    last = session.scalar(select(func.max(PromptVersion.version)).where(PromptVersion.agent_id == agent.id)) or 0
    v = PromptVersion(agent_id=agent.id, version=last + 1, body=body, note=note[:200], created_by=created_by)
    session.add(v)
    session.flush()
    record_audit(session, created_by, "prompt.version_added", f"agent:{agent.id}", {"version": v.version})
    return v


def activate(session: Session, agent: Agent, version_id: int, actor: str = "system") -> PromptVersion:
    v = session.get(PromptVersion, version_id)
    if v is None or v.agent_id != agent.id:
        raise PromptError("That version does not belong to this agent.")
    agent.active_version_id = v.id
    if agent.candidate_version_id == v.id:
        agent.candidate_version_id, agent.ab_enabled, agent.ab_share_b = None, False, 0.0
    record_audit(session, actor, "prompt.activated", f"agent:{agent.id}", {"version": v.version})
    return v


def set_split(session: Session, agent: Agent, candidate_id: int | None, share_b: float, actor: str = "system") -> None:
    if candidate_id is None or share_b <= 0:
        agent.candidate_version_id, agent.ab_enabled, agent.ab_share_b = None, False, 0.0
    else:
        v = session.get(PromptVersion, candidate_id)
        if v is None or v.agent_id != agent.id:
            raise PromptError("That version does not belong to this agent.")
        if v.id == agent.active_version_id:
            raise PromptError("The candidate must be a different version from the active one.")
        if not 0 < share_b <= 0.5:
            raise PromptError("The candidate may take between 1 and 50 percent of calls.")
        agent.candidate_version_id, agent.ab_enabled, agent.ab_share_b = v.id, True, share_b
    record_audit(session, actor, "prompt.split_set", f"agent:{agent.id}", {"candidate": candidate_id, "share": share_b})


def choose_version(agent: Agent, call_key: str) -> int | None:
    """A or B for one call, decided by a stable hash so the same call key always gets the same answer."""
    if agent.ab_enabled and agent.candidate_version_id and agent.ab_share_b > 0:
        h = int(hashlib.sha256(f"{agent.id}:{call_key}".encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
        if h < agent.ab_share_b:
            return agent.candidate_version_id
    return agent.active_version_id


def diff(old: str, new: str) -> list[dict]:
    """Line by line difference, ready to draw: kind is same, add or del."""
    out = []
    for line in difflib.ndiff((old or "").splitlines(), (new or "").splitlines()):
        tag, text = line[:2], line[2:]
        if tag == "? ":
            continue
        out.append({"kind": {"  ": "same", "+ ": "add", "- ": "del"}[tag], "text": text})
    return out
