# Telnyx (calls and texts)

Checked 2026-11-22 and 2026-11-23. https://developers.telnyx.com

- VERIFIED: send a text with POST /v2/messages, Bearer auth, body to, text, from. The reply has data.id.
- VERIFIED: place a call with POST /v2/calls (connection_id, to, from, webhook_url, client_state, answering_machine_detection). Answering machine results are human, machine or not sure.
- VERIFIED: webhooks carry telnyx-signature-ed25519 and telnyx-timestamp. For message webhooks the signed string is the timestamp, a pipe, then the raw body, and anything older than 5 minutes is rejected.
- UNVERIFIED for call events: that the same signed string applies (it is the scheme the vendor libraries use).
- VERIFIED from the vendor pages read 2026-11-23: the paths and required fields of streaming_start (stream_url is a wss address, stream_track, stream_bidirectional_mode), send_dtmf (digits), speak (payload and a voice written Provider.Model.VoiceId) and transfer (to). Answering machine results arrive as call.machine.detection.ended with the result in data.payload.result.
- A contract test found one real mistake: the speak action was sent the voice "female", which is not the documented format. It now sends Telnyx.KokoroTTS.af.
- UNVERIFIED: the answer and hangup action paths (the hangup page returned 404 when fetched, and answer was not read). They were written by symmetry.
- No machine readable OpenAPI file could be fetched with a page fetch; the excerpts in mock/contracts/telnyx are field lists read from the pages.
- UNVERIFIED: the portal path to the public key and the steps to create an API key and a Call Control application.
- Your own job, not the software's: US carriers require registering your brand and campaign (10DLC) before business texts are delivered, and caller ID and STIR/SHAKEN setup are yours too. See docs/US-CALLING-CHECKLIST.md.
- In this project: tested against a mock written from these docs (mock/telnyx_mock.py), including a real Ed25519 signature. Never run against the real service.
