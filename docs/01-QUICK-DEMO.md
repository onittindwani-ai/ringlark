# Quick demo (about 10 minutes)

You will run the whole product on your own computer with fictional people and an offline stand in agent. No call is placed. No accounts, no keys.

## Before you start

You need Python 3.12 or newer (or uv), Node 22 or newer, pnpm (`corepack enable` or `npm i -g pnpm`), and Google Chrome (only for the optional automated tests). About 2 GB of free disk space.

## Steps

1. Open a terminal in the project folder.
2. Make a Python environment and install: `python3.12 -m venv .venv`, then `.venv/bin/pip install -e packages/core-py -e "apps/api[dev]"`. No python3.12 on your Mac? Use uv instead: `uv venv --python 3.12 .venv`, then `uv pip install --python .venv/bin/python -e packages/core-py -e "apps/api[dev]"`. Or just run `make install`.
3. Install and build the web part: `pnpm install`, then `pnpm build`. If you change code later, build again, because the start command serves the last build.
4. Start the API in demo mode. In one terminal run:
   `MODE=live DEMO_MODE=true DATABASE_URL=sqlite:///./demo.sqlite3 SESSION_SECRET=demo-secret-not-for-real-use-1234 .venv/bin/python -m uvicorn ringlark.api.app:app_from_env --factory --port 8000 --proxy-headers`
   (Demo mode builds only offline adapters, so MODE=live here still cannot call or text anyone.)
5. Start the web app in a second terminal: `API_BASE_URL=http://127.0.0.1:8000 INSECURE_COOKIES=1 NEXT_PUBLIC_DEMO_HINT=1 pnpm --filter web start`.
6. Open http://localhost:3000. Sign in with `owner@example.test` and the demo password `demo-password-1`. It works only while `DEMO_MODE=true`.
7. Press Cmd+K (Ctrl+K on Windows or Linux), choose **Reset the demo data**, and confirm. This loads a fictional dental practice, 52 people (the file has 55 rows and 3 are duplicates, which are skipped), 2 agents and 30 earlier calls.
8. In the blue demo strip press **Run now**. Calls are placed to the fake phone. Press **+1 day** and **Run now** again. The Overview shows who was held back and why.
9. Open **Live console**, pick a call and press play. The waveform, the transcript and the agent state move together. Press **4x** to go faster. Try **Take over**.
10. Open **Call log**, open a call and drag the scrubber. The transcript follows.
11. Open **Agents and prompts**, change a line of the prompt, save (a new version is made), look at the compare view, then open **Simulator and persona suite** and run the suite. You get a score with the failures listed.
12. Open **Follow ups and approvals** and approve a text. It is sent on the next run (press **Run now**), and in demo mode it goes to the fake outbox.
13. Open **Numbers and compliance**, add a number to the do not call list, run again and see it held back.
14. Press **Pause all**. Everything stops. Press **Turn it off** to resume.

## What to look at

- Run `python tools/score_seed.py`. It checks that the 19 planted problem rows (bad numbers, wrong time zones, do not call, revoked consent, duplicates, too many tries, already tried today) were all held back.
- The agent here is a set of rules, not a language model. Every screen that shows it says so.

## If something fails

See `15-TROUBLESHOOTING.md`.
