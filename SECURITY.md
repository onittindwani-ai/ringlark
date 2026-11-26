# Security

## Reporting a problem

Please do not post security problems in a public issue. Open the repository's **Security** tab, choose **Report a vulnerability** (a private report only the maintainers can read), and include steps to reproduce. We aim to acknowledge a report within 5 working days. Never include real keys, passwords, phone numbers or customer data.

## Two risks to know before you deploy

- **Demo mode.** With `DEMO_MODE=true` and no `OWNER_PASSWORD_HASH` the app has a public demo password and a data reset button. Setting an owner password hash switches both off; the app also refuses demo mode on Postgres. Never expose a demo to the internet.
- **Secrets.** `SESSION_SECRET` signs every login. If it is the example value anyone who has read the code can sign in as the owner, so outside demo mode the app refuses to start with a short or example one (32 or more random characters). Keep `.env` out of git.

## What was checked

- Webhook signature checks: Telnyx (Ed25519 over timestamp and body) and Ultravox (HMAC SHA256 of body plus timestamp), with tests for a missing signature, a wrong signature, a body that was changed, a key from another sender, and an old timestamp.
- The agent tool endpoints need a per call token. Tests: no token, another call's token, and an unknown tool all fail. The token works only while the call is placed or in progress.
- Prompt injection: a test where a caller tries to make the agent switch to live mode, turn off the kill switch and call another number. Settings do not change and no call is placed. The agent can only send fixed text messages to the person on the call, and a test checks it cannot send its own words or to another number. A persona in the persona suite also tries "ignore your instructions". A prompt is not a lock: the protection is that the tools are limited and checked in code (one booking, one transfer and one text of each kind per call, an offered time, one plain email address, a token that expires). On a real call the voice model is given the safety rules in its prompt; the code that reads every caller turn (stop requests, human claims, prices) runs in the text simulator and the live model path, not inside the Ultravox voice loop, so on a real call a stop request is enforced after the call from the transcript.
- Server side request forgery guard on adapter addresses (private, local, non http and credential bearing addresses are refused).
- Login rate limits (per address and account, per address, per account; one cleaned spelling of the email), signed httpOnly session cookie, CSRF header on writes, owner only settings (the approver login cannot change them). The public demo password, demo accounts and reset exist only without an owner password hash. Request bodies are refused by size before they are read (sign in, webhooks, tool calls each have their own limit).
- Texts: a person who said stop (on a call, by text or on the do not call list) is checked again at the moment of sending, on every path. The kill switch and draft setting stored in the app are read before every write that leaves the system and the kill switch hangs up live calls. Mail connections verify certificates.
- Secret scan of tracked files (`python tools/scan_secrets.py`): nothing found, with a test that it does catch placeholder keys.
- Dependency audit on 2026-11-23: `pip-audit` over the installed Python packages and `pnpm audit` over all JavaScript packages both reported no known vulnerabilities. This only covers known, published problems on that date. `ringlark` and `sendora-core` are local packages and cannot be audited this way.
- Compliance property tests (see `docs/14-LIMITS-AND-HONEST-NOTES.md`) check that the dialer never calls outside hours, a do not call number or a revoked consent number.

## What was not checked

No outside penetration test. No test against real vendor accounts. The CI workflow builds the Docker images and starts the compose stack on GitHub; nothing was deployed to a real host. Whether Telnyx call events use the same signed string as message events was not confirmed. Treat this as a careful self review, not an audit.

## Supported versions

Only the latest release.
