# Deploy on Railway

**Not tested by me: I did not deploy to Railway.** Railway's own "Config as Code" file (`railway.json`) is deprecated; existing files keep working until 2026-12-01 and new services cannot opt in (see `facts/hosting.md`). So this guide uses dashboard settings. A starting `railway.json` is in `deploy/railway/` in case your account still allows it.

You will make four things in one Railway project: a Postgres database, the API, the worker, and the web app.

1. New project, then **Add Postgres**.
2. **Add service** from your Git repository, named `api`. Settings: Dockerfile path `apps/api/Dockerfile`, root of the repo as the build context. Start command is in the Dockerfile. Health check path `/health`.
3. Variables for `api`: `DATABASE_URL` (use the Postgres reference, and change the start of it to `postgresql+psycopg://`), `SESSION_SECRET`, `MODE=draft`, `DEMO_MODE=false`, `OWNER_EMAIL`, `OWNER_PASSWORD_HASH`, `PUBLIC_BASE_URL` (the API's public address), and the adapter choices (see `04`).
4. Run migrations once: in the `api` service shell, `alembic upgrade head`. The Dockerfile start command also runs it on boot.
5. **Add service** again, named `worker`, same Dockerfile and same variables, start command `python -m ringlark.worker`. No public address needed.
6. **Add service**, named `web`, Dockerfile path `apps/web/Dockerfile`. Variable `API_BASE_URL` set to the API's private address (Railway shows it as `api.railway.internal` plus port).
7. Give `web` a public domain. Give `api` a public domain too, only so Telnyx and Ultravox can reach it (the webhooks and the agent tool endpoints).
8. Sign in, run `python tools/doctor.py` in the `api` shell.

Keep `MODE=draft` until `09-GO-LIVE-CHECKLIST.md` is finished.
