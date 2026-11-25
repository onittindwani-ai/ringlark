# Connect your tools

Ringlark talks to outside services through adapters. Each category (calls, voice, texts, calendar, CRM, email) has a safe offline adapter called `seed`, and real ones you can switch on. **None of the real ones has been tested against a real account.** Tier A adapters are tested against local copies written from the public docs. Tier B are written from the docs and not run. Tier C are recipe prompts only.

Switch one at a time. After each, run `python tools/doctor.py` (add `--live` to test the real connection; it places no call).

## Calls and texts: Telnyx (Tier A)

1. Make a Telnyx account, buy a number, finish carrier registration for texting and caller ID (your job, see `02` and `US-CALLING-CHECKLIST.md`).
2. Create a Call Control application. Note its connection id. Create an API key and find the account public key. The exact menu names are UNVERIFIED (see `facts/telnyx.md`).
3. Set `TELEPHONY_ADAPTER=telnyx`, `SMS_ADAPTER=telnyx`, `TELNYX_API_KEY`, `TELNYX_PUBLIC_KEY`, `TELNYX_CONNECTION_ID`, `TELNYX_FROM_NUMBER` (E.164 format, like +14155550123).
4. Set `PUBLIC_BASE_URL` to the public address of your API.
5. In Telnyx, point the application's webhook to `https://YOUR-API-HOST/api/webhooks/telnyx`.

## Voice engine: Ultravox (Tier A)

1. Make an Ultravox account and an API key. Make a webhook secret when you add the webhook.
2. Set `VOICE_ADAPTER=ultravox`, `ULTRAVOX_API_KEY`, `ULTRAVOX_WEBHOOK_SECRET`.
3. In Ultravox, add a webhook to `https://YOUR-API-HOST/api/webhooks/ultravox` for call ended events.
4. Pick the voice by listening to a real test call. See `VOICE-OPTIONS.md`.

**The bridge is UNVERIFIED.** Ringlark creates the Ultravox call, dials with Telnyx, and joins the two with a Telnyx streaming action. That join is written from the docs and never run live. A documented alternative is a TeXML application that connects the call to the Ultravox stream. See `ARCHITECTURE.md` and `14`.

## Calendar (Tier A: calcom)

1. Make a Cal.com event type for the meeting. Make an API key.
2. Set `CALENDAR_ADAPTER=calcom`, `CALCOM_API_KEY`, `CALCOM_EVENT_TYPE_ID`.

## CRM (Tier A: twenty)

Set `CRM_ADAPTER=twenty`, `TWENTY_BASE_URL`, `TWENTY_API_KEY`. The real field names are unverified. Ringlark finds a person by phone and adds a note after each call.

## Email (Tier B: smtp_imap)

Follow up emails go through your own mailbox: `EMAIL_ADAPTER=smtp_imap`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `EMAIL_FROM`. Gmail needs 2 step verification and an app password. All follow ups wait for approval unless you change `FOLLOW_UPS_NEED_APPROVAL`.

## Other voice platforms

Vapi and Retell AI are recipe prompts in `prompts/` (Tier C). Paste one into Claude Code or Codex to have it write the adapter. They are not built or tested here.

## The model behind the simulator (optional)

The default simulator is an offline stand in made of rules. To use a language model for summaries, set `LLM_BACKEND=anthropic` and `ANTHROPIC_API_KEY`. Its quality here is unverified.
