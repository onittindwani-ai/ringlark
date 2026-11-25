# Using it for a client

You run Ringlark for someone else's business. Keep each client in their own copy.

## Rules that keep you safe

1. **One install per client.** Own database, own settings, own phone numbers, own voice and calendar accounts. Never mix two clients' people in one database.
2. **Their accounts, their names.** The client creates and owns the Telnyx, Ultravox, calendar and CRM accounts. You get access, not ownership. Caller ID and texting registration are in the client's business name.
3. **Their consent.** Only import people the client has the right to call. Each row needs a consent record. You are not a source of leads in this system.
4. **Two logins.** The client owner is the owner. If you approve follow ups for them, use the approver login so you cannot change settings.
5. **Start in draft.** Run a week of drafts and persona suite runs with the client reading them.
6. **Say what the agent is.** The client's customers hear that it is an AI assistant. Never configure it to pretend otherwise.

## Setting up

1. Do `02` and `US-CALLING-CHECKLIST.md` with the client.
2. Set up the install (`05` to `08`). Use the client's address in `OWNER_EMAIL`.
3. Write the agent prompt with `PROMPT-WRITING-GUIDE.md` and the templates in `prompts/`. A real install starts with no agent, no number and no campaign (the demo loads them from a seed file). As the owner, with the `TOKEN` below and the headers `x-session: $TOKEN` and `x-ringlark: 1`:
   - create the agent and its first prompt version: `POST /api/agents` with `{"name": "Sam", "company": "Their Business", "transfer_number": "+1...", "prompt": "<the prompt>"}` (a company left out becomes `COMPANY_NAME`);
   - make that version the live one: `POST /api/agents/<agent id>/activate` with `{"version_id": <id from the answer>}` (also on the Agents page);
   - add the phone number you own: `POST /api/numbers` with `{"e164": "+1...", "agent_id": <agent id>}`, then tick its checklist on the Numbers page as you finish each registration;
   - create the campaign on the Campaigns page, or `POST /api/campaigns` (it requires a granted call consent on file by default, so import each person with `call_consent` set to yes; only the owner can send `require_prior_consent: false`).
   Then run the simulator and the persona suite and fix what fails.
4. Import their people. The easy way: open Campaigns, press **Import**, then **Choose a CSV file**. You see the row count and the first rows before anything is added, then press **Import**. The same steps by API:
   `TOKEN=$(curl -s -H "content-type: application/json" -d '{"email":"you@theirdomain.com","password":"..."}' https://api.theirdomain.com/api/auth/login | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")`
   then post the CSV text to `/api/campaigns/<campaign id>/targets` with header `x-session: $TOKEN` and `x-ringlark: 1`. Columns: `first_name`, `last_name`, `phone`, `timezone`, `email`, `sms_consent`, `call_consent`. A clear yes (`yes`, `true`, `1`) in `sms_consent` allows texts to that person. A clear yes in `call_consent` records a granted call consent for that number, which a campaign with `require_prior_consent` needs before it will call anyone. Anything else counts as no, and a `call_consent` never overrides a number that is on the do not call list or whose consent was withdrawn (that row is flagged `consent_not_recorded_refused_before`). A row with a bad number or an unknown time zone is kept and flagged and is never called, because hours cannot be checked. An email that is not one plain address (for example two addresses with a comma) is dropped and flagged `bad_email`. A number already in any campaign counts as a duplicate. Once a campaign is running only the owner can add people to it. Only `+1` numbers are called unless `ALLOWED_CALLING_COUNTRIES` says more. The reply says how many were added, how many were duplicates and what was flagged.
5. Look at the flags in the campaign table.
6. Add the client's existing do not call numbers before the campaign starts: one list with `POST /api/suppressions/import` and `{"rows": [{"phone": "+14155550100", "reason": "their old list"}, ...]}` (up to 5,000 rows a time; the reply counts added, already listed and bad numbers), or one at a time on the Numbers and compliance page.

## What to charge for

This guide gives no price figures. It gives the shape of the offer, so you can price it yourself after looking at your market and your costs.

- **Setup, once.** Business basics check (`02`), the calling rules check (`US-CALLING-CHECKLIST.md`), accounts and phone numbers, install and hosting, writing and testing the agent prompt, list cleaning, a week in draft mode with the client reading every call plan. Charge for the hours and the care, not for the software, which is free.
- **Running it, monthly.** Reading the follow up approvals on the days they need a person, listening to flagged calls, tuning the prompt, keeping the do not call list current, a short report. State plainly how many hours a month that includes.
- **Costs that pass through, at cost.** Hosting, phone numbers and calling minutes, texting and carrier fees, the voice engine, the calendar and CRM seats, and any model usage. Show the client these as their own accounts, not as your markup.
- **Never charge for** a promised number of meetings or deals. This system places calls inside safety limits, books meetings and drafts follow ups. It cannot promise results, and the demo numbers are fictional.

## Onboarding checklist

1. Business basics check (`02`) and the calling checklist signed off by the client.
2. Client created their own phone, voice, calendar and CRM accounts and gave you access.
3. Caller ID and texting registration done in the client's business name (the checklist on the Numbers page shows what is still open).
4. Install running with its own database, backups on (`11`), `make doctor` clean.
5. Their people imported with consent records, flags read, existing do not call numbers added.
6. Agent prompt written with the client, simulator and persona suite run and read.
7. Voicemail left off unless the client wants it and has approved the exact message. Phone menus: hang up, or one configured key.
8. One week in draft mode, the client reads the call plans and says yes or no.
9. Switch to live for a few calls a day (the daily cap is 25 in the demo and 50 by default), then raise it slowly.

## Handover

When you finish or the client takes it over: give them the owner login, the list of every account and who owns it, the location of the backups and the restore steps (`11`), the prompt versions and templates as files, and what the Audit page shows (there is no audit export button, so copy what the client needs). Ask them to change every password and key while you watch, then remove your access. Keep nothing of theirs on your machines.

## What to put in the client contract

Plain wording, checked by your own lawyer: what is included in setup and in the monthly work; that costs of third party accounts are the client's; that the client owns the data, the accounts and the numbers; that the client confirms they have the right to call and text every person on their lists and keeps the consent records; that the caller always says it is an AI; that no results are promised; who answers if a call goes wrong, and how fast; how either side ends the work and what happens to the data afterwards. This is not legal advice.

## Reporting

The Overview and Metrics pages show counts from the database, not promises. Do not quote results to a client from the demo data. It is fictional. Do not quote the persona suite as a measure of how a language model agent will do on real calls: the suite here runs an offline rule based agent.

## When the client leaves

Give them a database backup (`11`) and the CSV files you imported, then delete their install and database and revoke every key they gave you. See `13`.
