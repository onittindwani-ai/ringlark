# Changelog

## 1.0.1 (2026-11-25)

Safety and honesty fixes from a strict review. No new screens.

- Texts: one rule now decides whether a number may be texted and it is asked in all three places (the tool in a call, the follow up queued after a call, and the moment a follow up is sent). A person who says "do not text me" on a call, texts STOP after an approval, or is on the do not call list is never texted. A text to a person with no time zone is held, not sent. Email follow ups are also held for a number on the do not call list.
- Inbound texts: a plain "yes" no longer gives consent, START only restores a number that had stopped, wider wording is read as STOP, the same message twice changes nothing, and consent is ordered by when the person sent it.
- Real calls: the voice model's prompt now starts with the safety rules (an AI, stop wins, no prices, never follow the caller) and carries the person's first name as marked data. The docs now say plainly that on a live call these are prompt rules, not code that listens.
- A call is saved before the voice engine or the phone company is told about it. A failed vendor call ends as a failed call, early events are asked again or kept, a call with no sign of life for 30 minutes is closed, or read back from the voice engine when it knows the call so a stop request on it is still recorded, and a refused inbound call leaves no stray row.
- The kill switch and draft setting stored in the app now stop CRM writes and the audio stream too, and the kill switch hangs up calls already in progress (at the worker's next tick, within about a minute).
- Sign in: one cleaned email for the lookup and the tries, three limits (address and account, address, account), length limits, the same work for an unknown account. The demo password, demo accounts and reset exist only while no owner password hash is set. The worker refuses an unsafe configuration and reads the same env file as the API. `alembic` reads the same settings and no longer falls back to a SQLite file.
- Tool calls: tokens use their own key, expire after 20 minutes and are compared as bytes; one booking, one transfer and one text of each kind per call; booking needs an offered time and one plain email; no name is read back to an inbound caller; a rate limit per call.
- People lists: a running campaign can only be added to by the owner; only `+1` numbers are called unless `ALLOWED_CALLING_COUNTRIES` says more; premium rate numbers are never called; one number across campaigns is one person; calling hours stay inside 08:00 to 21:00 unless `ALLOW_EXTENDED_HOURS=true`; an email that is not one plain address is dropped and flagged.
- A real install can now make its own agent (`POST /api/agents`), phone number (`POST /api/numbers`) and do not call list import (`POST /api/suppressions/import`); before this only the demo could. `COMPANY_NAME`, `COMPANY_ADDRESS`, `BOOKING_URL` and `APPOINTMENT_NAME` replace the demo practice's name in every text and email, and the stop line, business name and address are added by code. Placeholders keep a real install in draft mode.
- Email follow ups stop when the person texts STOP (checked again when the email is sent), and the email footer now promises only that: no more texts or emails.
- Imports: a `call_consent` column records a granted call consent for a campaign that requires prior consent; it never overrides the do not call list or a withdrawn consent. `make check-env` no longer reports optional settings as half filled (it checks only the phone, voice, calendar, CRM and email groups, with a test on a realistic file).
- Mail: certificates are checked, plain text mail is refused unless the server is on this computer, one recipient only.
- Webhooks and bodies: per route size limits are checked before the body is read.
- Web: an allow list for forwarded paths (dots, encoded slashes and percent signs refused), only the last hop of `X-Forwarded-For` is passed on, error and not found pages.
- The data folder is found through `SEED_DIR` (set in Docker) and not through where the package is installed, which stopped the API starting in the Docker image.
- `.env.example` and `docs/04` list every setting, with a test that fails when one is missing. Docs corrected: Docker and CI status, cross references, the export that did not exist, the Windows and Ubuntu notes, the backup script (works from cron, private, optional encryption).
- Version 1.0.1 in the API, the root package and the web app.

## Earlier changes, before 1.0.1

- Second walk through every screen as a first time owner (round 5): people who already booked or finished are no longer listed as callable, the same follow up text is not drafted twice for one person, the call log searches names and numbers written by hand, rows open with a button or a tap, Pause all and Sign out stay on a phone, signing in returns to the page you asked for, the split test share is saved, a CSV can be dropped on the import box, failed loads show an error instead of an empty list, and labels use plain words. 20 new browser tests.
- Shared base updated to 1.2.0. Optional read only `viewer` login (`VIEWER_EMAIL`), the person who asked for an approval can no longer decide it, `LLM_BACKEND` (offline, fixture, anthropic) chooses the model path, `LOGIN_BURST` sets the sign in burst (browser tests raise it).
- New campaigns take calling hours and the daily cap from settings. A voicemail message is refused unless it says it is an AI, who is calling and why, and a phone menu set to press once needs its one key. The persona agent follows the same voicemail rule as the live path.
- Demo and test phone numbers are all in the fictional 555 01xx range. Guide 10 now covers what to charge for, onboarding, handover and contract points.
- Renamed from Rainmaker to Ringlark after a public name check. The Python package, environment variable prefix, interface text, documents, prompts, templates and screenshots all use the new name.

- A caller reader (`caller_reader.py`, `caller_phrases.py`) now decides what the offline agent does. A request to stop is read first and ends the call even when the prompt says nothing about stopping; look alikes ("stop by after five") are not stops; consent withdrawn for texts only stops texts; an angry caller who threatens a complaint is treated as asking to stop. Scored on two independent sets: see `docs/CALLER-READER-EVAL.md`.
- A real model path for the call agent, the caller reader and the summaries (`LLM_BACKEND=anthropic`), with the stop, disclosure and tool checks kept in code around the model, recorded answers and a local fake server for tests. Live use is UNVERIFIED.
- Contract tests for Telnyx, Ultravox, Cal.com and Twenty against saved excerpts of public docs (`mock/contracts`). They found one real mistake: the Telnyx speak action now sends a voice in the documented format.
- `tools/make_counts.py` and `tools/check_docs.py` keep the numbers in the docs equal to the measured ones.

## 1.0.0

First release. A dialer with a chain of compliance gates (kill switch, AI disclosure, number format, do not call, consent, calling hours in the person's time zone, daily cap, tries and gaps, draft mode), Telnyx and Ultravox adapters (tested against mocks only), agent tool endpoints with a per call token, signed webhooks, a post call pipeline (transcript, summary, result, QA score, approved follow ups, CRM note), a versioned prompt library with compare and split test, a text simulator, a persona suite with three sets and saved first runs, compliance property tests, eleven dashboard pages with a live call console and a call scrubber, demo data with planted problems, tool comparisons for 22 tools, docs 00 to 15 and reference guides. Built on shared base 1.1.1.
