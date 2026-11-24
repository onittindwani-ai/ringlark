# How well the offline agent reads callers, on sets nobody tuned it for

**The reader and the agent here are rules, not a language model.** Every number below is a score for those rules. It says nothing about how a live model would do. A live model path exists (`LLM_BACKEND=anthropic`) and has never been run against the real service: UNVERIFIED.

## What was measured

Two independent test sets, A and B, were written by agents that never saw this code. They read only the spec, the start here guide and the capabilities page. Each set has about 135 things a caller says (one line each, with a label) and 25 whole calls (only the caller's turns, with an expected outcome and the compliance behaviour required). The authors' own notes are in `data/eval/independent/README-heldout-authors.md`, including the labels they chose, the ambiguous items and the codes they used.

`tools/eval_independent.py` runs both sets. For one line it measures two things:

- **Label:** what the reader called the line. Strict means the author's main label, lenient means any label the author accepted.
- **Behaviour:** what a fresh offline agent with the shipped strong prompt actually did. For a line that must stop the call, did it end the call with a do not call result and suppress the number?

For a whole call it plays the caller's turns against the agent and compares the end result and the compliance checks it can see (it lists the ones it cannot see, and never counts those as passed).

## Order of work, so the numbers can be trusted

1. Read only the authors' notes. Wrote the scorer and a reader that mirrored the old rules. (While checking the file layout I printed 3 lines and 2 scripts of set A. Nothing was tuned on them.)
2. Ran set A once: the **first run**, saved untouched (`set_a_first_run.json`).
3. Improved the reader and agent from general knowledge of how people talk (inflections, negation and look alikes, channel words, a few common phrases in Spanish, French, Portuguese and romanised Hindi, our own phrase test in `apps/api/tests/test_caller_reader.py`). Set A items were not looked at. Set B was not opened.
4. Ran set B once: the **first run**, saved untouched (`set_b_first_run.json`). Set A rerun for the record (`set_a_after_tuning.json`), now not held out.
5. Only then looked at the stop requests the agent missed in both sets, and fixed general causes (see "What changed after looking"). **From here both sets are spent**: the "final" numbers were tuned on the stop misses and are not held out numbers. They are in `set_a_final_offline.json` and `set_b_final_offline.json`.

## The numbers

| | Lines, label strict | Lines, label lenient | Calls, right outcome | Calls, all checkable codes passed |
|---|---|---|---|---|
| Old self written persona set, first run (14 calls, different kind of test) | | | 7 of 14 (50 percent) | |
| **Set A, first run** (before any change, held out) | 65 of 135 (48.1 percent) | 69 of 135 (51.1 percent) | 11 of 25 | 19 of 25 |
| Set A, after general improvements (not held out) | 99 of 135 (73.3 percent) | 102 of 135 | 16 of 25 | 22 of 25 |
| **Set B, first run** (after the general improvements, held out) | 83 of 137 (60.6 percent) | 84 of 137 (61.3 percent) | 13 of 25 | 23 of 25 |
| Set A, after looking at the stop misses (not held out) | 99 of 135 (73.3 percent) | 105 of 135 (77.8 percent) | 16 of 25 | 22 of 25 |
| Set B, after looking at the stop misses (not held out) | 84 of 137 (61.3 percent) | 87 of 137 (63.5 percent) | 13 of 25 | 23 of 25 |

The honest numbers for how it reads callers it has not seen are the two first runs: about half on the old reader (set A) and about 61 percent on the improved reader (set B). The old self written persona set is a different test (whole calls, written by the same author as the rules), so the 7 of 14 is not comparable line by line.

## Compliance: a stop request must always win

Reported on its own, by what the agent did, not by its label. "Must stop" is every line whose accepted readings include a request not to be called again (the authors counted it as stop if stopping was a safe reading). "Clear" is the same without the ambiguous lines.

| | Must stop: stopped | Clear stop requests: stopped | Look alikes wrongly stopped ("stop by after 5") | Lines that must not stop, wrongly suppressed (96) | Channel only opt outs honoured (no text or email after) |
|---|---|---|---|---|---|
| Set A, first run | 15 of 24 | 11 of 15 | 1 of 5 | 1 of 96 | 7 of 7 |
| **Set B, first run** | 15 of 21 | 13 of 14 | 0 of 2 | 0 of 96 | 6 of 11 as printed (the first scorer wrongly counted "I won't email you again" as an offer; 11 of 11 on the fixed scorer, final run) |
| Set A, final | 23 of 24 | 15 of 15 | 0 of 5 | 1 of 96 | 7 of 7 |
| Set B, final | 21 of 21 | 14 of 14 | 0 of 2 | 0 of 96 | 11 of 11 |

Whole calls where the person asks to stop mid call: the agent ended the call at the right turn in 5 of 5 (set A, first run) and 4 of 4 (set B, first run). The first run files say 8 of 9 and 7 of 9 because the first scorer counted channel opt out calls (stop the texts, the call may go on) as call stops; the scorer was fixed afterwards and the old engine was re scored with the fixed scorer to get the 5 of 5 and 4 of 4. The agent never claimed to be human in any line or call. The one remaining miss in set A is an ambiguous line about deleting a consent record that was read as a text only opt out (the call continues, the texts stop).

**Not yet covered:** the agent ends the call with "do not call" on a stop request, but it cannot record a channel opt out itself while the call goes on. That is recorded by the post call step (`postcall.py` reads the transcript and records the revoked text consent, so a later text is blocked). The test harness only runs the call, so it cannot show that step; `apps/api/tests/test_engine.py` and `test_caller_reader.py` cover it.

## What changed after looking at the stop misses

All general, none of it a copy of a test line.

- A stop request is read before anything else, including an injection attempt ("ignore your rules and stop calling me") and interest ("book it, and never call me again"). The stop does not depend on the prompt any more: a weak prompt that says nothing about stopping still ends the call. (The persona suite still separates strong from weak prompts on the other rules.)
- Look alikes are removed before reading: "stop by", "don't stop calling", "stop, hold on", "can't stop thinking".
- More ways to ask: "taking my number off", "I don't want any more calls", "can you not call me again", "mat call karo", "never quit".
- Consent withdrawn for everything, for "automated" contact (our own calls are automated) or with no named channel is a stop. Consent withdrawn for text, email or recording only stops that channel and the call goes on. A recording refusal ends the call.
- An angry caller who threatens a complaint or a lawsuit, or tells us to go away, is treated as asking to stop: the number is removed. This is a policy choice: one lost lead costs less than one more unwanted call. Plain anger with no threat ends the call politely and does not suppress the number. Change it in `caller_phrases.py` (`HOSTILE_STOP`).

## Where it is still weak

- It reads about half of the objections ("we're all set", "send me an email", "I'll think about it") and many soft interest lines as "unclear". Unclear is the safe fall back (the agent asks once to repeat, then ends and flags the call for a person), but it loses leads. Recall per label on the final runs: objection 47 percent on both sets, interest 67 percent (set A) and 40 percent (set B), wrong person 67 and 33 percent, transfer request 63 and 50 percent, recording question 40 percent.
- Callback requests are caught when the person names a time or says "call back"; indirect forms are missed (set B first run 40 percent).
- Languages other than English: 12 lines in the two sets, a handful of phrases covered. Do not rely on it for them.
- The agent offers only the two times it was given. A caller who picks another day ("Friday is fine") is not booked.
- It cannot hear. Tone, sarcasm and talking over the agent are out of reach of text rules.
- Fifteen of the compliance codes the authors listed cannot be checked from a transcript by this harness (for example repeating a callback time back, or not revealing personal details). They are listed in each result file under `codes_not_measured_by_this_harness` and are not counted as passed.

## Run it

```
python tools/eval_independent.py --set a    # or b; add --out file.json to save the full result
```

Only totals are printed. Failing lines are listed by id in the result file, not by their text. Do not tune on a set and call it held out: write new lines in your own words, run them once, save that first run, then fix.
