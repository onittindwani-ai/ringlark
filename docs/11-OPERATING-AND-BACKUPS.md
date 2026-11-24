# Operating and backups

## Daily

- Open Follow ups and approvals. Approve or reject drafted texts and emails.
- Open QA review and look at calls marked **Needs a look**. Listen to the real recording in your phone system if you record calls (Ringlark does not store audio).
- Open Overview. Check that the held back list matches what you expect (for example calls waiting for the person's morning).

## Weekly

- Audit page, **Verify the chain**. If it says broken, someone or something changed history. Stop and look.
- Look at Approvals for anything stuck.

## Stopping fast

Press **Pause all** (the kill switch). It stops all dialing and sending at once. To stop even if the web app is down, set `KILL_SWITCH=true` and restart the API and worker.

## Backups

- **SQLite:** stop the app, copy the `.sqlite3` file. Or `sqlite3 ringlark.sqlite3 ".backup backup.sqlite3"` while it runs.
- **Postgres:** `pg_dump --format=custom "$DATABASE_URL_PLAIN" > ringlark.dump` (use the plain `postgresql://` form of the address). `deploy/hetzner/backup.sh` does this for you.
- Also keep a copy of your prompt versions (they are in the database, and you can copy the active one from Agents and prompts).

## Restore (test this once before you need it)

1. Make an empty database.
2. Postgres: `pg_restore --clean --if-exists -d "$DATABASE_URL_PLAIN" ringlark.dump`. SQLite: put the file back.
3. Start the API. Open Audit, **Verify the chain**.

## Logs

The API and worker log to the console. In Docker: `docker compose logs -f api worker`. Logs hold phone numbers. Check them for anything private before you share them.
