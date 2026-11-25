# Contributing

1. Fork, branch, make a small change.
2. Run `make test` and `make seed-check`. Both must pass. For web changes also `pnpm typecheck` and, after `pnpm build`, `pnpm e2e`.
3. Do not edit `packages/core-py` or `packages/ui-kit`; they are a frozen shared base.
4. Use plain words in docs and UI text. No em or en dashes.
5. Commit messages: `type: what the change delivers`, for example `fix: hold back a number with a bad time zone`.
6. Never commit keys, real phone numbers, real customer data or `.env`.
7. Do not tune the agent rules against the held out persona sets. Add a new set instead and save its first run.

Setup: `make install` (see `docs/05-RUN-LOCALLY.md`; on Windows use WSL 2 with Ubuntu). A test fails when a setting is missing from `.env.example` or `docs/04-ENVIRONMENT-VARIABLES.md`, so add it to both.

Issues: describe what you did, what you expected and what happened. Paste `python tools/doctor.py` output (it prints no secrets).
