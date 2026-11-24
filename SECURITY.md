# Security

## Reporting a problem

Please do not post security problems in a public issue. Use the repository's private security advisory feature, or contact the maintainers privately. Include steps to reproduce. Never include real keys, passwords, phone numbers or customer data.

## What was checked

- Webhook signature checks: Telnyx (Ed25519 over timestamp and body) and Ultravox (HMAC SHA256 of body plus timestamp), with tests for a missing signature, a wrong signature, a body that was changed, a key from another sender, and an old timestamp.
- The agent tool endpoints need a per call token. Tests: no token, another call's token, and an unknown tool all fail. The token works only while the call is placed or in progress.
- Prompt injection: a test where a caller tries to make the agent switch to live mode, turn off the kill switch and call another number. Settings do not change and no call is placed. The agent can only send fixed text messages to the person on the call, and a test checks it cannot send its own words or to another number. A persona in the persona suite also tries "ignore your instructions". A prompt is not a lock: the protection is that the tools are limited.
- Server side request forgery guard on adapter addresses (private, local, non http and credential bearing addresses are refused).
- Login rate limit, signed httpOnly session cookie, CSRF header on writes, owner only settings (the approver login cannot change them).
- Secret scan of tracked files (`python tools/scan_secrets.py`): nothing found, with a test that it does catch fake looking keys.
- Dependency audit on 2026-11-23: `pip-audit` over the installed Python packages and `pnpm audit` over all JavaScript packages both reported no known vulnerabilities. This only covers known, published problems on that date. `ringlark` and `sendora-core` are local packages and cannot be audited this way.
- Compliance property tests (see `docs/14-LIMITS-AND-HONEST-NOTES.md`) check that the dialer never calls outside hours, a do not call number or a revoked consent number.

## What was not checked

No outside penetration test. No test against real vendor accounts. Docker images were not built here. Whether Telnyx call events use the same signed string as message events was not confirmed. Treat this as a careful self review, not an audit.

## Supported versions

Only the latest release.
