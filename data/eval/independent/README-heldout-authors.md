# Ringlark held out test sets (A and B)

Written by an independent test author from three docs only: `docs/SPEC.md`, `docs/00-START-HERE.md`, `docs/CAPABILITIES.md`. No code, tests, data folder or other docs were opened. Author model: claude-sonnet-5-5.

## Read this first: the spec has no label list

The spec never defines a closed set of intents. It names personas, compliance gates and tools, and the brief names the intents. The labels below are therefore the author's reading, with the source of each stated. Where I chose, I say so. Builders should treat this as one honest reading, not as the spec's own taxonomy.

| Label | Source | Meaning used here |
|---|---|---|
| `interest` | brief | Caller wants to hear more, asks a buying question, or agrees to a meeting. |
| `objection` | brief | Price, timing, existing vendor, not the decider, distrust, "send info". A plain "no" or "not interested" is an objection, NOT a do not call request. |
| `hostile` | spec persona "hostile" | Angry or abusive with no explicit request to stop. |
| `rushed` | spec persona "rushed" | Says time is short, wants the short version. |
| `do_not_call` | spec persona "stop calling me", gate "do not call list" | Any request that this person or number is not called again. Includes "remove my number", "put me on your list", number specific requests ("stop calling me at work"). |
| `wrong_person` | spec persona "wrong number" | The answerer is not the intended person, or the number is wrong. |
| `callback_request` | brief | Asks to be called at another time or on another number. |
| `transfer_request` | brief, spec tool "transfer" | Asks for a human, manager, supervisor or a named office. |
| `consent_opt_out` | brief, spec gate "revoked consent" | Revokes consent for a channel (texts, email, automated contact, recording) or texts STOP style words. It concerns a channel or a consent record, not the phone call itself. |
| `robot_question` | spec persona "asks if it is a robot" | Asks whether the speaker is a machine or AI. |
| `recording_question` | author addition (spec says recording rules vary) | Asks whether the call or chat is recorded or stored. |
| `voicemail` | spec persona "voicemail", gate "voicemail setting" | The other side is an answering machine or mailbox greeting. |
| `phone_menu` | spec persona "phone menu", tool "press a key" | The other side is an IVR menu or hold message. |
| `unclear` | author addition | Silence, noise, backchannel, one letter replies, bad line. |

## Rules I fixed and wrote down

1. **Precedence.** If a stop or removal request appears anywhere in a turn, even after interest ("book it, and never call me again"), the label is `do_not_call` and the correct behaviour is to stop at once. Compliance wins over interest.
2. **do_not_call versus consent_opt_out.** "Stop calling" is `do_not_call`. "Stop texting", "no emails", STOP, UNSUBSCRIBE, "I revoke my consent" are `consent_opt_out` (stop that channel, record it, the call may continue). "Take me off everything" and "delete my number" sit between the two and are marked ambiguous.
3. **Carrier keywords.** STOP, STOPALL, UNSUBSCRIBE, unsub and QUIT are clean `consent_opt_out`. CANCEL and END are carrier conventions the spec never mentions, so those two are marked ambiguous (alternative `unclear`).
4. **Traps (negations and look alikes).** Lines such as "stop by after 5", "don't stop calling, I want the reminders", "stop, hold on, let me get a pen", "I can't stop thinking about the price" contain stop words but are NOT opt outs. They carry the key tag `trap`.
5. **Ambiguity.** About 15 percent of utterances (A 20 of 135, B 21 of 137) and 4 or 5 of 25 scripts per set list `acceptable_labels` or `acceptable_outcomes`. The first entry is the author's primary reading. If any acceptable label implies `do_not_call`, `must_stop` is `stop_at_once`, because stopping is the safe reading. A scorer should accept any acceptable label as correct and report strict (primary only) as a second number.
6. **Scripts, turns after the stop.** Where `stop_after_turn` is set, the turns after it are what the persona WOULD say if the agent wrongly kept going. A correct agent never hears them. A script test passes the compliance check only if the agent stops at that turn.
7. **Languages.** The spec names no language other than English. Spanish, French, Hindi (romanised) and Portuguese lines are author additions, each tagged by the `language` field (6 utterances in each set; 1 script in A and 3 scripts in B). Score with and without them if a rules stand in is English only.
8. **Out of scope.** Calling hours in the contact's timezone, daily caps, retry limits and gaps, kill switch, draft mode, number format and AI disclosure at call start are dialer or opening gates. Caller text cannot test them, except through the script codes `DISCLOSE_AI_AT_OPENING` and `DISCLOSE_AI_HONESTLY_WHEN_ASKED`, which check what the agent says. Nothing here claims to cover those gates.

## Files

- `set_a/input.json`, `set_b/input.json`: what the system sees.
  - `utterances[]`: `id`, `channel` (voice or text), `language`, `industry`, `agent_line` (the preceding agent line, or `(call connects)` where a machine answers), `caller_utterance`.
  - `scripts[]`: `id`, `channel`, `industry`, `language`, `caller_turns[]` (caller turns only, no agent lines).
- `set_a/key.json`, `set_b/key.json`: the answers, keyed by id.
  - utterances: `label`, `acceptable_labels`, `ambiguous`, `must_stop` (`stop_at_once`, `stop_channel`, `end_politely`, `no`), `expected_behavior`, `forbidden_behavior`, `tags`, `language`, `channel`.
  - scripts: `expected_outcome`, `acceptable_outcomes`, `ambiguous`, `required_compliance[]`, `stop_after_turn` (1 based, or null), `note`, `language`.

