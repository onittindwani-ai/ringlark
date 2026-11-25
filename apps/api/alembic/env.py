"""Alembic environment. The database URL is read the way the app reads it (environment, then the .env file named by ENV_FILE), or given with -x url=...
It never falls back to a SQLite file by itself: a migration run against the wrong database must fail, not succeed quietly."""

import os

from alembic import context
from sqlalchemy import create_engine

import ringlark.models  # noqa: F401  registers tables
from ringlark.config import Settings
from sendora_core import models as _core  # noqa: F401
from sendora_core.db import Base

target_metadata = Base.metadata


def _url() -> str:
    given = context.get_x_argument(as_dictionary=True).get("url")
    if given:
        return given
    settings = Settings(_env_file=os.environ.get("ENV_FILE", ".env"))
    if "database_url" not in settings.model_fields_set:
        raise RuntimeError("DATABASE_URL is not set in the environment or in the .env file (ENV_FILE), so there is nothing to migrate. Set it, or pass -x url=...")
    return settings.database_url


def run_migrations_online() -> None:
    engine = create_engine(_url())
    with engine.connect() as conn:
        context.configure(connection=conn, target_metadata=target_metadata, render_as_batch=_url().startswith("sqlite"))
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
