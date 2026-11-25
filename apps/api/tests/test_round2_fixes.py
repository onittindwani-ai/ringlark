"""Round 2 audit fixes: a new campaign needs a consent, "booked" needs a booking, the event loop is never held by a vendor, an empty transcript is not
"no answer", an unclear call is read before anyone redials, and a live install without its public address stays in draft."""

import asyncio
import time
from datetime import timedelta

import httpx
import pytest
from sqlalchemy import select

from testkit import NOW, make_settings
from ringlark import dialer
from ringlark.adapters.base import PersonRecord
from ringlark.context import Ctx
from ringlark.models import Agent, Call, Campaign, ConsentRecord, Disposition, FollowUp, QAScore, Target
from ringlark.postcall import EMPTY_TRANSCRIPT_WAIT, process_call, store_turns
from ringlark.toolauth import tool_base_url, tool_token
from sendora_core.models import Event
from sendora_core.settings import Mode
from spies import SpySms, SpyTelephony, SpyVoice
from test_api import TX, a_live_call, client, login, telnyx_post  # noqa: F401
from test_hardening_api import real_client

PROMPT = "You are Sam, an AI assistant calling for Acme Dental. Be brief and kind. Offer the listed times. If the person asks you to stop, stop. " * 2


def real_campaign(c, **extra):
    h = {**c.h, "x-ringlark": "1"}
    agent = c.post("/api/agents", headers=h, json={"name": "Sam", "prompt": PROMPT}).json()
    c.post(f"/api/agents/{agent['id']}/activate", headers=h, json={"version_id": agent["versions"][0]["id"]})
    n = c.post("/api/numbers", headers=h, json={"e164": "+14155550190", "agent_id": agent["id"]}).json()
    camp = c.post("/api/campaigns", headers=h, json={"name": "First", "agent_id": agent["id"], "number_id": n["id"], **extra})
    assert camp.status_code == 200, camp.text
    return h, camp.json()


# ---- 1. a campaign needs a call consent unless the owner says otherwise
def test_a_campaign_made_with_no_flag_requires_consent_and_will_not_dial_a_person_with_none(tmp_path):
    c = real_client(tmp_path)  # MODE=live, demo mode off, a real install
    assert c.ctx.settings.mode is Mode.LIVE
    h, camp = real_campaign(c)  # the body is what the Campaigns page sends: a name and an agent
    assert camp["require_prior_consent"] is True
    rows = [{"phone": "+14155550101", "first_name": "Ava", "timezone": "America/New_York"}, {"phone": "+14155550102", "first_name": "Ben", "timezone": "America/New_York", "call_consent": "yes"}]
    c.post(f"/api/campaigns/{camp['id']}/targets", headers=h, json={"rows": rows})
    assert c.post(f"/api/campaigns/{camp['id']}/start", headers=h).status_code == 200
    with c.ctx.factory() as s:
        res = dialer.dial_tick(s, c.ctx.effective(s), c.ctx.adapters, NOW)
        s.commit()
        assert res.placed == 1 and c.ctx.adapters.telephony.log == [("place", "+14155550102")]  # only the person with a consent on file
        assert res.reasons.get("no_consent_on_file") == 1
    shown = {t["name"]: t["why"] for t in c.get(f"/api/campaigns/{camp['id']}/targets", headers=h).json()}
    assert shown["Ava"] == "no_consent_on_file"


def test_only_the_owner_can_make_a_campaign_that_skips_the_consent_check_and_it_is_audited(client):
    o, a = {**login(client), "x-ringlark": "1"}, {**login(client, "approver@example.test"), "x-ringlark": "1"}
    agent = client.get("/api/agents", headers=o).json()[0]
    body = {"name": "No consent check", "agent_id": agent["id"], "require_prior_consent": False}
    assert client.post("/api/campaigns", headers=a, json=body).status_code == 403
    assert client.post("/api/campaigns", headers=o, json=body).json()["require_prior_consent"] is False
    assert any(e["action"] == "campaign.consent_not_required" for e in client.get("/api/audit", headers=o).json())
    assert client.post("/api/campaigns", headers=a, json={"name": "Plain", "agent_id": agent["id"]}).json()["require_prior_consent"] is True


