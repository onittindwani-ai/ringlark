# US calling checklist

**This is not legal advice.** It lists what Ringlark does, and what only you can do. Rules differ by state and change. Ask a qualified person where you operate, and read each source yourself.

## AI voices and consent

- In February 2024 the FCC ruled that AI generated voices count as "artificial" voices under the TCPA, so calls that use them need the called person's prior express consent. It said it was confirming how the existing rules apply. Sources (law firm summaries read 2026-11-23, not the ruling itself): https://www.cooley.com/news/insight/2024/2024-02-15-fcc-ai-generated-robocalls-illegal-under-the-tcpa and https://www.wiley.law/alert-FCC-Extends-Regulatory-Reach-Over-AI-Announces-TCPA-Restrictions-Cover-AI-Generated-Voices-in-Outbound-Calls.
- The same summaries say the penalties can be large (damages of $500 per call, up to $1,500 if willful, plus FCC fines). UNVERIFIED in detail.
- What Ringlark does: keeps a consent record for each person. A new campaign (made on the Campaigns page or with `POST /api/campaigns`) requires a granted call consent on file, so it never dials a person with no record: the import takes a `call_consent` column (a clear yes records the consent) and a person without one is shown as "No consent on file" and is not called. It never dials a revoked consent, and it says in the first sentence that it is an AI assistant. Only the owner can create a campaign with the consent check turned off (`require_prior_consent: false`, written to the audit log), and a campaign created before this default keeps the setting it had. The fictional demo practice runs with the check off because its people are made up.
- What only you can do: collect consent in a form that meets the law, keep the proof, and decide whether your consent is enough for your calls. Ringlark stores the record you give it.

## Caller ID and signed calls (STIR/SHAKEN)

- Your carrier signs your calls and shows your business name. Ask your carrier for the attestation level of your number and register your business name for caller ID.
- Ringlark has a checklist per number on the Numbers and compliance page where you record what you did. It does not do it for you.

## Texting (10DLC)

- Business texts from a normal US number need brand and campaign registration. See `BUSINESS-BASICS-HUB-COPY.md` section 5.
- Only text people who agreed to texts. Every follow up text includes how to stop.

## Calling hours

- Ringlark checks hours in the person's own time zone, weekdays only, 09:00 to 17:00 by default (a decided default you can change). Federal rules set the earliest and latest hours, and states can be stricter. The default is inside the federal hours, and a person with an unknown time zone is never called.

- The hours come only from the time zone column in your list, and nothing else tells Ringlark where a person is. A list exported with one default zone (all New York, say) would call a person in Los Angeles at 6:00 in the morning. The import compares the area code with the zone and warns about rows that do not fit (a partial table, a warning only), and the owner has to say they looked before such a campaign starts. Check the zones yourself too: ask where the people are, not only which number they have. The daily cap counts from midnight in `OFFICE_TIMEZONE`.

## Do not call

- Ringlark keeps its own do not call list and adds a number the moment a person asks to stop. Honor the national and state registries too. Import them with the do not call import (`POST /api/suppressions/import`, steps in `10-USING-IT-FOR-A-CLIENT.md`) or one by one on the Numbers and compliance page. Ringlark does not look them up for you.

## Recording

- Some places need everyone on a call to agree to recording. Ringlark does not store audio. If your phone or voice service records calls, tell people in the first sentence and check the rule where they live. The default greeting says the call may be recorded and transcribed because Ringlark stores a transcript.

## Voicemail

- Off by default. If you turn it on, the message must say it is an AI assistant, who it is calling for and why. The dialer refuses a vague message. Rules for leaving AI voice messages are covered by the same consent question above.

## Before you call real people

Tick every item in `09-GO-LIVE-CHECKLIST.md`.
