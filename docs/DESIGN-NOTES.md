# Design notes

Written before the pages and the app CSS. The look comes from the shared UI kit (`packages/ui-kit`). This file says what Ringlark adds on top and why.

## Who looks at it, and what for

The person who sets up AI phone callers for a business, and the business owner who keeps an eye on them. They open it to answer four questions: is anything being called that should not be, how did the last calls go, what needs a person to decide, and is the prompt getting better or worse. So the Overview leads with the safety state (draft or live, kill switch, who was blocked and why), then outcomes.

## Palette (60, 30, 10)

- 60 percent warm neutrals (cream, oat, sand), 30 percent coffee ink, 10 percent one accent. The accent is **slate blue** (`#3f5d7c`, dark theme `#8fb3d6`), a calm tone that reads as "telephone line" and stays clear of the clay used by a sibling system. True red is only for a real alarm (kill switch on, a failed compliance check, a flagged call).
- Status colours always come with a word: a call outcome is a badge with text, never a dot alone.
- Dark theme "espresso" keeps the same order of importance.

## Type, space, radius, motion

Geist for the interface and every number (tabular figures for durations and counts), Instrument Serif for page titles and the two big numbers. Space 8, 13, 21, 34, 55, 89. Radius 8, 13, 21. Motion tokens come from the kit: press 120 to 160 ms, hover 160 ms, sheets 240 to 320 ms, charts draw in once. Only transform and opacity animate. Reduced motion keeps fades and drops movement.

## The signature: the live call console

A call is a thing that unfolds in time, so the console is built around time.
- A synthetic waveform for the agent and the caller, drawn from the turn times (labelled synthetic on the page, because it is not recorded audio), with a playhead.
- A transcript that streams word by word in step with the playhead, the current turn highlighted.
- An agent state chip that changes as it happens: ringing, speaking, listening, using a tool, ended.
- Take over and Transfer buttons that need a confirm and are written to the audit log.
- In demo mode the console replays a recorded call at real speed (or 4x). The same player is the **scrubber** on the Call log: drag the bar and the transcript follows, click a line and the bar jumps to it.

## Pages

Overview, Live console, Call log, Campaigns, Agents and prompts (versioned editor, diff, split test, simulator, persona suite), Numbers and compliance, QA review, Follow ups and approvals, Integrations, Audit log, Metrics.

## Micro interactions in this app

Every action button shows the processing state and then a tick. Prompt save shows a live word count and refuses short prompts with the fix. The diff colours added and removed lines and also marks them with + and - signs (not colour alone). Persona results fill in row by row. A target table says in plain words why a person cannot be called right now ("closed in their time zone", "on the do not call list"). Empty states offer the next step. Destructive and risky actions (start a campaign, activate a prompt, take over, kill switch) confirm first.

## Honest labels

Anything produced by the offline stand in is labelled: the persona suite says "offline rules, not a language model", the waveform says "synthetic", the demo bar says "fictional data, nothing leaves this machine".
