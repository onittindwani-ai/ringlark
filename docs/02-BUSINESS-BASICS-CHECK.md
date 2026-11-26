# Business basics check

Do this before you place a single real call. It is boring and it matters more than any setting in the app. The shared guide is copied in `BUSINESS-BASICS-HUB-COPY.md`, and the calling specific list is `US-CALLING-CHECKLIST.md`.

## Quick checklist

1. **A real business, a real name, a real number.** The agent says who it calls for. The number people see must be a number of that business that someone answers.
2. **Consent first.** Only call people who agreed to be called by this business, in the way the law where you operate requires. Ringlark keeps a consent record per person and never dials a person whose consent was revoked (a new campaign requires a granted call consent on file by default, so a person you imported with no `call_consent` yes is not called). It does not check where your consent records came from. It cannot decide whether your consent is good enough. That is your job and your lawyer's.
3. **The agent says it is an AI.** The first sentence says it, and the dialer will not place a call whose greeting lacks it. Calls made with AI voices are covered by the US rules for artificial or prerecorded voices (see `US-CALLING-CHECKLIST.md`).
4. **Registered caller ID and signed calls.** Your carrier shows your business name and signs your calls (STIR/SHAKEN). Ringlark records that you did this, it cannot do it for you.
5. **Texting needs registration.** In the US, business texts need your brand and campaign registered with carriers (10DLC). Your job, takes days to weeks. Only text people who agreed to texts. Every text the system writes carries "Reply STOP to opt out." and is checked again for a STOP at the moment it is sent.
6. **A real way to stop.** The agent honors "stop calling me" on the call and the number goes on the do not call list at once. Keep your older do not call lists and import them.
7. **Know your rules.** Rules differ by country and state, including calling hours, recording consent and rules for AI voices. This is not legal advice. Ask someone qualified where you operate.
8. **Who approves.** Follow up texts and emails wait for approval by default. Decide who approves and set an approver login (see `04`).
9. **A human to transfer to.** Decide which number a transferred call goes to and in which hours (default 09:00 to 17:00 office time). Outside those hours the agent offers a call back instead.

## Tools that cost money or are free

Open source options exist for some pieces. See `TOOLS-AND-ALTERNATIVES.md` for the comparison and how it was scored.
