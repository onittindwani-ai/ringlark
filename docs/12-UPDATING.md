# Updating

1. Back up the database (`11`).
2. Read `CHANGELOG.md` for what changed.
3. Pull the new code: `git pull`.
4. Reinstall: `make install`, or `.venv/bin/pip install -e packages/core-py -e "apps/api[dev]"` (with a uv environment: `uv pip install --python .venv/bin/python -e packages/core-py -e "apps/api[dev]"`) and `pnpm install && pnpm build`.
5. Migrate (Postgres): `cd apps/api && ../../.venv/bin/alembic upgrade head`. SQLite creates missing tables on start but does not change old ones, so for SQLite across a schema change, export, start fresh and re-import, or use Postgres.
6. Restart the API, worker and web app.
7. Run `python tools/doctor.py` and open the Audit page.

The shared packages in `packages/` (the base) are versioned separately. Do not edit them in a client install; changes belong upstream.

Settings can be added in an update. `.env.example` lists every name; compare it with your `.env`.
