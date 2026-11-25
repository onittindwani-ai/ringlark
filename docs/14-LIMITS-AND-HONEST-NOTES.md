# Limits and honest notes

Read this before you trust Ringlark with real people. Everything here was run on the date shown (2026-11-23) unless it says UNVERIFIED. The Python test and coverage numbers were measured again on 2026-11-25 for version 1.0.1 (that run included the SQLite migration cycle). The Postgres migration cycle was skipped in that run (no `TEST_POSTGRES_URL`) and the browser tests were not run again either.

## What was run

- <!--n:tests.passed-->416<!--/n--> Python tests pass (that includes the 81 tests of the shared core package, which `pytest.ini` now collects) and <!--n:tests.skipped-->1<!--/n--> is skipped (the Postgres cycle, which needs `TEST_POSTGRES_URL`). Line coverage of the `ringlark` package is <!--n:tests.coverage_percent-->91<!--/n--> percent (`pytest --cov=ringlark`). The weakest files are `worker.py` (49 percent) and `adapters/smtp_imap.py` (57 percent). <!--n:contract_tests-->12<!--/n--> contract tests check the adapters against saved excerpts of the vendors' public docs.
- Compliance property tests make thousands of random worlds and check that the dialer never calls outside the person's hours, never calls a do not call or revoked consent number, never goes over the cap, and never places a call without the AI disclosure. They run on the pure rules and on the real database path.
- Browser tests (Playwright, Chrome) run the whole demo path, axe accessibility checks on all 11 pages in light and dark with zero serious or critical findings, keyboard use, reduced motion, 5,000 call rows, layout shift, console errors, and 8 screenshots states at 1440 by 900 and 390 by 844.
- `tools/score_seed.py`: all 7 planted problem types are held back (19 rows).
- Migrations: up, down and up again on SQLite with no drift. The same cycle also passed on Postgres 17.7 in a throwaway local cluster (`TEST_POSTGRES_URL`). The rest of the app was not run against Postgres by an automated test.

## What was NOT run (UNVERIFIED)

- **Any real Telnyx, Ultravox, Cal.com or Twenty account.** The adapters are tested against local copies written from the public docs.
- **The Telnyx to Ultravox bridge.** Ringlark creates the Ultravox call with a Telnyx medium, dials with Telnyx Call Control, and joins the audio with a `streaming_start` action. The action paths for answer, streaming_start, speak, send_dtmf and hangup were written by symmetry with the documented ones. If the join does not work on your first test call, the documented alternative is a TeXML application that connects the call to the stream. This is the most likely thing to need a fix.
- **The shape of Ultravox tool parameters** (`staticParameters`) and the Ultravox messages path.
- **The Telnyx signed string for call events** (`timestamp|body`, as the vendor libraries do).
- **A real deployment.** The CI workflow in `.github/workflows/ci.yml` builds both Docker images and starts the compose stack on a GitHub runner, then checks that the API and the web sign in page answer. No deployment to a real host (Hetzner, Railway or Vercel) was done, and the three hosting guides were not followed on a real account. The Caddyfile and cloud-init were checked for valid syntax only.
- **A language model on a real call.** The agent in the demo and in the persona suite is a set of rules that reads directives from your prompt text, and it is labelled "offline rules, not a language model" on every screen. A real model path exists (`LLM_BACKEND=anthropic`, see "The live model path" below). It has run only against a local fake of the Anthropic endpoint (request shape, schema, guards) and against recordings made from that fake. It has never been run with a real key, so how a real model behaves on a call is UNVERIFIED.
- **How a voice sounds.** Nobody who built this can hear. Voice quality is for you to judge on a real test call.

## The live model path (UNVERIFIED live)

What is built and tested without an account (`apps/api/tests/test_model_path.py`, 22 tests):

- The model plays the agent one turn at a time and answers in a fixed JSON shape (what to say, which of the six tools). The greeting with the AI disclosure is written by code, never by the model.
- What the person says is passed in as marked data. Words that look like the markers cannot close the block.
- Rules run around the model and cannot be talked out of it: a request to stop, a withdrawn consent, a machine or a phone menu are handled by the rules with no model call. A claim to be a person is replaced with the disclosure, a machine question always gets an honest answer, no price, no link, no leak of the instructions. A booking must use an offered time and a name, a text is dropped after a withdrawn consent, a key press must be the configured key and only once, and "booked" is not accepted without a real booking (the same check is in the end call tool, so it holds on a real voice call too, not only on the text path).
- There is no tool for placing a call, so no caller can make the agent dial anyone. A bad answer (wrong shape, unknown tool, unknown outcome code), the kill switch or an used up budget ends the call politely and marks it "needs review".
- Call summaries and the weekly summary go through the same wrapper; a summary with a number that was not in the facts is replaced by a plain one. The persona suite scorer is code, not a model: with a model agent, the caller is still scripted and the checks are still code.

