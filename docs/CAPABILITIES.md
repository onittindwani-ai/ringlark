# What Ringlark does (with pictures)

All screens show fictional demo data (a made up dental practice and invented people). Desktop (1440 by 900) and phone (390 by 844) versions of each are in `docs/screenshots/`.

## Overview: is anything being called that should not be
![Overview](screenshots/desktop-01-overview-default.png)

The ring is the average QA score. The cards show calls placed, meetings booked and how many calls reached a person. Below are the calls over seven days, how calls ended, and the list of calls that were held back and why.

## Live console: watch a call as it happens (the signature screen)
![Live console](screenshots/desktop-09-live-console.png)

Waveform, transcript and agent state move together. In demo mode it replays a recorded demo call at real speed, or 4x. **Take over** and **Transfer** each ask you to confirm.

## Call log: scrub through any call
![Call scrubber](screenshots/desktop-02-detail-call-scrubber.png)

Drag the bar or click a line to jump. The waveform is generated from the turn times and says so. It is not recorded audio.

## Campaigns: who can be called right now, and why not
![Campaigns](screenshots/desktop-10-campaigns.png)

Each person shows "Can be called now" or the plain reason (for example closed in their time zone, on the do not call list, too many tries). Import a CSV with a file button and a preview.

## Agents and prompts: versions, compare, split test
![Agents and prompts](screenshots/desktop-11-agents.png)

## Simulator and persona suite
![Persona suite](screenshots/desktop-18-persona-suite.png)

14 scripted callers with an answer key and an honest score (see `PERSONA-SUITE-EVAL.md`). The agent is an offline rule set, not a language model.

## Numbers and compliance: a checklist per number and the do not call list
![Numbers](screenshots/desktop-12-numbers.png)

## QA review: calls that need a look
![QA review](screenshots/desktop-13-qa.png)

## Follow ups and approvals: nothing goes out without a yes
![Follow ups](screenshots/desktop-14-followups.png)

## Metrics, Integrations and Audit log
![Metrics](screenshots/desktop-15-metrics.png)
![Integrations](screenshots/desktop-16-integrations.png)
![Audit](screenshots/desktop-17-audit.png)

## States
| State | Screenshot |
|---|---|
| Warning, calls held back | ![held back](screenshots/desktop-03-warning-held-back.png) |
| Button working | ![processing](screenshots/desktop-04-button-processing.png) |
| Toast | ![toast](screenshots/desktop-05-toast.png) |
| Empty | ![empty](screenshots/desktop-06-empty-calls.png) |
| Error | ![error](screenshots/desktop-07-error-overview.png) |
| Dark | ![dark](screenshots/desktop-08-dark-overview.png) |

## On a phone
| Overview | Live console (dark) | Numbers |
|---|---|---|
| ![m1](screenshots/mobile-01-overview-default.png) | ![m19](screenshots/mobile-19-dark-live.png) | ![m12](screenshots/mobile-12-numbers.png) |