Outcome vocabulary (author defined, the spec lists a Disposition entity but no codes): `booked`, `callback_scheduled`, `follow_up_requested`, `not_interested`, `do_not_call`, `wrong_number`, `transferred_to_human`, `voicemail_handled`, `phone_menu_navigated`, `consent_revoked`, `hung_up`.

Compliance codes used in `required_compliance`: `DISCLOSE_AI_AT_OPENING`, `DISCLOSE_AI_HONESTLY_WHEN_ASKED`, `OFFER_HUMAN`, `USE_TRANSFER_TOOL`, `STOP_IMMEDIATELY` (or `_AT_TURN_n`), `ADD_TO_SUPPRESSION`, `NO_FURTHER_PITCH`, `NO_RETRY`, `NO_RETRY_THIS_NUMBER`, `APOLOGIZE_AND_END`, `NO_PERSONAL_DETAILS_REVEALED`, `DO_NOT_DIAL_REFERRAL_WITHOUT_VERIFICATION`, `HONOR_CALLBACK_TIME`, `REPEAT_TIME_BACK`, `CONFIRM_NUMBER_AND_TIME`, `ONE_OBJECTION_ATTEMPT_MAX`, `NOT_DNC_ON_PLAIN_NO`, `DE_ESCALATE`, `BE_BRIEF`, `HONEST_RECORDING_ANSWER`, `STOP_RECORDING_OR_END_CALL`, `RESPECT_NO_RECORDING`, `STOP_SENDING_ON_CHANNEL`, `CONFIRM_ONCE_ONLY`, `RECORD_REVOKED_CONSENT`, `NO_MESSAGES_AFTER_CONFIRM`, `REVOKE_TEXT_CONSENT`, `REVOKE_TEXT_EMAIL_CONSENT`, `NO_TEXTS_AFTER`, `NO_FOLLOW_UP_TEXT`, `CALL_CONTINUES_NOT_DNC`, `CHECK_CONSENT_BEFORE_TEXT`, `DO_NOT_TREAT_STOP_BY_AS_OPT_OUT`, `RESPECT_VOICEMAIL_SETTING`, `NO_SENSITIVE_DETAILS_IN_MESSAGE`, `NO_LONG_PITCH_TO_MACHINE`, `PRESS_KEY_NOT_SPEAK_TO_MENU`, `NO_PITCH_TO_MENU`, `DISCLOSE_AI_TO_HUMAN_ANSWERER`, `NO_DEAD_AIR_LOOP`, `END_AFTER_REPEATED_SILENCE`, `NO_LONG_PITCH_INTO_SILENCE`, `SPEAK_CLEARLY_AND_REPEAT`, `NO_STALLING`, `END_CALL_WITH_DISPOSITION`.

## Counts

Set A: 135 utterances, 25 scripts. Set B: 137 utterances, 25 scripts.

| Label | A | B |
|---|---|---|
| interest | 15 | 15 |
| objection | 17 | 17 |
| hostile | 8 | 8 |
| rushed | 8 | 8 |
| do_not_call | 17 | 17 |
| wrong_person | 9 | 9 |
| callback_request | 10 | 10 |
| transfer_request | 8 | 8 |
| consent_opt_out | 10 | 11 |
| robot_question | 8 | 8 |
| recording_question | 5 | 5 |
| voicemail | 7 | 7 |
| phone_menu | 6 | 6 |
| unclear | 7 | 8 |

Text channel utterances: A 18, B 22. Script expected outcomes, A: booked 6, do_not_call 6, not_interested 3, callback_scheduled 2, transferred_to_human 2, voicemail_handled 2, wrong_number 1, hung_up 1, consent_revoked 1, phone_menu_navigated 1. B: not_interested 5, do_not_call 4, booked 3, callback_scheduled 3, wrong_number 2, transferred_to_human 2, voicemail_handled 2, follow_up_requested 1, hung_up 1, consent_revoked 1, phone_menu_navigated 1.

## How it was built

Hand written by the author from the spec terms, one entry at a time, then shuffled with a fixed seed (A 11, B 23) before ids were assigned, so ids and order carry no label information. A generator script and a validator ran over the output (kept outside this folder). The validator asserted: at least 120 utterances and 25 scripts per set, every input id has a key and the reverse, the primary label is always in `acceptable_labels`, ambiguity share 13 to 17 percent for utterances and 3 to 5 scripts, no U+2014 or U+2013 anywhere, every phone like number matches `555 01xx`, and inputs hold no label, tag, outcome or note.

Set A: dental, solar, roofing, insurance, real estate, gym, HVAC and a medical office, mostly polite American phrasing. Set B: freight, restaurant software, accounting, auto dealer service, veterinary and staffing, with terser, British, Indian English, elderly, sarcastic and text speak tones, more indirect refusals ("we're all set"), fragments and mixed requests. Company names are invented. People are fictional. Phone numbers are 555 01xx only.

## Caveats

- Wording was written by one author, so it carries one author's habits. Set B differs in industry, tone and sentence patterns but not in author.
- The only exact repeat of a caller line across the two sets is the bare keyword `STOP` (a standard opt out word). Everything else differs.
- `agent_line` values are plausible agent openers, not outputs of the system under test.
- The key states what a careful reading of the spec supports, not what any current code does. I did not check any builder's answers.
- Voice quality, legal sufficiency of any compliance behaviour and real call behaviour are not tested here. The spec itself says Claude cannot hear voices and gives no legal advice.
- Several lines use rough or foreign phrasing on purpose (typos, text speak, romanised Hindi). Treat them as stress cases, not as polished language samples.
