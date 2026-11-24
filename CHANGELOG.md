# Changelog

## Unreleased

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
