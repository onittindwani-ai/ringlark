# Go live checklist

Do not skip items. Tick each one. Going live means real calls reach real people, and a mistake can cost money and break the law.

## Before

- [ ] `02-BUSINESS-BASICS-CHECK.md` and `US-CALLING-CHECKLIST.md` are fully done (caller ID, signed calls, consent records, texting registration if you text, someone qualified has looked at your rules).
- [ ] `DEMO_MODE=false`, a real `OWNER_PASSWORD_HASH`, a `SESSION_SECRET` of 32 or more random characters, and `PUBLIC_BASE_URL` set to your https address. With Docker also a `POSTGRES_PASSWORD` made with `openssl rand -hex 24`. `make check-env` reports no problem.
- [ ] `COMPANY_NAME` is your business name. If you send email follow ups, `COMPANY_ADDRESS` is your postal address and `EMAIL_FROM` is a real address of yours. The Overview shows no problem about them (until they are set a real install stays in draft mode). If you text a booking link, `BOOKING_URL` is set.
- [ ] You made the agent, the number and the campaign in your own install (`10`, "Setting up"): a real install starts empty.
- [ ] `.venv/bin/python tools/doctor.py --live` reports no FAIL.
- [ ] The Integrations page **Test** button passes for every category you switched on, and the Telnyx and Ultravox webhook addresses are set at those services.
- [ ] **The bridge works.** Place one test call to your own phone (`VOICE-OPTIONS.md`, test call steps) and confirm you hear the agent and the agent hears you. The Telnyx to Ultravox join has never been run live by this project.
- [ ] You listened to the test call and you like the voice. Nobody who built this can hear it.
- [ ] The agent's first sentence says it is an AI. Ask it "are you a person" and check it says no.
- [ ] Say "stop calling me" on the test call. Confirm the number appears on the do not call list.
- [ ] Your people list was imported **by the owner** with consent records (a `call_consent` yes for each person: a new campaign calls nobody without one; an approver's import with that column is refused). Fill `consent_date`, `consent_source` and `consent_note` for each person so the record is evidence. Open Campaigns and look at "why they can or cannot be called now" for every row.
- [ ] Your older do not call list is imported (`POST /api/suppressions/import`, see `10`, or one by one on the Numbers and compliance page). Do it before you start the campaign.
- [ ] Voicemail is off, or the message says who is calling and why (the dialer refuses a vague message).
- [ ] `RETENTION_DAYS` is what you decided (default 365: transcripts, summaries and follow up messages older than that are deleted every day), and you know how to erase one person on request (`13`, "Personal data") and what that does not reach (other services, backups).
- [ ] A custom greeting, if you wrote one, says it is an AI and that the call may be recorded (the app refuses one that does not).
- [ ] You know who takes a transferred call and in which hours.
- [ ] Two people know where the kill switch is.

## First day

- [ ] Run in `draft` for a week and read what it would have done. Run the persona suite after every prompt change.
- [ ] Switch to `live` with one campaign, a low daily cap and a short list.
- [ ] Place a test call to your own phone and ask for an appointment: the times the agent offers must be the open times of your calendar, in your time zone, and the booking must appear in Cal.com at the hour you chose (this was never run against the real services, see `14`).
- [ ] If you leave voicemail on, test it on two real answering machines: the message must start after the beep and be heard whole (the event order is UNVERIFIED, see `14`).
- [ ] Watch the Live console for the first calls. Use **Take over** if a call goes wrong.
- [ ] Read every call marked **Needs a look** in QA review the same day.

## Always

- [ ] Reply to real replies and call backs the same day.
- [ ] Check the Audit log weekly and press **Verify the chain**.
- [ ] Back up the database (see `11`).
