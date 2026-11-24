# Twenty (CRM)

Checked 2026-11-22. https://docs.twenty.com

- VERIFIED shape: GraphQL at /graphql with a Bearer key. A key is created under Settings, Developers, API.
- UNVERIFIED: the exact createPerson input fields. Introspection can be disabled for API keys, so the adapter keeps field names in one place for you to adjust.
- In this project: tested against a mock (mock/twenty_mock.py). The real field names are unverified.

- No machine readable spec exists to test against: the docs page says there is no static API reference, because each workspace generates its own from its schema (Settings, Developers, API). The contract test (mock/contracts/twenty) therefore checks only the documented auth header and the /graphql path.
