# Cal.com (calendar)

Checked 2026-11-22. https://cal.com/docs/api-reference/v2

- VERIFIED: POST /v2/bookings with header cal-api-version 2026-02-25 and body start, attendee (name, timeZone, email), eventTypeId.
- UNVERIFIED: the slots endpoint version header (two pages disagreed: 2024-09-04 and 2024-08-13), so it is the setting CALCOM_SLOTS_VERSION.
- UNVERIFIED: webhook signature (HMAC SHA256 of the raw body in x-cal-signature-256, and the literal no-secret-provided when no secret is set) came from a third party.
- UNVERIFIED: where the API key and the event type id live in the dashboard. The key is shown once.
- In this project: tested against a mock (mock/calcom_mock.py). Never run against the real service.
