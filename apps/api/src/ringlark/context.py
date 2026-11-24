"""Runtime context shared by the API and the worker: settings, database, adapters, model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from ringlark import clock
from ringlark.config import Settings
from ringlark.models import State
from ringlark.offline_llm import OfflineBackend
from ringlark.registry import AdapterSet, build_adapters, build_registry
from sendora_core.costs import CostTracker
from sendora_core.llm import LLM, build_llm
from sendora_core.settings import Mode


@dataclass
class Ctx:
    settings: Settings
    factory: sessionmaker[Session]
    adapters: AdapterSet | Any = None
    registry: Any = None

    def __post_init__(self) -> None:
        self.registry = self.registry or build_registry(self.settings)
        if self.adapters is None:
            self.adapters = build_adapters(self.settings, self.registry)

    def effective(self, session: Session) -> Settings:
        """The kill switch can be turned on in the app, and the mode can be pulled back to draft. Neither can go the other way."""
        kill, force = session.get(State, "kill_switch"), session.get(State, "force_draft")
        upd: dict[str, Any] = {}
        if kill and kill.value == "1":
            upd["kill_switch"] = True
        if force and force.value == "1":
            upd["mode"] = Mode.DRAFT
        return self.settings.model_copy(update=upd) if upd else self.settings

    def now(self, session: Session):
        return clock.now(session, self.settings.demo_mode)

    def llm(self, session: Session) -> LLM:
        # LLM_BACKEND=offline (default) | fixture | anthropic. The offline stand in is the zero account default.
        # The anthropic path is UNVERIFIED against the real service.
        return build_llm(self.effective(session), CostTracker(session), offline=OfflineBackend())


def set_state(session: Session, key: str, value: str) -> None:
    row = session.get(State, key)
    if row is None:
        session.add(State(key=key, value=value))
    else:
        row.value = value
