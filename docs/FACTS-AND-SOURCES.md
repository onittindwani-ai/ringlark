# Facts and sources

Every outside fact this project relies on, with where it came from and when it was checked (2026-11-22 and 2026-11-23). **VERIFIED** means a public page or a package registry said it on that date. **UNVERIFIED** means a third party said it, sources disagreed, or it could not be found. Nothing here was tested against a real account. Vendors change things, so check the page before you rely on a fact. One file per vendor is in `docs/facts/`.

| Fact | Status | Source |
|---|---|---|
| Ultravox creates a call with `POST /api/calls`, header `X-API-Key`, body `systemPrompt`, `voice`, `selectedTools`, `medium`, `maxDuration`; reply has `callId` and `joinUrl` | VERIFIED | https://docs.ultravox.ai/api-reference/calls/calls-post |
| Ultravox signs webhooks with HMAC SHA256 of body plus timestamp, headers `X-Ultravox-Webhook-Timestamp` and `X-Ultravox-Webhook-Signature`, about 1 minute tolerance | VERIFIED | https://docs.ultravox.ai/webhooks/securing-webhooks.md |
| Ultravox has built in voices, cloning and an external voice option | VERIFIED | https://docs.ultravox.ai/voices/overview.md |
| Ultravox tool parameter shape (`staticParameters`) and the messages path | UNVERIFIED | Not shown in the pages read |
| A Telnyx call joins an Ultravox call through a `streaming_start` action | UNVERIFIED | Written from the docs by symmetry; a TeXML connect to the stream is the documented alternative |
| Telnyx sends a text with `POST /v2/messages` and places a call with `POST /v2/calls` | VERIFIED | https://developers.telnyx.com |
| Telnyx signs webhooks with Ed25519 over `timestamp|body`; 5 minute tolerance | VERIFIED for messages, UNVERIFIED for call events | https://developers.telnyx.com |
| Telnyx call action paths and fields for streaming_start, speak (voice as Provider.Model.VoiceId), send_dtmf and transfer; machine detection event `call.machine.detection.ended` with `data.payload.result` | VERIFIED (pages read 2026-11-23) | https://developers.telnyx.com/api-reference/call-commands/dial and the streaming-start, send-dtmf, speak-text, transfer-call pages |
| Telnyx answer and hangup action paths | UNVERIFIED | Hangup page returned 404; answer not read |
| Where the Telnyx public key and connection id live in the portal | UNVERIFIED | A third party guide |
| Cal.com books with `POST /v2/bookings`, header `cal-api-version: 2026-02-25` | VERIFIED | https://cal.com/docs/api-reference/v2 |
| Cal.com slots version header, webhook signature, key location | UNVERIFIED | Sources disagree or were third party |
| Twenty CRM takes GraphQL at `/graphql` with a Bearer key | VERIFIED (shape) | https://docs.twenty.com |
| Twenty field names for people and notes | UNVERIFIED | Introspection can be turned off for API keys |
| The FCC ruled in February 2024 that AI generated voices count as artificial voices under the US TCPA, so calls with them need prior express consent | VERIFIED from law firm summaries, not from the ruling itself | https://www.cooley.com/news/insight/2024/2024-02-15-fcc-ai-generated-robocalls-illegal-under-the-tcpa and https://www.wiley.law/alert-FCC-Extends-Regulatory-Reach-Over-AI-Announces-TCPA-Restrictions-Cover-AI-Generated-Voices-in-Outbound-Calls |
| Statutory damages under the TCPA are $500 per call, up to $1,500 if willful | VERIFIED from law firm summaries | same sources |
| Vercel can build a monorepo app from `apps/web` with "Include source files outside of the Root Directory" | VERIFIED | https://vercel.com/docs |
| Railway "Config as Code" is deprecated, existing files work until 2026-12-01 | VERIFIED | https://docs.railway.com |
| Hetzner cloud-init user data starts with `#cloud-config` | VERIFIED | https://docs.hetzner.com |
| Hetzner firewall and SSH key details | UNVERIFIED | Official pages were thin |
| Next.js 16 uses `proxy.ts` instead of middleware | VERIFIED | https://nextjs.org/docs (page updated 2026-11-18) |
| Library versions: next 16.4.6, react 19.3.1, @tanstack/react-query 5.108.2, @playwright/test 1.65.1, fastapi 0.165.0, alembic 1.20.1, cryptography 50.0.2 | VERIFIED | npm and PyPI registries, 2026-11-22 |

## What is measured here, not looked up

The seed counts, test counts, coverage and persona suite scores come from running this repo. They are in `data/counts.json`, `docs/14-LIMITS-AND-HONEST-NOTES.md` and the README. If a number there and a number somewhere else disagree, the measured one is right.

Tool comparison sources (pricing pages, licences, 2026-11-23): see `facts/comparison-sources.md`.

## The model path (2026-11-23)

Ringlark reaches a model only through the shared wrapper in `packages/core-py`, which uses the Anthropic Messages API (`POST /v1/messages`, header `anthropic-version`, structured output with `output_config.format`). The facts it relies on, with the pages they came from, are in the hub file `docs/FACTS-AND-SOURCES.md` under "Anthropic Messages API (docs read 2026-11-23)". What Ringlark adds on top of them:

| Fact | Status | How it was checked |
|---|---|---|
| The call agent, the caller reader and the summaries send the same request shape as the shared wrapper (path, `x-api-key`, `anthropic-version`, JSON schema in `output_config`, no `temperature`, `top_p`, `top_k`, `tools` or `tool_choice`) | VERIFIED against a local fake server that asserts each field | `apps/api/tests/test_model_path.py` |
| The agent model is `claude-sonnet-5-5` and the reader and summaries use `claude-haiku-5-5` (settings `LLM_HARD_MODEL` and `LLM_BULK_MODEL`) | VERIFIED as settings defaults; model ids and prices on the vendor's page change | hub facts, 2026-11-23 |
| A real model follows the schema and the agent rules on a real call, within the time a voice call allows | UNVERIFIED live | never run with a real key. Run `python tools/eval_independent.py` with a model reader first |
| Recorded answers in `data/llm_fixtures` | They are NOT model answers | made from a local fake server that answers with the offline rules (`tools/record_llm_fixtures.py`) |
