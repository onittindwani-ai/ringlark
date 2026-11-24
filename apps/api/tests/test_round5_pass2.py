"""Fixes found by walking every screen as a first time owner (round 5, second pass)."""

from sqlalchemy import select

from ringlark import postcall
from ringlark.models import Call, FollowUp, Target

from test_api import client, login  # noqa: F401  (the fixture and the sign in helper)


def _targets(client, h, cid):
    return {t["id"]: t for t in client.get(f"/api/campaigns/{cid}/targets", headers=h).json()}


def test_a_person_who_already_booked_or_finished_is_not_listed_as_callable(client):
    h = login(client)
    cid = client.get("/api/campaigns", headers=h).json()[0]["id"]
    with client.ctx.factory() as s:
        booked = s.scalars(select(Target).where(Target.campaign_id == cid, Target.status == "booked")).first()
        done = s.scalars(select(Target).where(Target.campaign_id == cid, Target.status == "done")).first()
        assert booked and done
        ids = (booked.id, done.id)
    ts = _targets(client, h, cid)
    assert (ts[ids[0]]["can_call_now"], ts[ids[0]]["why"]) == (False, "person_booked")
    assert (ts[ids[1]]["can_call_now"], ts[ids[1]]["why"]) == (False, "person_done")
    # Nobody who is listed as callable has a finished status: the dialer would never pick them up.
    assert all(t["status"] in ("new", "queued", "contacted") for t in ts.values() if t["can_call_now"])


def test_people_of_a_campaign_that_is_not_running_are_not_callable_yet(client):
    h = login(client)
    agent = client.get("/api/agents", headers=h).json()[0]
    c = client.post("/api/campaigns", headers=h, json={"name": "Not started", "agent_id": agent["id"]}).json()
    client.post(f"/api/campaigns/{c['id']}/targets", headers=h, json={"rows": [{"phone": "+14155559901", "timezone": "America/New_York"}]})
    why = {t["why"] for t in client.get(f"/api/campaigns/{c['id']}/targets", headers=h).json()}
    assert "ok" not in why
    assert "campaign_not_running" in why or why <= {"outside_hours", "daily_cap", "retry_same_day"} | {"kill_switch", "draft_mode"}
    client.post(f"/api/campaigns/{c['id']}/start", headers=h)
    again = {t["why"] for t in client.get(f"/api/campaigns/{c['id']}/targets", headers=h).json()}
    assert "campaign_not_running" not in again


def test_the_call_log_search_finds_a_name_and_a_number_written_by_hand(client):
    h = login(client)
    rows = client.get("/api/calls?limit=500", headers=h).json()
    named = next(r for r in rows if r["name"])
    first = named["name"].split()[0]
    by_name = client.get("/api/calls", params={"q": first.lower(), "limit": 500}, headers=h).json()
    assert by_name and all(first.lower() in r["name"].lower() or first in r["phone"] for r in by_name)
    assert named["id"] in {r["id"] for r in by_name}
    digits = named["phone"][2:]  # without +1
    pretty = f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    by_phone = client.get("/api/calls", params={"q": pretty, "limit": 500}, headers=h).json()
    assert named["id"] in {r["id"] for r in by_phone}
    # A percent sign is text, not a wildcard.
    assert client.get("/api/calls", params={"q": "%"}, headers=h).json() == []


def test_the_same_follow_up_is_not_drafted_twice_for_one_person(client):
    h = login(client)
    with client.ctx.factory() as s:
        t = s.scalars(select(Target).where(Target.sms_consent.is_(True), Target.status == "new")).first()
        assert t is not None
        calls = []
        for i in range(2):
            c = Call(campaign_id=t.campaign_id, target_id=t.id, agent_id=1, direction="outbound", peer_phone=t.phone, status="completed")
            s.add(c); s.flush(); calls.append(c)
        n1 = postcall._followups(s, client.ctx, calls[0], t, "interested_callback")
        n2 = postcall._followups(s, client.ctx, calls[1], t, "interested_callback")
        s.commit()
        waiting = s.scalars(select(FollowUp).where(FollowUp.to == t.phone, FollowUp.status == "pending")).all()
    assert (n1, n2) == (1, 0) and len(waiting) == 1
    fu = client.get("/api/followups", headers=h).json()
    mine = next(f for f in fu if f["to"] == t.phone)
    assert mine["name"] == f"{t.first_name} {t.last_name}".strip()
    approvals = client.get("/api/approvals", headers=h).json()
    assert any(a["summary"] == "Send a text message follow up" for a in approvals)
    assert not any("a sms" in a["summary"].lower() for a in approvals)
