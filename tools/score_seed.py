"""Check the dialing rules find every planted problem in the seed data, at the fixed time in data/answer_key.json.

    python tools/score_seed.py        prints PASS or FAIL for each planted problem and exits 1 on any FAIL
"""

from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import _common  # noqa: F401
from ringlark import dialer
from ringlark.config import Settings
from ringlark.models import Agent, Call, Campaign, Target
from ringlark.seeding import DEFAULT_DATA, load_seed, read_seed
from sendora_core import models as _core  # noqa: F401
from sendora_core.db import Base, make_engine, make_session_factory
from sqlalchemy import select


def score(data_dir: Path | None = None) -> dict:
    data = data_dir or DEFAULT_DATA
    key = json.loads((data / "answer_key.json").read_text())
    now = datetime.fromisoformat(key["now_utc"])
    with tempfile.TemporaryDirectory() as d:
        s = Settings(_env_file=None, database_url=f"sqlite:///{d}/score.sqlite3", mode="live", demo_mode=True, handoff_dir=d)
        engine = make_engine(s.database_url)
        Base.metadata.create_all(engine)
        with make_session_factory(engine)() as session:
            info = load_seed(session, read_seed(data), now)
            session.flush()
            camp = session.get(Campaign, info["campaign_id"])
            agent = session.get(Agent, camp.agent_id)
            found: dict[str, list[str]] = {}
            for t in session.scalars(select(Target).order_by(Target.id)):
                dec = dialer.decide(session, s, camp, agent, t, now, 0)
                found.setdefault(dec.reason, []).append(t.phone)
            dup = info["import"].duplicates
    planted = key["planted"]
    got = {"bad_number": len(found.get("bad_number", [])), "unknown_timezone": len(found.get("unknown_timezone", [])), "do_not_call": len(found.get("do_not_call", [])),
           "consent_revoked": len(found.get("consent_revoked", [])), "duplicate_phone": dup, "max_attempts": len(found.get("max_attempts", [])), "retry_same_day": len(found.get("retry_same_day", []))}
    rows = [{"problem": k, "planted": planted[k], "found": got[k], "pass": planted[k] == got[k]} for k in planted]
    return {"rows": rows, "ok_to_call_now": len(found.get("ok", [])), "outside_hours_now": len(found.get("outside_hours", [])), "all_pass": all(r["pass"] for r in rows)}


def main() -> int:
    r = score()
    for row in r["rows"]:
        print(f"{'PASS' if row['pass'] else 'FAIL'} {row['problem']}: planted {row['planted']}, found {row['found']}")
    print(f"ok to call at the fixed time: {r['ok_to_call_now']}, closed for the person's local time: {r['outside_hours_now']}")
    return 0 if r["all_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