# ---- 2. booked needs a booking
def test_the_tool_endpoint_downgrades_booked_without_a_booking_and_keeps_it_with_one(client):
    cid, _ = a_live_call(client)
    tok = {"X-Tool-Token": tool_token(client.ctx.settings.session_secret, cid)}
    out = client.post(f"/api/tools/{cid}/end_call", headers=tok, json={"disposition": "booked"}).json()
    assert out["disposition"] == "needs_review"
    with client.ctx.factory() as s:
        assert s.get(Call, cid).disposition == "needs_review"
        assert s.scalars(select(Event).where(Event.kind == "tool.downgraded", Event.entity_id == str(cid))).first()
    cid2, _ = a_live_call(client)
    tok2 = {"X-Tool-Token": tool_token(client.ctx.settings.session_secret, cid2)}
    with client.ctx.factory() as s:
        now = client.ctx.now(s)  # the demo clock, which is what the tool asks the calendar with
    slot = client.ctx.adapters.calendar.slots(now, now + timedelta(days=14))[0].isoformat()
    booked = client.post(f"/api/tools/{cid2}/book_meeting", headers=tok2, json={"slot": slot, "name": "Ava Alder", "email": "ava@example.test"}).json()
    assert booked["ok"], booked
    assert client.post(f"/api/tools/{cid2}/end_call", headers=tok2, json={"disposition": "booked"}).json()["disposition"] == "booked"


# ---- 3. a slow vendor does not hold the event loop
class SlowCrm:
    def find_by_phone(self, phone):
        time.sleep(0.7)
        return None

    def upsert_person(self, person):
        return "slow"

    def healthcheck(self):
        return True, "slow"


class SlowVoice(SpyVoice):
    def create_call(self, **kw):
        time.sleep(0.7)
        return super().create_call(**kw)


async def _health_time_while(client, slow_request) -> float:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=client.app), base_url="http://test") as ac:
        slow = asyncio.create_task(slow_request(ac))
        t0 = time.perf_counter()
        await asyncio.sleep(0.15)  # the slow request is now waiting on its vendor; if it holds the event loop this sleep cannot end until the vendor answers
        r = await ac.get("/health")
        took = time.perf_counter() - t0
        assert r.status_code == 200
        assert (await slow).status_code == 200
        return took


async def test_a_slow_crm_during_a_tool_call_does_not_freeze_other_requests(client):
    cid, _ = a_live_call(client)
    client.ctx.adapters.crm = SlowCrm()
    tok = {"X-Tool-Token": tool_token(client.ctx.settings.session_secret, cid)}
    took = await _health_time_while(client, lambda ac: ac.post(f"/api/tools/{cid}/lookup_crm", headers=tok, json={}))
    assert took < 0.5, f"another request waited {took:.2f}s behind a slow vendor (it is 0.7s when the loop is held)"


async def test_a_slow_voice_engine_while_answering_an_inbound_call_does_not_freeze_other_requests(client):
    client.ctx.adapters.voice = SlowVoice(client.ctx.factory)
    body, h = TX.signed_event("call.initiated", {"direction": "incoming", "from": "+14155550123", "to": "+14155550191", "call_control_id": "v3:slow"})
    took = await _health_time_while(client, lambda ac: ac.post("/api/webhooks/telnyx", content=body, headers=h))
    assert took < 0.5, f"another request waited {took:.2f}s behind a slow vendor (it is 0.7s when the loop is held)"


# ---- 4. an empty transcript, and a call nobody has read
def an_answered_call(s, live_voice):
    camp = s.scalars(select(Campaign)).first()
    t = s.scalars(select(Target).where(Target.status == "new").order_by(Target.id)).first()
    c = Call(campaign_id=camp.id, target_id=t.id, agent_id=camp.agent_id, peer_phone=t.phone, status="in_progress", telnyx_call_id="seed-cc-5", external_id="uv-5", answered_by="human")
    s.add(c); s.flush()
    return c, t


def test_an_empty_transcript_is_read_again_and_then_goes_to_a_person_not_to_no_answer(session, ctx, seeded):
    ctx.settings.demo_mode = False
    ctx.settings.company_name = "Acme Dental"
    ctx.adapters.voice = SpyVoice(ctx.factory)
    c, t = an_answered_call(session, ctx)
    assert process_call(session, ctx, c) == {"skipped": True, "reason": "transcript_empty"} and not c.processed
    assert process_call(session, ctx, c)["reason"] == "transcript_empty"  # still waiting, the call is not closed
    ctx.adapters.voice.transcripts["uv-5"] = [{"speaker": "agent", "text": "Hi, this is Casey, an AI assistant. This call may be recorded.", "start_ms": 0, "end_ms": 2000}, {"speaker": "caller", "text": "Stop calling me", "start_ms": 2200, "end_ms": 3000}]
    r = process_call(session, ctx, c)  # the transcript arrived late: it is read and the stop request is found
    assert r["disposition"] == "do_not_call" and c.processed and t.status == "suppressed"


