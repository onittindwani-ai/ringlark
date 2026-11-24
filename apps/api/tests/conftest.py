import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from ringlark.config import Settings
from ringlark.context import Ctx
from ringlark.seeding import load_seed, read_seed
from sendora_core import models as _core  # noqa: F401
from sendora_core.db import Base, make_engine, make_session_factory

DATA = Path(__file__).resolve().parents[3] / "data"
# A Tuesday, 17:00 UTC: 12:00 New York, 09:00 Los Angeles (open), 17:00 London and 22:30 Kolkata (closed).
NOW = datetime(2026, 12, 1, 17, 0, tzinfo=UTC)


def make_settings(tmp_path, **kw) -> Settings:
    base = dict(database_url=f"sqlite:///{tmp_path / 'rm.sqlite3'}", mode="live", demo_mode=True, handoff_dir=str(tmp_path / "handoff"), seed_dir=str(DATA), session_secret="test-only-secret-test-only-secret-1")
    base.update(kw)
    return Settings(_env_file=None, **base)


@pytest.fixture
def settings(tmp_path):
    return make_settings(tmp_path)


@pytest.fixture
def factory(settings):
    engine = make_engine(settings.database_url)
    Base.metadata.create_all(engine)
    return make_session_factory(engine)


@pytest.fixture
def ctx(factory, settings):
    return Ctx(settings, factory)


@pytest.fixture
def session(factory):
    with factory() as s:
        yield s


@pytest.fixture
def seeded(session: Session):
    seed = read_seed(DATA)
    info = load_seed(session, seed, NOW)
    session.commit()
    return {"seed": seed, "info": info, "key": json.loads((DATA / "answer_key.json").read_text())}
