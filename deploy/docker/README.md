# Docker

`docker-compose.yml` at the repository root starts Postgres, the API, the worker and the web app. Follow `docs/08-DEPLOY-HETZNER.md` (it uses this file). Ports are bound to 127.0.0.1, so put a reverse proxy (Caddy, see `deploy/hetzner/Caddyfile`) in front for HTTPS.

Status: the compose file passes `docker compose config` and YAML parsing. The images were never built (no Docker daemon in the build environment), so the Dockerfiles are UNVERIFIED. `pnpm build` (which the web image runs) was run and passes.
