"""Shared test helpers for the API tests. They live here, not in conftest.py, because the shared core tests have a conftest.py of their own and
`from conftest import ...` would pick the wrong one when both folders are collected in one run."""

from datetime import UTC, datetime
from pathlib import Path

from ringlark.config import Settings

DATA = Path(__file__).resolve().parents[3] / "data"
# A Tuesday, 17:00 UTC: 12:00 New York, 09:00 Los Angeles (open), 17:00 London and 22:30 Kolkata (closed).
NOW = datetime(2026, 12, 1, 17, 0, tzinfo=UTC)


def make_settings(tmp_path, **kw) -> Settings:
    base = dict(database_url=f"sqlite:///{tmp_path / 'rm.sqlite3'}", mode="live", demo_mode=True, handoff_dir=str(tmp_path / "handoff"), seed_dir=str(DATA), session_secret="test-only-secret-test-only-secret-1")
    base.update(kw)
    return Settings(_env_file=None, **base)
