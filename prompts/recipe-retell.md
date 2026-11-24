# Recipe: build a Retell AI voice adapter (not built, not tested)

Retell AI was scored from its documentation only, so no endpoint is claimed here. Paste this into Claude Code:

> Read apps/api/src/ringlark/adapters/base.py and adapters/ultravox.py. Look up the current Retell AI API documentation yourself and tell me the source link. Write an adapter `retell` that implements the same voice interface, registered as Tier C until it is tested. Write tests against a local mock that you write from the documentation. Every real call must go through `guard_write`. Read the key from `RETELL_API_KEY`. Check the base URL with `safe_base_url`. Keep the AI disclosure and the per call tool token. Mark everything you could not confirm as UNVERIFIED in docs/FACTS-AND-SOURCES.md. Do not call the real service.
