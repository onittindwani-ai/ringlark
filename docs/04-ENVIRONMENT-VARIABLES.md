# Environment variables

An environment variable is a named setting you give the program before it starts, instead of typing it in a file the program ships with. Names are listed here. Never put real values in a file you commit. Copy `.env.example` to `.env` and fill it in. `.env` is ignored by git.

Check your setup any time. `make check-env` (same as `python3 tools/check_env.py`) compares your `.env` with `.env.example` and lists what is missing, still a placeholder, or half filled in. `python tools/doctor.py` goes one step further and tests that each service you filled in actually answers. Both print names, never values.

## How to set them

1. Copy the example: `cp .env.example .env`.
2. Edit `.env` in a text editor and fill the values you need.
3. Run the API with `ENV_FILE=.env` (that is the default).
4. On Vercel, Railway or a server, set the same names in that service's settings page instead of a file.

## Core

| Name | What it is | Default |
|---|---|---|
| `DATABASE_URL` | Where data lives. SQLite for trying out, Postgres for real use. | `sqlite:///./ringlark.sqlite3` |
| `SESSION_SECRET` | A long random string that signs logins and per call tool tokens. Make one: `python -c "import secrets;print(secrets.token_urlsafe(48))"`. Change it and everyone is signed out. | a dev only value |
| `MODE` | `draft` (nothing leaves) or `live` (really calls and texts). | `draft` |
| `DEMO_MODE` | `true` builds only offline adapters and allows the demo password. Set `false` for real use. | `true` |
| `KILL_SWITCH` | `true` stops everything at start. | `false` |
| `PUBLIC_BASE_URL` | The public https address of the API. Ultravox reaches the agent tool endpoints there. | empty |
| `SEED_DIR` | Folder with the demo data. Set automatically when run from the repo. | empty |

## Sign in (steps)

1. Run `python tools/hash_password.py`. Type a password twice (it is hidden).
2. It prints a line like `OWNER_PASSWORD_HASH='...'`. Put that line in `.env`. The quotes matter, because the hash contains `$` characters.
3. Set `OWNER_EMAIL` to your email.
4. Optionally make a second person who can only approve: repeat with `APPROVER_EMAIL` and `APPROVER_PASSWORD_HASH`. For someone who may only look (an accountant, a client who watches), repeat with `VIEWER_EMAIL` and `VIEWER_PASSWORD_HASH`: that login can open every page and change nothing.
5. Set `DEMO_MODE=false`. The demo password stops working.

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
| calcom | `CALCOM_API_KEY`, `CALCOM_EVENT_TYPE_ID`, `CALCOM_WEBHOOK_SECRET`, `CALCOM_BASE_URL`, `CALCOM_SLOTS_VERSION`, `CALCOM_BOOKINGS_VERSION` | Cal.com settings: make an API key; open the event type and read its id from the address. Menu names UNVERIFIED. |
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
| `OFFICE_TIMEZONE` | Time zone of those hours. | `America/New_York` |
| `SMS_WINDOW_START`, `SMS_WINDOW_END` | Hours for follow up texts, in the person's time zone. | 8, 21 |
| `LOGIN_BURST` | Sign in tries in a row from one address and email before a short wait (one more every 12 seconds). Leave it at 5 outside tests. | `5` |

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
| Demo phone numbers | `+1 415 555 0100` to `0199` | The fictional range reserved for stories and examples. Never use real numbers in the demo. |

## Reply and summary model

| Name | What it is | Default |
|---|---|---|
| `LLM_BACKEND` | `offline` (built in stand in, no account), `fixture` (recorded answers from `LLM_FIXTURES_DIR`) or `anthropic` (real model, needs a key, not yet verified against the real service). Wins over `LLM_MODE`. | `offline` |
| `LLM_MODE` | Older switch: `live` means `anthropic`, anything else means `offline`. | `fixture` |
| `ANTHROPIC_API_KEY` | Only for `anthropic`. Shown once at creation. | empty |

## Web app only

| Name | What it is |
|---|---|
| `API_BASE_URL` | Where the web app finds the API. Default `http://127.0.0.1:8000`. |
| `INSECURE_COOKIES` | Set `1` only on plain http for local tests. Never in production. |
| `NEXT_PUBLIC_DEMO_HINT` | Set `1` to show the demo sign in hint. Leave empty in production. |
| `WEB_PORT` | Port for the browser tests (default 3000). |
| `POSTGRES_PASSWORD` | Docker compose only. |

## Going live changes four things

`MODE=live`, `DEMO_MODE=false`, a real `OWNER_PASSWORD_HASH`, and a `SESSION_SECRET` you made. `python tools/doctor.py` lists what is still missing.
