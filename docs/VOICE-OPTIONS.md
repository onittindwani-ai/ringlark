# Voice options

**Nobody who built Ringlark can hear a voice.** Every statement about how a voice sounds would be a guess. So this guide tells you what the choices are and how to judge them yourself on a real test call. Scores in `TOOLS-AND-ALTERNATIVES.md` leave voice quality out for the same reason.

## What the voice engine offers (checked 2026-11-23)

Ultravox offers built in voices, voice cloning, and a way to bring a voice from another provider (an external voice). Source: https://docs.ultravox.ai/voices/overview.md (VERIFIED). Ringlark picks the voice by name per agent, shown on Agents and prompts. The demo's "Mark (builtin)" is a stand in name for the offline demo only.

## Choices

1. **A built in voice.** Easiest. No extra account. Try several names on test calls.
2. **ElevenLabs through Ultravox's external voice option.** Needs your own ElevenLabs account and key, and its own price and terms. The Ultravox docs name it as an option. Details of the setup are UNVERIFIED here.
3. **A cloned voice of a real person.** Only with that person's clear written permission, and say so on the call as the AI disclosure requires. Cloning is a separate paid or self hosted step and carries legal and reputation risk.
4. **A self hosted voice service** (for example a cloning server you run) used through the generic external voice option. UNVERIFIED that this works. Treat it as an experiment.

## How to judge a voice (do this yourself)

1. Place a test call to your own phone with the voice you want (see below).
2. Listen for: does it sound clear on a phone speaker, does it pause in the right places, does it interrupt you, does it handle "um" and silence, does the speed suit the people you call.
3. Ask a friend who has never heard it to listen and say what they think it is.
4. Try three voices on the same script and pick the one you would be comfortable getting a call from.
5. Check the first sentence says it is an AI assistant, in a voice that is not trying to fool anyone.

## Test call steps

1. Set `MODE=live` and the Telnyx and Ultravox variables (`03`).
2. Add your own number as the only person in a campaign with a consent record you made for yourself, and a calling window that includes now (or run the test in your own hours).
3. Press **Run now** in a live install, or wait for the worker.
4. Open **Live console** to watch the call.
5. Hang up when done. Read the transcript and the QA score.
6. Change the voice name on the agent, save and call again.

## Cost

Voice is usually priced by the minute and changes. Read the vendor page the day you decide. This repo states no figure.
