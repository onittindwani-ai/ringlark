import json

import pytest
from sqlalchemy.orm import Session

from ringlark.context import Ctx
from ringlark.seeding import load_seed, read_seed
from sendora_core import models as _core  # noqa: F401
from sendora_core.db import Base, make_engine, make_session_factory
from testkit import DATA, NOW, make_settings  # noqa: F401  (re-exported for the tests that import it from here)


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
