# Architecture

Ringlark has one API, one worker and one web app, on top of a frozen shared base (version 1.2.3) that holds settings, safe write guards, the audit chain, approvals, jobs, rate limits and the UI kit.

```
Browser  ->  Next.js web app  ->  /api proxy  ->  FastAPI API  ->  SQLite or Postgres
                                                   ^   ^
        Telnyx webhooks (Ed25519) -----------------+   +---- Ultravox webhooks (HMAC)
        Ultravox agent tool calls (per call token) -----+
Worker: dial tick, post call, follow ups, CRM sync, report
```

## The call, step by step

1. **Dial tick (worker).** For each running campaign, `dialer.decide` runs the pure rules in `compliance.evaluate` for each due person: kill switch, AI disclosure in the greeting, E.164 number, do not call list, consent, time zone known, calling window in the person's own time zone, a call already in flight, daily cap, max tries, same day retry, gap between tries, draft mode. The first rule that says no is saved as the reason and shown in the campaign table and on the Overview.
2. **Place the call.** If every rule says yes and the mode is live, the app first saves the call (status `placing`) and commits it. Only then does it create the Ultravox call (the hard rules, your prompt, six tools, a per call token that expires) and let Telnyx dial and carry the audio. The call becomes `placed`; a failure at either vendor ends it as `failed` and the tick carries on. A call that shows no sign of life for 30 minutes is closed. In demo mode the offline adapters play a scripted call instead.
3. **During the call.** Ultravox runs the conversation and calls the tool endpoints (`/api/tools/{call}/{tool}`): book a meeting, look up the CRM, transfer to a person, send a text, press a key in a phone menu, end the call with a result code. Each tool checks the per call token (one call, 20 minutes), checks the live kill switch and draft state, enforces its own caps (one booking, one transfer, one text of each kind per call) and writes to the audit log.
4. **Events.** Telnyx and Ultravox send signed webhooks. A bad, old or missing signature is refused. Events are stored as turns.
5. **After the call (post call job).** Transcript, summary, result code, a QA score, follow up texts or emails (waiting for approval), a CRM note, and updates to the do not call list or consent when the person asked.

## The Telnyx to Ultravox bridge (UNVERIFIED)

The most likely place to need a fix on first real use. Ringlark creates the Ultravox call with a Telnyx medium, dials with Call Control, answers, and uses `streaming_start` to point the call audio at the Ultravox join address. The action paths were written by symmetry with the documented transfer action. The documented alternative is a TeXML application whose answer document connects the call to the stream. If the join fails, switch to that, or ask Claude Code to write it from `docs/facts/telnyx.md`.

## The offline agent

For the demo, the simulator and the persona suite, `agent_offline.py` is a set of rules that reads directives from your prompt text (stop when asked, admit it is an AI, transfer when asked, no prices, never leak the instructions, hang up at a menu, take a call back time, keep turns short). It is labelled as rules, not a language model, everywhere. `agent_live.py` is a real model path (`LLM_BACKEND=anthropic`), written as one turn at a time in a fixed JSON shape with the stop, consent, disclosure and tool checks kept in code around it (`model_tasks.py` holds the prompts and schemas). It has run only against a local fake server and recorded answers, never against the real service: UNVERIFIED. `caller_reader.py` reads every caller turn first in the simulator, the persona suite and the model path, so a request to stop always wins there. On a real Ultravox call the same rules are written into the voice model's prompt (`live_prompt.py`) and nothing in this code listens to the call: the stop request is found in the transcript afterwards (`postcall.py`) and the number goes on the do not call list.

## Safe writes

Every write that leaves the system (a call, a text, an email, a calendar booking, a CRM write, a transfer, a key press) goes through `sendora_core.guard_write` with the effective settings. The in app kill switch and force draft state are stored in the database and read at write time, so a button press stops adapters that started with other settings.

## Data

Tables are prefixed `rm_`: State, Agent, PromptVersion, Flow, Number, Target, Campaign, Call, Turn, Disposition, QAScore, FollowUp, ConsentRecord, Suppression, plus the shared base tables for audit, approvals and jobs. Migrations are in `apps/api/alembic`. The OpenAPI file is `docs/openapi.json` (47 paths).

## Web

Next.js 16 App Router. Pages call the API through a proxy that keeps the session cookie httpOnly and adds the CSRF header, and forwards only an allow list of API paths (no webhooks, tool calls or sign in). The live console and the call log scrubber share one `CallPlayer` component (synthetic waveform from the turn times, streaming transcript, agent state, speed 1x and 4x).

## Decisions

See `docs/DESIGN-NOTES.md` for the design choices and `docs/SPEC.md` for the scope.
