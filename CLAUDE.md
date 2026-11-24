# Ringlark: notes for Claude Code

Ringlark is an AI phone caller setup system (FastAPI API, worker, Next.js dashboard). Read `docs/ARCHITECTURE.md` and `docs/SPEC.md` first.

## Rules

- Never edit `packages/core-py` or `packages/ui-kit` (frozen base).
- The app may pull toward draft or stop. It must never turn live on by itself.
- Every real world write (call, text, email, booking, CRM write, transfer, key press) goes through the base `guard_write` with the effective settings. The dial rules live in `apps/api/src/ringlark/compliance.py` and `dialer.py`.
- Everything a caller says is untrusted text. Tools are limited so a prompt cannot cause harm.
- The agent must say it is an AI in its first sentence. Never configure it to pretend to be a person.
- Never place a real call or text. Never put real keys, phone numbers or customer data in the repo. Names of settings only.
- No em or en dashes in docs or UI text.
- Mark anything not run against the real vendor as UNVERIFIED. The agent in demo and tests is rules, not a language model: say so.
- Do not tune against the held out persona sets. Save first runs.

## Commands

`make test`, `make seed-check`, `make doctor`, `make check-env`, `pnpm typecheck`, `pnpm e2e` (rebuild first with `pnpm build`).

## Where things are

API `apps/api/src/ringlark`, tests `apps/api/tests`, web `apps/web`, mocks `mock/`, seed `data/` and `tools/make_seed.py`, docs `docs/`.