def test_a_transcript_that_never_comes_is_flagged_for_a_person_and_holds_the_redial_until_it_is_read(session, ctx, seeded):
    ctx.settings.demo_mode = False
    ctx.settings.company_name = "Acme Dental"
    ctx.adapters.voice = SpyVoice(ctx.factory)
    c, t = an_answered_call(session, ctx)
    assert process_call(session, ctx, c)["reason"] == "transcript_empty"
    later = ctx.now(session) + EMPTY_TRANSCRIPT_WAIT + timedelta(seconds=5)
    ctx.now = lambda s: later  # type: ignore[method-assign]
    r = process_call(session, ctx, c)
    assert r["disposition"] == "needs_review" and c.processed and c.status == "completed"
    q = session.scalars(select(QAScore).where(QAScore.call_id == c.id)).one()
    assert q.flagged and q.sampled and not q.reviewed and "No transcript" in q.flag_note
    camp = session.get(Campaign, c.campaign_id)
    t.timezone = "America/New_York"
    # a day later, in the person's hours, with a consent on file: only the unread call stops the redial
    session.add(ConsentRecord(phone=t.phone, kind="call", status="granted", source="test"))
    when = NOW + timedelta(days=1)
    d = dialer.decide(session, ctx.settings, camp, session.get(Agent, camp.agent_id), t, when, 0)
    assert not d.allowed and d.reason == "awaiting_review"
    q.reviewed = True
    d = dialer.decide(session, ctx.settings, camp, session.get(Agent, camp.agent_id), t, when, 0)
    assert d.reason != "awaiting_review"


def test_marking_the_call_as_read_in_the_app_releases_the_person(client):
    h = {**login(client), "x-ringlark": "1"}
    with client.ctx.factory() as s:
        camp = s.scalars(select(Campaign)).first()
        t = s.scalars(select(Target).where(Target.status == "new").order_by(Target.id)).first()
        c = Call(campaign_id=camp.id, target_id=t.id, agent_id=camp.agent_id, peer_phone=t.phone, status="completed", disposition="needs_review", processed=True)
        s.add(c); s.flush()
        s.add(QAScore(call_id=c.id, score=60, checks={}, flagged=True, flag_note="x", sampled=True, reviewed=False))
        s.commit()
        cid, tid = c.id, t.id
    why = {x["id"]: x["why"] for x in client.get(f"/api/campaigns/{camp.id}/targets", headers=h).json()}
    assert why[tid] == "awaiting_review"
    assert client.post(f"/api/qa/{cid}/review", headers=h).status_code == 200
    why = {x["id"]: x["why"] for x in client.get(f"/api/campaigns/{camp.id}/targets", headers=h).json()}
    assert why[tid] != "awaiting_review"


# ---- 6. a live install without its public address stays in draft
LIVE = dict(mode="live", demo_mode=False, telephony_adapter="telnyx", voice_adapter="ultravox", session_secret="test-only-Rt7Kq2Vw9Xm4Zc8Lb3Nf6Hy1Js5Dp0Ga2Ue7", owner_password_hash="x", company_name="Acme Dental")


@pytest.mark.parametrize("missing", ["public_base_url", "telnyx_public_key", "ultravox_webhook_secret"])
def test_live_with_real_adapters_and_a_missing_address_or_key_is_forced_into_draft(tmp_path, factory, missing):
    full = {"public_base_url": "https://ringlark.example.test", "telnyx_public_key": "test-only-key", "ultravox_webhook_secret": "test-only-secret"}
    st = make_settings(tmp_path, **{**LIVE, **{**full, missing: ""}})
    assert any(missing.upper() in p for p in st.identity_problems())
    ctx = Ctx(st, factory, adapters=type("A", (), {})())
    with factory() as s:
        assert ctx.effective(s).mode is Mode.DRAFT
    ok = make_settings(tmp_path, **{**LIVE, **full})
    assert not [p for p in ok.identity_problems() if missing.upper() in p]
    with factory() as s:
        assert Ctx(ok, factory, adapters=type("A", (), {})()).effective(s).mode is Mode.LIVE


def test_an_http_address_is_not_enough_for_the_tool_endpoints(tmp_path):
    st = make_settings(tmp_path, **{**LIVE, "public_base_url": "http://ringlark.example.test", "telnyx_public_key": "test-only-k", "ultravox_webhook_secret": "test-only-s"})
    assert any("PUBLIC_BASE_URL" in p for p in st.identity_problems())


