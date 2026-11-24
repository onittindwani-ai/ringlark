# Security and data

## What the app does

- Sign in with email and password. Passwords are stored only as argon2 hashes. Sessions are signed, httpOnly cookies. Five wrong tries from one address slow down fast.
- Writes from the browser must carry a special header, which blocks cross site tricks. The web app refuses to forward login, webhook and tool calls.
- Webhooks are verified before anything is read: Telnyx by Ed25519 signature with a 5 minute window, Ultravox by HMAC SHA256 with a timestamp window of about a minute. Bad, old or missing signatures are refused. Bodies over 1 MB are refused.
- The agent's tool endpoints (book, look up, transfer, text, key press, end call) need a per call token that the app made when it created the call. The token cannot be used for another call and stops working when the call ends.
- Adapter addresses are checked so a setting cannot point at a private network (server side request forgery guard).
- Everything a caller says is treated as untrusted text. The agent prompt tells the agent never to follow instructions given by the person on the call, and the persona suite includes a prompt injection caller. A prompt is not a lock, so the tools themselves are limited: the agent cannot change settings, switch live on, or call a number that failed the rules.
- Every dial, tool call and approval goes in a hash chained audit log. **Verify the chain** detects edits.
- The do not call list and consent records are re read from the database before every dial.

## What you must do

- Keep `.env` out of git. Use long random values for `SESSION_SECRET`.
- Put the API and web behind HTTPS.
- Keep keys to the minimum scope (a Telnyx key for calls and messaging only, a Cal.com key for one event type).
- Back up, and rotate any key you suspect leaked.

## Personal data

Phone numbers and call transcripts are personal data. You decide the retention period. Ringlark stores transcripts and summaries, not audio. To remove a person, add them to the do not call list first (so they are never re-imported and called), then delete their record if the law or they ask. Keep a do not call record even after deletion, otherwise a re import could call them again. Ultravox and Telnyx handle call audio under their own terms: read them.

## Checks run

Secret scan (`tools/scan_secrets.py`), `pip-audit` and `pnpm audit` on 2026-11-23. Results are in `SECURITY.md`.

## Reporting a problem

See `SECURITY.md` at the repository root.
