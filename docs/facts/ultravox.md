# Ultravox (voice engine)

Checked 2026-11-23. https://docs.ultravox.ai

- VERIFIED: create a call with POST /api/calls, header X-API-Key. The body takes systemPrompt, a voice name or an external voice, selectedTools (a temporary tool describes an HTTP endpoint), a telnyx medium and maxDuration. The reply has callId and joinUrl.
- VERIFIED: webhooks are signed. Headers X-Ultravox-Webhook-Timestamp and X-Ultravox-Webhook-Signature. The signature is HMAC SHA256, as hex, of the body plus the timestamp. Reject timestamps older than about a minute. A comma separated signature header can hold more than one value.
- VERIFIED: built in voices, voice cloning and a bring your own voice option exist (voices overview page).
- UNVERIFIED: the shape of staticParameters and automaticParameters for tools (Ringlark uses a static header with a per call token).
- UNVERIFIED: the path to read the transcript of a finished call. Ringlark builds its transcript from the call events it stores.
- UNVERIFIED: how a Telnyx call joins an Ultravox call. Ringlark dials with Telnyx and uses a streaming action to the joinUrl. The documented alternative is a TeXML connect to the stream.
- In this project: tested against a mock (mock/ultravox_mock.py), including the signature. Never run against the real service.

- Contract test (2026-11-23, mock/contracts/ultravox): the request fields, the telnyx medium written as {"telnyx": {}}, the maxDuration pattern (for example 600s), firstSpeakerSettings with exactly one of user or agent, voice never combined with externalVoice, and the callId and joinUrl response were checked against the calls-post page. No OpenAPI file was fetched.
