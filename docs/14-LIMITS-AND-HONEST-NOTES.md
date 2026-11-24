# Limits and honest notes

Read this before you trust Ringlark with real people. Everything here was run on the date shown (2026-11-23) unless it says UNVERIFIED.

## What was run

- <!--n:tests.passed-->236<!--/n--> Python tests pass and <!--n:tests.skipped-->1<!--/n--> is skipped (the Postgres cycle, which needs `TEST_POSTGRES_URL`). Line coverage of the `ringlark` package is <!--n:tests.coverage_percent-->87<!--/n--> percent (`pytest --cov=ringlark`). The weakest files are `worker.py` (41 percent) and `followups.py` (54 percent). <!--n:contract_tests-->12<!--/n--> contract tests check the adapters against saved excerpts of the vendors' public docs.
- Compliance property tests make thousands of random worlds and check that the dialer never calls outside the person's hours, never calls a do not call or revoked consent number, never goes over the cap, and never places a call without the AI disclosure. They run on the pure rules and on the real database path.
- Browser tests (Playwright, Chrome) run the whole demo path, axe accessibility checks on all 11 pages in light and dark with zero serious or critical findings, keyboard use, reduced motion, 5,000 call rows, layout shift, console errors, and 8 screenshots states at 1440 by 900 and 390 by 844.
- `tools/score_seed.py`: all 7 planted problem types are held back (19 rows).
- Migrations: up, down and up again on SQLite with no drift. The same cycle also passed on Postgres 17.7 in a throwaway local cluster (`TEST_POSTGRES_URL`). The rest of the app was not run against Postgres by an automated test.

## What was NOT run (UNVERIFIED)

- **Any real Telnyx, Ultravox, Cal.com or Twenty account.** The adapters are tested against local copies written from the public docs.
- **The Telnyx to Ultravox bridge.** Ringlark creates the Ultravox call with a Telnyx medium, dials with Telnyx Call Control, and joins the audio with a `streaming_start` action. The action paths for answer, streaming_start, speak, send_dtmf and hangup were written by symmetry with the documented ones. If the join does not work on your first test call, the documented alternative is a TeXML application that connects the call to the stream. This is the most likely thing to need a fix.
- **The shape of Ultravox tool parameters** (`staticParameters`) and the Ultravox messages path.
- **The Telnyx signed string for call events** (`timestamp|body`, as the vendor libraries do).
- **Docker images and every deploy guide.** There was no Docker daemon, so `docker build` was never run. The compose file, Caddyfile and cloud-init were checked for valid syntax only.
- **A language model on a real call.** The agent in the demo and in the persona suite is a set of rules that reads directives from your prompt text, and it is labelled "offline rules, not a language model" on every screen. A real model path exists (`LLM_BACKEND=anthropic`, see "The live model path" below). It has run only against a local fake of the Anthropic endpoint (request shape, schema, guards) and against recordings made from that fake. It has never been run with a real key, so how a real model behaves on a call is UNVERIFIED.
- **How a voice sounds.** Nobody who built this can hear. Voice quality is for you to judge on a real test call.

## The live model path (UNVERIFIED live)

What is built and tested without an account (`apps/api/tests/test_model_path.py`, 22 tests):

- The model plays the agent one turn at a time and answers in a fixed JSON shape (what to say, which of the six tools). The greeting with the AI disclosure is written by code, never by the model.
- What the person says is passed in as marked data. Words that look like the markers cannot close the block.
- Rules run around the model and cannot be talked out of it: a request to stop, a withdrawn consent, a machine or a phone menu are handled by the rules with no model call. A claim to be a person is replaced with the disclosure, a machine question always gets an honest answer, no price, no link, no leak of the instructions. A booking must use an offered time and a name, a text is dropped after a withdrawn consent, a key press must be the configured key and only once, and "booked" is not accepted without a real booking.
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
- No call recording or audio storage. The waveform in the screens is generated from turn times and says so.
- English only in the prompts and persona suite.
- SQLite is fine to try. Use Postgres for real use.