What is not known: whether a real model keeps to these rules over a long, messy call, how it handles interruptions and silence, how long each turn takes (a voice call needs fast turns, and a model turn through a text path is not the Ultravox voice loop), and what it costs per call. The recorded answers in `data/llm_fixtures` were made from the fake server answering with the offline rules, so they show the replay path works, not how good a model is. The independent held out numbers in `CALLER-READER-EVAL.md` are for the offline rules only. When you have a key, run the same tool with a model reader before you trust one.

## The persona suite is not a model score

Dev set 14 of 14 (tuned against, so it proves little). Held out set 1: first run 12 of 14, then tuned, so no longer held out. Held out set 2: first run 7 of 14, not tuned at the time; the current code scores 14 of 14 on it after later reader changes, so it is spent too. The first runs are saved in `data/eval/`. Read `PERSONA-SUITE-EVAL.md`.

## Not legal advice

Rules for AI voices, consent, recording, calling hours and texting depend on place. `US-CALLING-CHECKLIST.md` lists what Ringlark does and what it cannot do for you.

## Shipped defaults you can change

These rules were decided as a safe starting point. They are not legal advice and your client may need different ones. Voicemail is off unless a campaign enables it with a message that says it is an AI, who is calling and why. Phone menus: hang up, or press one configured key once. 3 tries per person on different days, 09:00 to 17:00 in the person's time zone, weekdays, daily cap 50 (25 in the demo). Transfers 09:00 to 17:00 New York time, weekdays. Demo numbers are in the fictional 555 01xx range. Change any of them in the settings listed in `04-ENVIRONMENT-VARIABLES.md`.

## Other limits

- One campaign dials at a time per tick. It is a small dialer, not a call center.
- On a live call the rules are in the voice model's prompt, not in code that listens (see `13`). The tool side and the after call checks are code. A person can be kept on the line by a model that ignores its prompt until the call ends and the transcript is read.
- No email is read back: there is no inbox reader. A person who wants to stop email follow ups texts STOP (checked again at the moment an email is sent) or says so on a call (they go on the do not call list, which also stops emails). The email footer promises exactly that and no more: a STOP text ends texts and emails, it does not by itself put the number on the do not call list for calls.
- A call saved before ringing that shows no sign of life for 30 minutes is settled by the dial tick. If the voice engine knows it (it has an Ultravox id) it is moved to in progress and its transcript is read back, so a stop request said on it is still recorded; if it never reached the voice engine it is marked failed. Either way its attempt counts, so nobody is called twice by accident. The Ultravox call made for a crashed attempt is not cancelled (the adapter has no cancel).
- There is no unique database rule on (person, attempt). The in flight check and the saved row before ringing prevent a double dial, but a second worker started by mistake is not stopped by the database.
- An inbound caller's number is whatever caller ID says, and caller ID can be faked. Inbound calls are capped (`MAX_INBOUND_CALLS`, `MAX_INBOUND_PER_NUMBER_HOUR`) and the agent never reads a name back to them; an inbound caller has no time zone on file, so the app never texts one (no text is sent without a known local time, whatever the caller replied).
- No call recording or audio storage. The waveform in the screens is generated from turn times and says so.
- English only in the prompts and persona suite.
- The code that looks for a request to stop in a call transcript is a set of patterns and missed 9 of 24 and 6 of 21 must-stop lines on its first runs (see `13` and `CALLER-READER-EVAL.md`). A call that ends as needs review holds the person until someone has read it, which is a person doing the check the code cannot. Whether Ultravox returns the transcript right away when a call ends is UNVERIFIED: an empty one is read again for about 3 minutes and then flagged for a person.
- A booking that times out at Cal.com may or may not have been saved. The agent is told someone will follow up, the call is flagged, and it is not booked a second time on that call, so check the calendar for it.
- The Docker images and Postgres are named by a floating tag (`python:3.12-slim`, `node:22-slim`, `postgres:17`), so a rebuild can pull a newer image. Pin them by digest at release time if you need the same bytes every time. Docker on the Hetzner server comes from the Ubuntu package archive (`docker.io`, `docker-compose-v2`); the cloud-init was written that way but no server was created to try it.
- The web app sends a content security policy (same site only, no framing, no plugins) that still allows inline scripts, because Next.js needs them without a nonce setup. It was not run in a browser here, so the browser tests in CI are the first real check.
- SQLite is fine to try. Use Postgres for real use.
