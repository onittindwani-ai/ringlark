# Run it on your own computer

`01-QUICK-DEMO.md` is the fast version. This is the full one, including real settings and Postgres.

## Install

On Windows use WSL 2 with Ubuntu and run everything inside it. PowerShell and cmd are not supported (the commands below use `.venv/bin/...` paths, `VAR=value command` and `make`). On Ubuntu or Debian (and WSL) install the venv package first: `sudo apt install python3-venv`.

1. Python 3.12 or newer (or uv, which fetches it), Node 22 or newer, pnpm (`corepack enable` or `npm i -g pnpm`). `make install` picks uv or python3.12 for you.
2. `python3.12 -m venv .venv`, or with uv (no Python 3.12 needed first): `uv venv --python 3.12 .venv`
3. `.venv/bin/pip install -c constraints.txt -e packages/core-py -e "apps/api[dev]"`, or with uv: `uv pip install --python .venv/bin/python -c constraints.txt -e packages/core-py -e "apps/api[dev]"` (add `-e "apps/api[postgres]"` if you use Postgres).
4. `pnpm install` then `pnpm build`.

## Settings

`cp .env.example .env`, then follow `04-ENVIRONMENT-VARIABLES.md`. Run `make check-env` (it needs only Python, no install) and then `.venv/bin/python tools/doctor.py`. The first reads your file, the second tests the services. Neither prints a value.

## Database

- **SQLite** (default): tables are created on start. Nothing to do.
- **Postgres**: set `DATABASE_URL=postgresql+psycopg://user:pass@host:5432/dbname` in `.env` (or the environment), then `cd apps/api && ENV_FILE=../../.env ../../.venv/bin/alembic upgrade head`. Alembic reads the same settings as the app (the file named by `ENV_FILE`, default `.env` in the folder you run it from) and stops with an error when `DATABASE_URL` is not set anywhere, instead of migrating a stray SQLite file. Do this on every update.

## Three programs

Run each in its own terminal, from the project folder.

1. **API:** `.venv/bin/python -m uvicorn ringlark.api.app:app_from_env --factory --port 8000 --proxy-headers` (it refuses to start with an example `SESSION_SECRET` when `DEMO_MODE=false`)
2. **Worker** (places due calls, processes ended calls, sends approved follow ups): `.venv/bin/python -m ringlark.worker`
3. **Web:** `pnpm --filter web start` (after `pnpm build`), or `pnpm dev` while you change code.

Open http://localhost:3000.

## Tests

- Python: `.venv/bin/python -m pytest` (<!--n:tests.passed-->458<!--/n--> passed, <!--n:tests.skipped-->1<!--/n--> skipped at the last full run; the skipped one needs a Postgres, set `TEST_POSTGRES_URL`).
- Seed check: `.venv/bin/python tools/score_seed.py` prints one PASS line per planted trap.
- Persona suite score: in the app, Agents and prompts, then Simulator and persona suite. Written up in `PERSONA-SUITE-EVAL.md`.
- Browser tests: `pnpm e2e` (needs Google Chrome; it starts its own API and web server and uses its own throwaway database). It tests the last build, so run `pnpm build` first.

## Stop everything

Press Ctrl+C in each terminal. Data stays in the database.
