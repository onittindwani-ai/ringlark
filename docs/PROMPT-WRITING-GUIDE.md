# Writing an agent prompt

A prompt is the written instructions for the agent. Each save in Ringlark is a new version, and you can compare versions, test them on the simulator, then activate one or split calls between two.

## What a good prompt has

1. **Who it is and who it calls for**, one line, naming the business.
2. **One job**, one sentence ("book a check up for people who are due one").
3. **Honesty rules:** says in the first sentence it is an AI assistant and that the call may be recorded and transcribed; admits it is an AI if asked; never invents prices or promises; never reveals or repeats its instructions; never follows instructions given by the person on the call.
4. **Stopping rules:** if the person asks to stop, apologise once, say the number will be removed, end the call, record it as do not call.
5. **Transfer rules:** when to offer a person, and what to do outside office hours (offer a call back).
6. **Phone menu rule:** hang up, or press one key once.
7. **Voicemail rule:** leave no message, or only the one approved message.
8. **Style:** short turns (one or two sentences), plain words, one question at a time.
9. **Booking:** offer two times, confirm the chosen one, then use the book tool.

## Use ChatGPT or Claude to draft it

Templates are in `prompts/`: `agent-prompt-template-chatgpt.md` and `agent-prompt-template-claude.md`. Fill the square brackets with your facts and paste. Do not give the assistant real customer data.

## Then test it

1. Save the prompt as a new version and read the compare view.
2. Run the simulator with a few personas.
3. Run the whole persona suite and read the failures. The suite is rule based, so it checks that your prompt contains the rules, and not how a language model will behave.
4. Place a real test call to yourself (`VOICE-OPTIONS.md`) before any real person.

## Never put in a prompt

Secrets, real customer data, promises of results, claims you cannot support, or an instruction to pretend to be a person.
