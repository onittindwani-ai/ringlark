# Environment variables

An environment variable is a named setting you give the program before it starts, instead of typing it in a file the program ships with. Names are listed here. Never put real values in a file you commit. Copy `.env.example` to `.env` and fill it in. `.env` is ignored by git.

Check your setup any time. `make check-env` (same as `python3 tools/check_env.py`) compares your `.env` with `.env.example` and lists what is missing, still a placeholder, or half filled in (a phone, voice, calendar, CRM or email group you started and did not finish; optional settings such as `SEED_DIR`, a second login or `IMAP_HOST` may stay empty). `.venv/bin/python tools/doctor.py` goes one step further and tests that each service you filled in actually answers. Both print names, never values.

## How to set them

1. Copy the example: `cp .env.example .env`.
2. Edit `.env` in a text editor and fill the values you need.
3. Run the API with `ENV_FILE=.env` (that is the default).
4. On Vercel, Railway or a server, set the same names in that service's settings page instead of a file.

## Core

| Name | What it is | Default |
|---|---|---|
| `DATABASE_URL` | Where data lives. SQLite for trying out, Postgres for real use. | `sqlite:///./ringlark.sqlite3` |
| `SESSION_SECRET` | A long random string (32 or more characters) that signs logins. With `DEMO_MODE=false` the app refuses to start if it is shorter or still an example. Make one: `python -c "import secrets;print(secrets.token_urlsafe(48))"`. Change it and everyone is signed out. | a dev only value |
| `MODE` | `draft` (nothing leaves) or `live` (really calls and texts). | `draft` |
| `DEMO_MODE` | `true` builds only offline adapters and allows the public demo password and the data reset button, but only while `OWNER_PASSWORD_HASH` is empty: setting a hash turns every demo shortcut off. Set `false` for real use. | `true` |
| `ALLOW_DEMO_SERVER` | The app refuses `DEMO_MODE=true` on a Postgres database, because a demo has public logins and a reset button. `true` allows it for a throw away trial. | `false` |
| `APP_NAME` | The name in the API title and health answer. | `ringlark` |
| `MAX_BODY_BYTES` | The most bytes any request may carry (25 MB). Sign in, webhooks and tool calls have much lower limits of their own (8 KB, 1 MB, 20 KB). | `26214400` |
| `HANDOFF_DIR` | Folder for the offline demo mailbox. Docker sets it to a volume. | `./handoff` |
| `KILL_SWITCH` | `true` stops everything at start. | `false` |
| `PUBLIC_BASE_URL` | The public https address of the API. Ultravox reaches the agent tool endpoints there. | empty |
| `SEED_DIR` | Folder with `seed.json` and `personas/`. Set automatically only when run from the repository; an installed copy (the Docker image) must set it, and Docker compose does (`/app/data`). | empty |

## Who the messages come from

Every text and email the system writes on its own names the business. While `COMPANY_NAME` is still the placeholder (and, when emails are on, `COMPANY_ADDRESS` or `EMAIL_FROM`), a real install (`DEMO_MODE=false`) stays in draft mode and the Overview lists the reason.

| Name | What it is | Default |
|---|---|---|
| `COMPANY_NAME` | The business name used in follow up texts and emails and in greetings of agents that have no company of their own. | `Your Company` |
| `COMPANY_ADDRESS` | The postal address printed under every email follow up. Required when `EMAIL_ADAPTER` is not `seed`. | empty |
| `BOOKING_URL` | The page the "booking link" text points to. Empty means that text is not sent outside the demo. | empty |
| `APPOINTMENT_NAME` | What the meeting is called in texts, for example `consultation`. | `appointment` (`check up` in the demo) |

## Sign in (steps)

