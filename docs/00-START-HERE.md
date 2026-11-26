# Start here

Ringlark helps you set up an AI phone caller that books meetings, and the follow ups after each call. It answers inbound calls and makes outbound calls inside rules that you can read. It runs on your own computer or server. It starts in a safe mode where no real call or text is ever made.

**Who this is for:** an implementer who sets up AI callers for clients, or a business owner who wants one. You can try the demo without coding. You need to be comfortable pasting commands.

## Pick your path

1. **I just want to see it work.** Read `01-QUICK-DEMO.md`. About 10 minutes. No accounts, no keys.
2. **I want to use it for a real business.** Read `02-BUSINESS-BASICS-CHECK.md` and `US-CALLING-CHECKLIST.md` first, then `03-CONNECT-YOUR-TOOLS.md`, `04-ENVIRONMENT-VARIABLES.md`, `VOICE-OPTIONS.md`, then one of `06`, `07` or `08` to put it online, and finish with `09-GO-LIVE-CHECKLIST.md`.
3. **I am using it for someone else's business.** Read `10-USING-IT-FOR-A-CLIENT.md`.
4. **I want to write a better agent prompt.** Read `PROMPT-WRITING-GUIDE.md`, then use the templates in `prompts/`.

## What you get

- A dashboard with eleven pages: Overview, Live console, Call log, Campaigns, Agents and prompts, Numbers and compliance, QA review, Follow ups and approvals, Metrics, Integrations, Audit log.
- A dialer that checks the rules before every call: kill switch, AI disclosure, number format, do not call list, consent (a new campaign calls only people with a granted call consent on file, unless the owner turns that check off for the campaign), calling hours in the person's own time zone, a call nobody has read yet, daily cap, tries per person, gap between tries.
- A versioned prompt library with a compare view, a split test, a text simulator and a persona suite (14 scripted callers with an answer key).
- Tools the agent can use during a call: book a meeting, look up the CRM, transfer to a person, send a text, press a key in a phone menu, end the call with a result.
- After each call: transcript, summary, result code, a QA score, follow ups that wait for your approval, and a CRM note.
- A fictional practice's worth of data with planted problems, so you can see the rules stop calls they should stop.

## What it is not

It is not a voice platform. The voice engine is Ultravox and the phone numbers and calls are Telnyx, both separate paid services. It is not a legal shield: rules for AI voice calls, consent and recording differ by place, and this is not legal advice. It has never been run against a real Telnyx, Ultravox, Cal.com or Twenty account, only against copies built from their public docs. How a Telnyx call joins an Ultravox call is the most likely thing to need a fix on first real use. Read `14-LIMITS-AND-HONEST-NOTES.md` before you trust it with real people.

## Safe mode, in one paragraph

The app has three states: **draft** (it plans and queues calls and follow ups, nothing leaves), **live** (it really calls and texts), and **kill switch** (everything stops). The app can move itself toward draft or stop, but it can never turn live on by itself. Only you can, by changing a setting on the server.

Words you may not know are in `GLOSSARY.md`.