def test_a_call_is_never_placed_with_a_made_up_tool_address(session, ctx, seeded):
    ctx.settings.demo_mode = False
    ctx.settings.company_name = "Acme Dental"
    ctx.settings.public_base_url = ""
    ctx.adapters.telephony, ctx.adapters.voice = SpyTelephony(), SpyVoice(ctx.factory)
    camp = session.get(Campaign, seeded["info"]["campaign_id"])
    camp.require_prior_consent = False
    res = dialer.dial_tick(session, ctx.effective(session), ctx.adapters, NOW)
    assert res.placed == 0 and not ctx.adapters.voice.prompts and ctx.adapters.telephony.log == []  # nothing reached the voice engine
    with pytest.raises(Exception, match="PUBLIC_BASE_URL"):
        tool_base_url(ctx.settings)


# ---- lows
def test_unknown_agent_ids_answer_404_not_500(client):
    h = {**login(client), "x-ringlark": "1"}
    for method, path, body in (("post", "/api/agents/9999/activate", {"version_id": 1}), ("post", "/api/agents/9999/split", {"share_b": 0.1}), ("get", "/api/agents/9999/diff?a=1&b=2", None),
                               ("post", "/api/agents/9999/simulate", {"version_id": 1, "persona_id": "D01"}), ("post", "/api/agents/9999/persona-suite", {"version_id": 1}),
                               ("post", "/api/agents/9999/versions", {"body": "x" * 50})):
        r = getattr(client, method)(path, headers=h, **({"json": body} if body is not None else {}))
        assert r.status_code == 404, (path, r.status_code)


def test_a_booking_that_times_out_is_not_tried_twice_and_never_a_500(client):
    cid, _ = a_live_call(client)
    tok = {"X-Tool-Token": tool_token(client.ctx.settings.session_secret, cid)}
    calls = []

    class Timeout:
        def slots(self, a, b):
            return [NOW + timedelta(days=1)]

        def book(self, **kw):
            calls.append(kw)
            raise httpx.ReadTimeout("slow")

        def healthcheck(self):
            return True, "x"

    client.ctx.adapters.calendar = Timeout()
    slot = (NOW + timedelta(days=1)).isoformat()
    first = client.post(f"/api/tools/{cid}/book_meeting", headers=tok, json={"slot": slot, "name": "Ava Alder", "email": "ava@example.test"})
    assert first.status_code == 200 and first.json()["ok"] is False and first.json()["failed"] is True
    second = client.post(f"/api/tools/{cid}/book_meeting", headers=tok, json={"slot": slot, "name": "Ava Alder", "email": "ava@example.test"})
    assert second.status_code == 200 and second.json()["ok"] is False and len(calls) == 1  # Cal.com may have saved the first one, so it is not asked again
    assert client.post(f"/api/tools/{cid}/end_call", headers=tok, json={"disposition": "booked"}).json()["disposition"] == "needs_review"


def test_a_text_that_times_out_is_not_sent_twice_and_never_a_500(client):
    cid, phone = a_live_call(client)
    with client.ctx.factory() as s:
        t = s.scalars(select(Target).where(Target.phone == phone)).first()
        t.sms_consent, t.timezone = True, "America/New_York"
        s.commit()
    tok = {"X-Tool-Token": tool_token(client.ctx.settings.session_secret, cid)}
    sent = []

    class Flaky(SpySms):
        def send(self, *, to, text):
            sent.append(to)
            raise httpx.ConnectTimeout("slow")

    client.ctx.adapters.sms = Flaky()
    client.ctx.settings.demo_mode = True  # the in call text checks the hour with the demo clock; the offline calendar keeps its clock
    with client.ctx.factory() as s:
        from ringlark import clock
        clock.set_offset(s, 0)
        s.commit()
    r1 = client.post(f"/api/tools/{cid}/send_sms", headers=tok, json={"kind": "callback"})
    r2 = client.post(f"/api/tools/{cid}/send_sms", headers=tok, json={"kind": "callback"})
    assert r1.status_code == 200 and r2.status_code == 200 and r2.json()["ok"] is False
    assert len(sent) == 1  # exactly the one try: the first request reached the vendor, the second never did
    with client.ctx.factory() as s:
        assert s.scalars(select(FollowUp).where(FollowUp.call_id == cid, FollowUp.status == "sent")).first() is None