1. Run `.venv/bin/python tools/hash_password.py` (after `make install` has made the `.venv` folder; plain `python3 tools/hash_password.py` also works when the libraries are installed), or `docker compose run --rm --no-deps api python /app/tools/hash_password.py` on the Docker path. Type a password twice (it is hidden). The tool puts the shared packages on its own path, so it works on a fresh clone; if your plain `python3` lacks the libraries it says so and prints the `.venv/bin/python` command to use.
2. It prints a line like `OWNER_PASSWORD_HASH='...'`. Put that line in `.env`. The quotes matter, because the hash contains `$` characters.
3. Set `OWNER_EMAIL` to your email.
4. Optionally make a second person who can only approve: repeat with `APPROVER_EMAIL` and `APPROVER_PASSWORD_HASH`. For someone who may only look (an accountant, a client who watches), repeat with `VIEWER_EMAIL` and `VIEWER_PASSWORD_HASH`: that login can open every page and change nothing.
5. Set `DEMO_MODE=false`. The demo password stops working. (Even with `DEMO_MODE=true`, a set `OWNER_PASSWORD_HASH` already switches the demo password, the demo accounts and the reset button off.)

## Adapters

| Name | Choices |
|---|---|
| `TELEPHONY_ADAPTER` | `seed`, `telnyx` |
| `VOICE_ADAPTER` | `seed`, `ultravox` |
| `SMS_ADAPTER` | `seed`, `telnyx` |
| `CALENDAR_ADAPTER` | `seed`, `calcom` |
| `CRM_ADAPTER` | `seed`, `twenty` |
| `EMAIL_ADAPTER` | `seed`, `smtp_imap` |

## Per adapter, with exact steps

| Adapter | Names | Where to get them |
|---|---|---|
| telnyx | `TELNYX_API_KEY`, `TELNYX_PUBLIC_KEY`, `TELNYX_CONNECTION_ID`, `TELNYX_FROM_NUMBER`, `TELNYX_BASE_URL` | Telnyx portal: create an API key; find the account public key; create a Call Control application and copy its connection id; buy a number. Menu names UNVERIFIED (`facts/telnyx.md`). |
| ultravox | `ULTRAVOX_API_KEY`, `ULTRAVOX_WEBHOOK_SECRET`, `ULTRAVOX_BASE_URL` | Ultravox console: create an API key; add a webhook and copy its secret (`facts/ultravox.md`). |
| calcom | `CALCOM_API_KEY`, `CALCOM_EVENT_TYPE_ID`, `CALCOM_BASE_URL`, `CALCOM_SLOTS_VERSION`, `CALCOM_BOOKINGS_VERSION` | Cal.com settings: make an API key; open the event type and read its id from the address. Menu names UNVERIFIED. |
| twenty | `TWENTY_BASE_URL`, `TWENTY_API_KEY` | Your Twenty workspace settings, API keys. |
| smtp_imap | `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_USE_TLS`, `IMAP_HOST`, `IMAP_PORT`, `IMAP_USE_SSL`, `EMAIL_FROM` | Your mail provider's settings page. |

Base URLs are checked so a setting cannot point the app at your private network.

## Rules the dialer follows

These are the shipped defaults, decided as a safe starting point. They are not legal advice. Change any of them to your own rules and check them with someone qualified for your country and state.

