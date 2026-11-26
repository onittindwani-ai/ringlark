"""Bring an existing SQLite file up to date at start, for the zero setup path. `create_all` makes missing tables but never adds a column or an index to a table that
already exists, so a database file made by an older version would fail with "no such column" or stay slow. Postgres installs use `alembic upgrade head` instead
(migration 0002). Everything here is safe to run again and does nothing on other databases."""

from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from sendora_core.db import Base

ADDED_COLUMNS = (("rm_consent", "note", "VARCHAR(300) NOT NULL DEFAULT ''"),)  # columns added after release 1.0.0


def upgrade_sqlite(engine: Engine) -> list[str]:
    """Create missing tables, add the columns in ADDED_COLUMNS and create the indexes the models declare. Returns what it did, for the log and the tests."""
    if engine.dialect.name != "sqlite":
        return []
    done: list[str] = []
    Base.metadata.create_all(engine)
    insp = inspect(engine)
    with engine.begin() as conn:
        for table, column, ddl in ADDED_COLUMNS:
            if insp.has_table(table) and column not in {c["name"] for c in insp.get_columns(table)}:
                conn.execute(text(f'ALTER TABLE "{table}" ADD COLUMN "{column}" {ddl}'))
                done.append(f"{table}.{column}")
    insp = inspect(engine)
    for table in Base.metadata.sorted_tables:
        have = {i["name"] for i in insp.get_indexes(table.name)}
        for index in table.indexes:
            if index.name and index.name not in have:
                index.create(engine, checkfirst=True)
                done.append(f"index {index.name}")
    return done
