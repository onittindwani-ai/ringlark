# Persona suite and how to read its score

The persona suite is 14 scripted callers who talk to an agent prompt in text, with no voice and no network. Each persona has an answer key: the result the agent should reach and checks it must pass (says it is an AI, stops when asked, never invents a price, never leaks its instructions, transfers when asked, short turns, and so on).

**The agent in the suite is an offline set of rules, not a language model.** It reads directives from your prompt text. So the suite tests your prompt's rules and the app's checks. It does not tell you how a language model will behave on a real call.

## The 14 callers

Hostile, rushed, wrong number, "stop calling me", voicemail, phone menu, "are you a robot", interested and ready to book, asks for a price, wants a human, prompt injection ("ignore your instructions"), silence, "call me back later", "who gave you my number".

## Three sets

| Set | Purpose | First run | Now |
|---|---|---|---|
| dev (14) | Tuned against while building | not kept | 14 of 14 |
| held out 1 (14) | Written without looking at the rules | 12 of 14, saved in `data/eval/persona_heldout_first_run.json` | tuned afterwards, so no longer held out |
| held out 2 (14) | Written in different wording, never tuned against | 7 of 14, saved in `data/eval/persona_heldout2_first_run.json` | 14 of 14 on the current code, measured in the browser test of 2026-11-24, so no longer a fair test |

## How to read this honestly

- The dev score proves little, because the rules were written against it.
- Held out 1 first run is 12 of 14. The misses were a number said in words and a name spelled with a capital. They were fixed, so that set is spent.
- Held out 2 first run is 7 of 14, and that is the number to trust more. Later work on the caller reader changed the rules, and the suite now scores 14 of 14 on this set, so treat it as spent as well and write a new set before you trust a score. Different wording finds what the rules miss. The seven that failed were the hostile caller, the rushed caller, a stop request in unusual words, a robot question in unusual words, a caller ready to book, a caller who wants a human, and a call back request.
- The first runs are saved untouched so nobody can quietly tune and re score.
- To keep the suite useful, write new callers in your own words before you tune, run them once, save the first run, then fix.

## Run it

Agents and prompts, then Simulator and persona suite, then Run the suite. Or `POST /api/agents/{id}/persona-suite`.
