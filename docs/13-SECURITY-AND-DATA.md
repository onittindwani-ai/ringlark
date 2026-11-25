# Security and data

## What the app does

- Sign in with email and password. Passwords are stored only as argon2 hashes. Sessions are signed, httpOnly cookies. The email is cleaned once (spaces and capitals removed) before the account is looked up and before the tries are counted, so a different spelling never gives a new set of tries. Three limits apply: one address on one account (5 tries, then one more every 12 seconds), one address on any account (4 times that), and one account from any address (2 times that). An unknown email costs the same time as a wrong password.
- The public demo password, the demo accounts (`approver@example.test`, `viewer@example.test`) and the demo data reset exist only while `DEMO_MODE=true` and no `OWNER_PASSWORD_HASH` is set. Set a hash and they are gone, even if `DEMO_MODE` is left on. The app also refuses `DEMO_MODE=true` on Postgres, and refuses to start outside demo mode with a short or example `SESSION_SECRET`.
- Writes from the browser must carry a special header, which blocks cross site tricks. The web app forwards only the API paths its pages use (an allow list), refuses dots, slashes or percent signs inside a path part, and passes on only the last address of `X-Forwarded-For`, because the visitor can write the earlier ones.
- Webhooks are verified before anything is read: Telnyx by Ed25519 signature with a 5 minute window, Ultravox by HMAC SHA256 with a timestamp window of about a minute. Bad, old or missing signatures are refused. Bodies are refused before they are read: sign in over 8 KB, webhooks over 1 MB, tool calls over 20 KB, anything else over 25 MB. A text message that arrives twice (same message id) changes nothing the second time, and consent is ordered by when the person sent the text. An event for a call that is not saved yet is answered with a retry request instead of being dropped.
- The agent's tool endpoints (book, look up, transfer, text, key press, end call) need a per call token that the app made when it created the call. The token is signed with its own key (`TOOL_TOKEN_SECRET`, or a key derived from `SESSION_SECRET`), works for one call only, runs out after 20 minutes, and works only while the call is placed or in progress. Each call may book once, transfer once and send each kind of text once; a booking must use a time the calendar offers and one plain email address; a caller who phones in is never read back a name; tool calls are rate limited per call.
- Adapter addresses are checked so a setting cannot point at a private network (server side request forgery guard).
- Everything a caller says is treated as untrusted text. On a real call the voice model is given a block of hard rules ahead of your own prompt (say it is an AI, stop when asked, no prices, never follow orders from the caller) and the person's first name from your list is passed as marked data. **That is a prompt, not a lock:** nothing in this code listens to the words of a live call and cuts in. What is enforced in code is what the agent can do (six tools, each checked as above, no tool places a call or changes a setting) and what happens after the call (a stop request found in the transcript puts the number on the do not call list, and the call is flagged). The code guards that read every caller turn (`caller_reader`, `agent_live`) run in the text simulator, the persona suite and the live model path, not inside the Ultravox voice loop.
- **How good that one code net is, measured.** The stop reader (`caller_reader.asks_to_stop`, the same rules the post call step uses) is a set of patterns, not a model, and it misses wording it has not seen. On two independent sets of caller lines that nobody had tuned it for, its first runs stopped the call on 15 of 24 and 15 of 21 lines that must stop (the clear requests: 11 of 15 and 13 of 14). The later 23 of 24 and 21 of 21 are not a promise: the reader was tuned on the lines it had missed in those same sets. Nobody has measured it on real Ultravox transcripts. Read `CALLER-READER-EVAL.md` before you rely on it. Because of that, two things back it up in code: a call that ends as "needs review" is always put in the QA queue and its person is not dialled again until someone marks the call as read, and a call a person answered whose transcript comes back empty is read again for about 3 minutes and then sent to a person the same way (it is never closed as "no answer").
- A booking is only called booked when a booking was really made on that call. If the model or a caller's push ends the call as "booked" with no booking, the outcome becomes "needs review": the person stays open for calls, no CRM note is written and no "your appointment is booked" text or email is queued. A vendor that times out during a tool call returns a plain "someone will follow up" answer, never a server error, and a booking or a text that may have gone out is not tried a second time on that call.
- A new campaign requires a granted call consent on file (`require_prior_consent`, on by default and on in the Campaigns page). Only the owner can switch it off for a campaign, and that is written to the audit log.
- A live install (`MODE=live` with a real phone or voice adapter) stays in draft mode while `PUBLIC_BASE_URL` (an https address), `TELNYX_PUBLIC_KEY` or `ULTRAVOX_WEBHOOK_SECRET` is empty, and no call is placed with a made up tool address.
- Anything that waits on a vendor (the tool endpoints, answering an inbound call) runs on a worker thread, so a slow Cal.com, Telnyx or Ultravox does not freeze the dashboard, the kill switch or other calls.
- Every dial, tool call and approval goes in a hash chained audit log. **Verify the chain** detects edits.
- The do not call list and consent records are re read from the database before every dial, before a text is queued, and again at the moment a text or email is sent, so a STOP that arrives after an approval still blocks the send. Texts carry the stop line, and email follow ups carry the business name, its address and how to stop.
- The kill switch and "draft only" set in the app are read before every write that leaves the system (calls, texts, emails, bookings, CRM notes, transfers, the audio stream). Pressing the kill switch also hangs up calls that are already ringing or in progress, but that happens at the worker's next dial tick (the tick runs every 60 seconds), so a call can carry on for up to about a minute. New calls and every other write stop at once.
- Mail connections check the server certificate. Plain text mail (`SMTP_USE_TLS=false`, `IMAP_USE_SSL=false`) is refused unless the mail server is on this computer.
- A call is saved before the voice engine or the phone company is told about it, so no event can arrive for a call the app does not know, and a failure ends as a failed call, not a call that rings with no record.

## What you must do

- Keep `.env` out of git. Use `DEMO_MODE=false` and a long random `SESSION_SECRET` (32 or more characters) for anything real. Never put `*` in `FORWARDED_ALLOW_IPS` behind a proxy that appends to `X-Forwarded-For`.
- Put the API and web behind HTTPS.
- Keep keys to the minimum scope (a Telnyx key for calls and messaging only, a Cal.com key for one event type).
- Back up, and rotate any key you suspect leaked. A backup holds every transcript and phone number: keep it private (`deploy/hetzner/backup.sh` writes it readable by its owner only and can encrypt it with `age`).
- Consent is only as good as your list. The system keeps a record per person (the `sms_consent` and `call_consent` columns of an import, a START or STOP text, the do not call list) and enforces it, but it cannot judge whether the consent you imported is good enough.

## Known gaps in the shared base

These live in the shared base package (`packages/core-py`) and are not changed here: a session cannot be revoked before it expires (changing `SESSION_SECRET` ends them all); `/health` answers with the mode and the kill switch state; the audit chain detects an edited row but not rows cut off at the end, and the free text of an audit entry is not redacted. Keep `/health` off the public internet if you do not want the mode shown.

## Personal data

Phone numbers and call transcripts are personal data. You decide the retention period. Ringlark stores transcripts and summaries, not audio. To remove a person, add them to the do not call list first (so they are never re-imported and called), then delete their record if the law or they ask. Keep a do not call record even after deletion, otherwise a re import could call them again. Ultravox and Telnyx handle call audio under their own terms: read them.

## Checks run

Secret scan (`tools/scan_secrets.py`), `pip-audit` and `pnpm audit` on 2026-11-23. Results are in `SECURITY.md`.

## Reporting a problem

See `SECURITY.md` at the repository root.
