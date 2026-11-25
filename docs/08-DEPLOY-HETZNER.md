# Deploy on a Hetzner server

**Not tested by me: I did not create a Hetzner server.** The files in `deploy/hetzner/` are written from Hetzner's public docs (see `facts/hosting.md`) and checked only for valid YAML and shell syntax. One small server runs everything with Docker Compose and Caddy (which gets a free HTTPS certificate for you).

## Steps

1. In Hetzner Cloud make a server (a small one is enough to start; Ubuntu LTS). Add your SSH key while creating it, since you cannot add it later without a rebuild.
2. Add a firewall allowing only ports 22, 80 and 443.
3. Point two DNS names at the server's address: one for the web app (`app.yourdomain.com`) and one for the API (`api.yourdomain.com`). The API name is for Telnyx and Ultravox only: the Caddyfile forwards just `/api/webhooks/*` and `/api/tools/*` on it and answers 404 for everything else, so the sign in and the data routes are reachable only through the web app. Set `PUBLIC_BASE_URL` to `https://api.yourdomain.com`.
4. Optional: paste `deploy/hetzner/cloud-init.yaml` into the "Cloud config" box when creating the server. It installs Docker and Caddy. It holds **no secrets**; do not add any.
5. Log in with SSH. Clone your repository to `/opt/ringlark`.
6. `cp .env.example .env` and fill it in (see `04`, "The Docker path"): `DEMO_MODE=false`, a `SESSION_SECRET` of 32 or more random characters, an `OWNER_PASSWORD_HASH`, a `POSTGRES_PASSWORD` of letters and digits only (`openssl rand -hex 24`), and `COMPANY_NAME`. The API refuses to start if these are not safe. Set the two DNS names in `deploy/hetzner/Caddyfile`.
7. `docker compose up -d --build`. Then `docker compose exec api alembic upgrade head`.
8. Copy `deploy/hetzner/Caddyfile` to `/etc/caddy/Caddyfile` and `sudo systemctl reload caddy`.
9. Open the web address and sign in.

## Backups

`deploy/hetzner/backup.sh` writes a compressed Postgres dump to `/var/backups/ringlark`. Run it daily with cron: `0 3 * * * /opt/ringlark/deploy/hetzner/backup.sh`. Also turn on Hetzner server backups. Test a restore (see `11`) before you need it.
