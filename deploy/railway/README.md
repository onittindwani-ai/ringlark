# Railway

`railway.json` here is for the `api` service. Railway has deprecated this file format (works until 2026-12-01 for existing services, new services cannot opt in), so set the same values in the dashboard. The worker uses the same Dockerfile with start command `python -m ringlark.worker`. The web service uses `apps/web/Dockerfile`. Steps: `docs/07-DEPLOY-RAILWAY.md`. UNVERIFIED: not deployed.
