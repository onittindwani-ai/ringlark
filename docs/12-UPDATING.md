# Updating

1. Back up the database (`11`).
2. Read `CHANGELOG.md` for what changed.
3. Pull the new code: `git pull`.
4. Reinstall: `make install`, or `.venv/bin/pip install -c constraints.txt -e packages/core-py -e "apps/api[dev]"` (with a uv environment: `uv pip install --python .venv/bin/python -c constraints.txt -e packages/core-py -e "apps/api[dev]"`) and `pnpm install && pnpm build`.
5. Migrate (Postgres): `cd apps/api && ../../.venv/bin/alembic upgrade head`. SQLite creates missing tables on start but does not change old ones, so for SQLite across a schema change use Postgres, or start a fresh database and import your lists again (there is no export button: keep your own copies of the CSV files you imported).
6. Restart the API, worker and web app.
7. Run `python tools/doctor.py` and open the Audit page.

The shared packages in `packages/` (the base) are versioned separately. Do not edit them in a client install; changes belong upstream.

Settings can be added in an update. `.env.example` lists every name (a test fails when a setting is missing from it or from `04`); compare it with your `.env`, or run `make check-env`.

## Pinned packages

`constraints.txt` pins every third party Python package to the version the tests ran against, so an install today gives the same set as the one that was tested (`make install`, the Docker image and CI all use it). After a deliberate upgrade of a package, install the new version, run the tests, then change that line of `constraints.txt` to the version you tested.
