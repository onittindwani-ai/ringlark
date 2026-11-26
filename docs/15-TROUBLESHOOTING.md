# Troubleshooting

Run `make check-env` first (it lists missing or half filled settings, names only), then `.venv/bin/python tools/doctor.py` (it tests each service you set up). Both name the problem in plain words.

| What you see | Likely cause | Fix |
|---|---|---|
| Sign in says wrong email or password | Demo password used with `DEMO_MODE=false`, or hash pasted without quotes | Use your own password. Put `OWNER_PASSWORD_HASH='...'` in single quotes. |
| Everything says 401 after a restart | `SESSION_SECRET` changed | Sign in again. |
| 429 too many requests | Behind a proxy without `--proxy-headers` | Start uvicorn with `--proxy-headers` and set `FORWARDED_ALLOW_IPS=<proxy address>` (the Docker image reads that variable). |
| No calls are placed | Draft mode (also forced when `PUBLIC_BASE_URL`, `TELNYX_PUBLIC_KEY` or `ULTRAVOX_WEBHOOK_SECRET` is missing on a live install), kill switch, outside calling hours, weekend, daily cap, or no consent | Check the top strip, then the Overview held back list and the campaign table. |
| One person is never called | Bad number, unknown time zone, do not call, no consent on file (the import had no `call_consent` yes), revoked consent, duplicate, too many tries, or their last call needs a look and nobody has marked it as read on the QA page | Open the campaign table, read the reason. |
| The Overview says calls are not being placed, or "Resting after repeated failures" | `DIAL_FAILURE_LIMIT` (3) calls in a row failed at the voice engine or Telnyx, so the dialer stopped for ten minutes | Open Integrations and press Test on the phone and voice rows, fix the key or the account, and wait: it goes on by itself and clears the message with the first call that goes through. People who failed to be reached were not used up. If an older build had marked people "suppressed" by an outage, the owner puts them back with `POST /api/campaigns/<id>/targets/restore` (guide 14). |
| The agent offers no times or books the wrong hour | Cal.com could not be reached when the call started, or the times were not copied exactly | The prompt then tells the model to use the tool `list_times`; check the Cal.com key and event type on Integrations, and read the call's transcript. Open times are said in the person's time zone and passed with their UTC offset. |
| The call connects but nobody hears the agent | The Telnyx to Ultravox join (never run live here) | See `14`. Check the Telnyx webhook log and the Ultravox call log. Try the TeXML alternative. |
| Agent tools fail during a call | `PUBLIC_BASE_URL` wrong or not https | Set it to the API's public address. Ultravox must reach `/api/tools/...`. |
| Webhook rejected | Wrong secret, wrong key, or old timestamp | Check `ULTRAVOX_WEBHOOK_SECRET`, `TELNYX_PUBLIC_KEY` and the server clock. |
| Doctor says FAIL for an adapter | Missing variable or wrong host | It names the variable. |
| Browser tests show old pages | `next start` serves the last build | Run `pnpm build`, then the tests. |
| Port 3000 in use | Another program | Set `WEB_PORT=3100` for the tests, `-p` for the app. |
| "database is locked" on SQLite | Two heavy writers | Use Postgres. |
| Alembic error on Postgres | Wrong URL form | Use `postgresql+psycopg://`. |
| Web build cannot find the ui kit | Vercel root settings | See `06` step 4. |
| Page looks unstyled | Web not built | `pnpm build` then start again. |
| Demo shows no calls | Clock not moved | Press **Run now**, **+1 day**, **Run now**. |

Still stuck: open an issue (see `CONTRIBUTING.md`) with the doctor output. Never paste real keys or real phone numbers.
