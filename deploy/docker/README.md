# Docker

`docker-compose.yml` at the repository root starts Postgres, the API, the worker and the web app. Follow `docs/08-DEPLOY-HETZNER.md` (it uses this file). Ports are bound to 127.0.0.1, so put a reverse proxy (Caddy, see `deploy/hetzner/Caddyfile`) in front for HTTPS.

Status: the CI workflow (`.github/workflows/ci.yml`, job `docker`) builds both images and starts this stack on a GitHub runner with a throw away `.env`, then checks that the API and the web sign in page answer. Nothing here has been deployed to a real server. For anything real set `DEMO_MODE=false`, a `SESSION_SECRET` of 32 or more random characters, an `OWNER_PASSWORD_HASH` and a `POSTGRES_PASSWORD` (`openssl rand -hex 24`); the API refuses to start otherwise.