| Name | What it is | Default |
|---|---|---|
| `DEFAULT_WINDOW_START`, `DEFAULT_WINDOW_END` | Calling hours in the person's own time zone, weekdays only. | 9, 17 |
| `DEFAULT_DAILY_CAP` | Most calls a campaign places in one day. | 50 |
| `FOLLOW_UPS_NEED_APPROVAL` | Follow ups wait for a person. | `true` |
| `HUMAN_TRANSFER_HOURS` | When a person can take a transferred call, in office time. | `09:00-17:00` |
| `OFFICE_TIMEZONE` | Time zone of those hours. It is also where each day starts for the daily cap and for the Overview's "calls today": midnight there, not midnight UTC. | `America/New_York` |
| `SMS_WINDOW_START`, `SMS_WINDOW_END` | Hours for follow up texts, in the person's time zone. | 8, 21 |
| `LOGIN_BURST` | Sign in tries in a row from one address and email before a short wait (one more every 12 seconds). One address trying many accounts gets 4 times this, and one account tried from many addresses gets 2 times. Leave it at 5 outside tests. | `5` |
| `ALLOW_EXTENDED_HOURS` | Campaign calling hours are held to 08:00 to 21:00 in the person's time zone. `true` lets the owner choose wider hours (each such campaign is written to the audit log). | `false` |
| `ALLOWED_CALLING_COUNTRIES` | Country calling codes the dialer may call, comma separated, each written like `+1` or `+44` (a plus sign and one to four digits). An empty value, or one with no readable entry (`1,44`, `US`), allows NO country, so the dialer calls nobody, and the settings page lists the problem; an entry that cannot be read is ignored and listed. Premium rate ranges (US 900 and 976, UK 09 and some international ranges) are never called. `+1` does not let the Caribbean numbers through (area codes 242, 246, 264, 268, 284, 345, 441, 473, 649, 664, 721, 758, 767, 784, 809, 829, 849, 868, 869 and 876), because they are other countries and some are used for one ring call back fraud: allow one by naming its area code, for example `+1,+1876`. Puerto Rico and the other US territories are covered by `+1`. A `+1` number that is not exactly ten digits after the `+1` is refused as a bad number. | `+1` |
| `MAX_INBOUND_CALLS` | Inbound calls answered at the same time. More are hung up on. | `5` |
| `MAX_INBOUND_PER_NUMBER_HOUR` | Inbound calls answered per caller number per hour. | `6` |
| `MAX_INBOUND_ANONYMOUS_HOUR` | Inbound calls answered per hour in all from callers whose number is withheld (no number, a word like "anonymous", or the carriers' placeholder). They share this one limit and do not use up the per number one, so a few private callers cannot lock out the others. Which value Telnyx sends for a withheld number is UNVERIFIED. | `30` |
| `DIAL_FAILURE_LIMIT` | Calls in a row that fail at the phone company or the voice engine before the dialer stops for ten minutes and shows the problem on the Overview. A call that failed before the phone could ring does not count as a try on the person. | `3` |
| `RECORDING_NOTICE_REQUIRED` | While `true`, a custom greeting must say the call may be recorded or transcribed (and always that it is an AI). A greeting without that is refused when the agent is saved, never used on an inbound call (the standard greeting is used) and holds the outbound dialer. Transcripts are always stored, so leave it on unless your own counsel says no notice is needed. | `true` |
| `RETENTION_DAYS` | A daily job deletes the transcripts, summaries and follow up messages of finished calls older than this many days. The call row, its outcome, the number and the do not call and consent records stay. `0` keeps everything for ever. Demo mode never deletes. To remove one person completely, use the erase route in guide 13. | `365` |
| `TOOL_TOKEN_SECRET` | Key for the per call tool tokens (20 minute life). Empty means a key derived from `SESSION_SECRET`. | empty |

New campaigns start with the first three hours and cap values above unless you set their own. The demo campaign uses a cap of 25.

### Rules set on each campaign

These are set when you create a campaign (on the Campaigns page or through the API). The shipped defaults are decided starting points: change them for your client.

| Rule | Default | Plain note |
|---|---|---|
| Voicemail | off | A campaign must turn it on, and the message must say it is an AI, who is calling and why (the app refuses a message that does not). |
| Phone menus (IVR) | hang up | Or `press_once`: press one configured key (0 to 9, star or pound) a single time, then end the call. |
| Tries per person | 3 | The first call plus two retries, never two on the same day in the person's time zone, and at least the retry gap (1 day) apart. |
| Calling hours | 09:00 to 17:00 | The person's local time, weekdays only. A person with an unknown time zone is never called. |
| Daily cap | 50 (25 in the demo) | Most calls the campaign places in one day. |
| Transfers to a person | 09:00 to 17:00 New York time, weekdays | Outside those hours the agent offers a call back instead. Set by `HUMAN_TRANSFER_HOURS` and `OFFICE_TIMEZONE`. |
| Demo phone numbers | `+1 415 555 0100` to `0199` | The range reserved for stories and examples. Never use real numbers in the demo. |

## Reply and summary model

These names are all optional. The model path is off unless you set `LLM_BACKEND=anthropic`; the budgets are the only spend limits for a live model.


| Name | What it is | Default |
|---|---|---|
| `LLM_BACKEND` | `offline` (built in stand in, no account), `fixture` (recorded answers from `LLM_FIXTURES_DIR`) or `anthropic` (real model, needs a key, not yet verified against the real service). Wins over `LLM_MODE`. | `offline` |
| `LLM_MODE` | Older switch: `live` means `anthropic`, anything else means `offline`. | `fixture` |
| `ANTHROPIC_API_KEY` | Only for `anthropic`. Shown once at creation. | empty |
| `ANTHROPIC_BASE_URL` | Where the model API is. Must be `https://` (plain http only for `127.0.0.1` or `localhost` tests). | `https://api.anthropic.com` |
| `ANTHROPIC_VERSION` | The `anthropic-version` header value. | `2026-10-21` |
| `LLM_MODEL` | One model id for both kinds of work. Empty means the two below. | empty |
| `LLM_HARD_MODEL`, `LLM_BULK_MODEL` | Model ids for the agent turns and for reading callers and summaries. | `claude-sonnet-5-5`, `claude-haiku-5-5` |
| `LLM_TIMEOUT` | Seconds one model request may take. | `120` |
| `LLM_MAX_TOKENS` | Reply limit, thinking included. | `4096` |
| `LLM_MAX_RETRIES` | Retries after the first try on rate limits and server errors. | `2` |
| `LLM_CALL_BUDGET` | Most live model calls per process. Empty means no limit. | empty |
| `LLM_BUDGET_USD` | Most tracked spend in US dollars. Empty means no limit. | empty |
| `LLM_THINKING` | `default` or `off`. | `default` |
| `LLM_FIXTURES_DIR` | Folder of recorded answers for `fixture` mode and for `LLM_RECORD`. | empty |
| `LLM_RECORD` | `true` saves every live answer as a fixture. | `false` |
| `LLM_REDACT` | Logs and fixtures never hold a full prompt or a key. | `true` |
| `LLM_LOG_PROMPTS` | Log a redacted, shortened prompt. | `false` |

## Web app only

| Name | What it is |
|---|---|
| `API_BASE_URL` | Where the web app finds the API. Default `http://127.0.0.1:8000`. |
| `INSECURE_COOKIES` | Set `1` only on plain http for local tests. Never in production. |
| `NEXT_PUBLIC_DEMO_HINT` | Set `1` to show the demo sign in hint. Leave empty in production. |
| `WEB_PORT` | Port for the browser tests (default 3000). |
| `POSTGRES_PASSWORD` | Docker compose only. Letters and digits only (or percent-encoded), because it is placed inside the database address. Make one: `openssl rand -hex 24`. |
| `FORWARDED_ALLOW_IPS` | API image only. The addresses uvicorn trusts to say who the visitor is. The image default is `127.0.0.1`; compose widens it to the private network that holds the web container. Never `*` behind a proxy that appends to `X-Forwarded-For`. |
| `ENV_FILE` | Which env file the API, the worker and `alembic` read (default `.env`). |

## The Docker path, in one place

`cp .env.example .env`, then set: `DEMO_MODE=false`; a real `SESSION_SECRET` (32 or more random characters); an `OWNER_PASSWORD_HASH` (with Docker and nothing installed on the host: `docker compose run --rm --no-deps api python /app/tools/hash_password.py`, which uses the API image's own Python; otherwise `.venv/bin/python tools/hash_password.py` after `make install`); a `POSTGRES_PASSWORD` (`openssl rand -hex 24`); `COMPANY_NAME`. Then `docker compose up -d --build`. The API refuses to start with an example secret, or with `DEMO_MODE=true` on Postgres.

## Going live changes four things

`MODE=live`, `DEMO_MODE=false`, a real `OWNER_PASSWORD_HASH`, and a `SESSION_SECRET` you made. `.venv/bin/python tools/doctor.py` lists what is still missing.
