# Ringlark spec

Ringlark is an AI SDR setup system. It helps an implementer or a business set up inbound and outbound AI phone callers and the follow ups after each call, and keeps them inside the rules. It is not a hosted voice platform. The voice engine is Ultravox. Phone numbers, calls and texts are Telnyx. Bookings go through Cal.com, the CRM is Twenty.

## What it does
1. Keeps a versioned prompt library for each agent, with a diff view and a split test (A and B).
2. Runs a text mode simulator: a scripted caller persona talks to an agent prompt with no voice and no network. The offline stand in is rules, not a language model.
3. Runs a persona suite (hostile, rushed, wrong number, stop calling me, voicemail, phone menu, asks if it is a robot, and more) with an answer key and an honest score.
4. Dials outbound campaigns inside compliance gates: calling hours in the contact's timezone, do not call list, revoked consent, daily caps, retry limits, voicemail setting, kill switch, draft mode.
5. Creates the Ultravox call (agent prompt, voice, tools) and lets Telnyx carry it. Tool endpoints let the agent book, look up the CRM, transfer, send a text and end the call with a disposition.
6. After each call: transcript, summary, disposition, QA score, follow ups (text and email, through approval), CRM update.
7. Shows it in a dashboard with a live call console and a call scrubber.

## Entities (tables prefixed rm_)
State, Agent, PromptVersion, Flow, Number, Target, Campaign, Call, Turn, Disposition, QAScore, FollowUp, ConsentRecord, Suppression.

## Jobs
dial_tick (place due calls), postcall (process ended calls), followups (queue and send approved follow ups), crm_sync, report.

## Adapters
Telnyx (A, calls and texts, against a mock written from the docs), Ultravox (A, against a mock), Cal.com (A), Twenty (A), email SMTP (B), offline seed adapters for every category.

## Endpoints (summary, full list in docs/openapi.json)
Auth, overview, calls (list, detail, replay, waveform, take over, transfer), campaigns (list, create, start, pause), targets, agents (list, create), prompt versions (create, activate, diff, split), simulator (run, persona suite), numbers (list, add) and compliance checklist, do not call list (add, import), QA, follow ups (approve, reject), integrations, settings, approvals, audit, metrics, demo helpers, signed webhooks (Telnyx, Ultravox), tool endpoints for the agent during a call.

## Evals
Persona suite (dev set and held out set, first runs saved), compliance property tests with seeded random worlds, QA scorer checks, answer key for the seed data.

## Hard limits
No real call without live mode and an explicit confirm. Claude cannot hear voices, so voice quality is judged by the owner on a real test call. Consent and AI voice rules vary by place and the docs give no legal advice. Each client registers their own business for calling and texting.
