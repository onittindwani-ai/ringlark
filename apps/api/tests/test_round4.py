"""Round 4 audit fixes. Every test here fails on the code before the fix.

H1 the voice model is told the open times, and has a tool for them. H2 a vendor failure is not an attempt on the person, and the dialer stops after a few in a row.
M3 a CRM outage never drops a note. M4 an unreadable country list allows nobody. M5 an unreadable vendor answer is an unknown outcome, never a crash.
M6 the documented setup path exists. M7 withheld callers have their own limit. M8 a voicemail is spoken after the beep. M9 time zone against area code. And the smaller findings."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from sqlalchemy import func, select

from testkit import NOW, make_settings
from ringlark import areacodes, compliance, crmsync, dialer, disclosure, intake, live, times
from ringlark.adapters.base import BadReply, UnknownOutcome
from ringlark.adapters.calcom import CalcomCalendar
from ringlark.adapters.crm import TwentyCrm
from ringlark.adapters.telnyx import TelnyxCalls, TelnyxSms, encode_state
from ringlark.adapters.ultravox import UltravoxVoice, tool_definitions
from ringlark.context import set_state
from ringlark.jobs import job_dial_tick
from ringlark.live_prompt import live_system_prompt
from ringlark.models import Agent, Call, CallAction, Campaign, Disposition, FollowUp, Number, QAScore, State, Suppression, Target
from ringlark.tools import ToolService
from ringlark.toolauth import tool_token
from sendora_core.adapters import AdapterError
from sendora_core.models import AuditEntry, Event
from spies import SpyCrm, SpyTelephony, SpyVoice
from test_api import a_live_call, client, login, telnyx_post  # noqa: F401
from test_engine import a_call
from test_hardening_api import real_client
from test_hardening_dialer import live_ctx

ROOT = Path(__file__).resolve().parents[3]


def tick(session, ctx, minutes: float = 0, days: float = 0):
    return dialer.dial_tick(session, ctx.effective(session), ctx.adapters, NOW + timedelta(minutes=minutes, days=days))


def vendor(handler):
    return httpx.Client(transport=httpx.MockTransport(handler), base_url="https://vendor.example.test")


def reply(status=200, body=None, raw=None):
    return lambda request: httpx.Response(status, json=body) if raw is None else httpx.Response(status, content=raw, headers={"content-type": "application/json"})


# ---- H1. the voice model is told the open times and has a tool to ask for them
def calendar_times(ctx):
    return ctx.adapters.calendar.slots(NOW, NOW + timedelta(days=14))


def test_the_prompt_of_a_real_outbound_call_carries_the_open_times_with_their_offset(session, ctx, seeded):
    live_ctx(ctx)
    res = tick(session, ctx)
    assert res.placed > 0
    prompt = ctx.adapters.voice.prompts[0]
    first = calendar_times(ctx)[0]
    assert first.isoformat() in prompt and "list_times" in prompt and "+00:00" in prompt  # the exact value book_meeting takes, and where to ask for more
    assert re.search(r"(Tuesday|Wednesday|Thursday|Friday) \w+ \d+ at \d+:\d\d (AM|PM) [A-Z]{2,4}: 2026-", prompt)  # said aloud in the person's own zone, then the value


def test_the_open_times_are_said_in_the_persons_own_time_zone(session, ctx, seeded):
    live_ctx(ctx)
    offered = times.offer([datetime(2026, 12, 2, 15, 0, tzinfo=UTC)], "America/Los_Angeles")
    assert offered[0].slot == "2026-12-02T15:00:00+00:00" and offered[0].say == "Wednesday December 2 at 7:00 AM PST"


def test_an_inbound_call_gets_the_open_times_too(session, ctx, seeded):
    live_ctx(ctx)
    num = session.scalars(select(Number).where(Number.agent_id.is_not(None))).first()
    assert live.handle_inbound(session, ctx, ctx.effective(session), {"to": num.e164, "from": "+14155550123", "call_control_id": "v3:t1"}) == "answered"
    assert "list_times" in ctx.adapters.voice.prompts[0] and "T" in ctx.adapters.voice.prompts[0] and "+00:00" in ctx.adapters.voice.prompts[0]


def test_a_calendar_that_is_down_does_not_stop_the_call_and_the_prompt_says_to_ask(session, ctx, seeded):
    live_ctx(ctx)

    class Down:
        def slots(self, a, b):
            raise httpx.ReadTimeout("Cal.com does not answer")

    ctx.adapters.calendar = Down()
    res = tick(session, ctx)
    assert res.placed > 0
    assert "No open times could be loaded" in ctx.adapters.voice.prompts[0] and "list_times" in ctx.adapters.voice.prompts[0]


def test_the_calendar_is_asked_once_per_tick_not_once_per_call(session, ctx, seeded):
    live_ctx(ctx)
    asked = []
    real = ctx.adapters.calendar

    class Counting:
        def slots(self, a, b):
            asked.append(1)
            return real.slots(a, b)

    ctx.adapters.calendar = Counting()
    assert tick(session, ctx).placed > 3 and len(asked) == 1


def test_the_prompt_without_times_says_none_were_loaded_and_with_an_empty_calendar_says_not_to_offer():
    assert "No open times could be loaded" in live_system_prompt("Be kind.", "Ava")
    assert "no open times in the next two weeks" in live_system_prompt("Be kind.", "Ava", [])


def test_list_times_is_a_tool_the_voice_engine_can_call(client):
    names = [t["temporaryTool"]["modelToolName"] for t in tool_definitions("https://app.example.test", 1, "tok")]
    assert "list_times" in names
    cid, _ = a_live_call(client)
    tok = {"X-Tool-Token": tool_token(client.ctx.settings.session_secret, cid)}
    r = client.post(f"/api/tools/{cid}/list_times", headers=tok, json={})
    assert r.status_code == 200 and r.json()["ok"] is True
    got = r.json()["times"]
    assert got and all(re.search(r"[+-]\d\d:\d\d$", t["slot"]) and t["say"] for t in got)


def test_booking_with_a_time_that_has_no_offset_is_refused_and_the_open_times_come_back(session, ctx, seeded):
    c, t = a_call(session, seeded)
    svc = ToolService(session, ctx, c)
    svc.now = NOW
    offered = calendar_times(ctx)
    naive = offered[0].replace(tzinfo=None).isoformat()  # the hour is right, the offset is missing: it would be read as UTC
    out = svc.run("book_meeting", {"slot": naive, "name": "Ava", "email": "ava@example.test"})
    assert out["ok"] is False and "offset" in out["say"] and [x["slot"] for x in out["times"]] == [x.isoformat() for x in offered]
    assert svc.run("book_meeting", {"slot": offered[0].isoformat(), "name": "Ava", "email": "ava@example.test"})["ok"] is True


def test_a_time_that_is_not_offered_is_refused_with_the_times_that_are_open(session, ctx, seeded):
    c, t = a_call(session, seeded)
    svc = ToolService(session, ctx, c)
    svc.now = NOW
    out = svc.run("book_meeting", {"slot": "2026-12-03T03:00:00+00:00", "name": "Ava", "email": "ava@example.test"})
    assert out["ok"] is False and out["times"] and "The open times are:" in out["say"]


def test_list_times_with_a_calendar_that_is_down_is_a_plain_answer_and_an_empty_calendar_says_so(session, ctx, seeded):
    c, t = a_call(session, seeded)

    class Down:
        def slots(self, a, b):
            raise httpx.ConnectError("down")

    ctx.adapters.calendar = Down()
    out = ToolService(session, ctx, c).run("list_times", {})
    assert out["ok"] is False and out["failed"] is True

    class Empty:
        def slots(self, a, b):
            return []

    ctx.adapters.calendar = Empty()
    out = ToolService(session, ctx, c).run("list_times", {})
    assert out["ok"] is True and out["times"] == [] and "no open times" in out["say"]


# ---- H2. a vendor failure before the phone rings is not an attempt, and the tick stops after a few in a row
def attempts(session):
    return [dialer.history(session, t, t.timezone)[0] for t in session.scalars(select(Target))]


def test_a_voice_engine_outage_makes_a_few_calls_not_all_of_them_and_keeps_every_try(session, ctx, seeded):
    live_ctx(ctx)
    base, held = attempts(session), set(session.scalars(select(Target.id).where(Target.status == "suppressed")))
    ctx.adapters.voice.fail = True
    first = tick(session, ctx)
    assert ctx.adapters.voice.n == 3 and first.placed == 0 and "vendor_trouble" in first.reasons and "Check the Integrations page" in first.trouble  # not 33
    assert not any(a == "place" for a, _ in ctx.adapters.telephony.log)
    assert attempts(session) == base  # none of the failed calls is an attempt on a person
    for d in range(4):  # four days of outage: nobody is used up
        tick(session, ctx, days=d)
    assert set(session.scalars(select(Target.id).where(Target.status == "suppressed"))) == held and attempts(session) == base


def test_the_dialer_rests_after_the_failures_and_goes_on_when_the_vendor_is_back(session, ctx, seeded):
    live_ctx(ctx)
    ctx.adapters.voice.fail = True
    tick(session, ctx)
    n = ctx.adapters.voice.n
    rest = tick(session, ctx, minutes=5)
    assert ctx.adapters.voice.n == n and rest.reasons == {"vendor_paused": 1}  # no vendor is asked while it rests
    ctx.adapters.voice.fail = False
    back = tick(session, ctx, minutes=12)
    assert back.placed > 0 and session.get(State, "dial_trouble").value == ""  # a call that went through clears the problem


def test_the_trouble_is_shown_on_the_overview_and_in_the_held_back_list(client):
    from ringlark.metrics import overview

    with client.ctx.factory() as s:
        assert overview(s, NOW)["dial_trouble"] is None
        set_state(s, "dial_trouble", '{"since": "x", "why": "3 calls in a row could not be placed"}')
        s.commit()
        assert "3 calls in a row" in overview(s, NOW)["dial_trouble"]


def test_the_limit_is_a_setting_and_a_refusal_by_the_phone_company_is_not_an_attempt_but_an_unknown_answer_is(session, ctx, seeded):
    live_ctx(ctx)
    base = attempts(session)
    ctx.settings.dial_failure_limit = 1
    ctx.adapters.telephony.fail = True  # Telnyx refuses at once: nothing rang
    tick(session, ctx)
    assert attempts(session) == base and session.scalars(select(Call).where(Call.blocked_reason == "place_failed")).first()

    class Unclear(SpyTelephony):
        def place_call(self, **kw):
            raise UnknownOutcome("Telnyx answered 503")  # it may have rung

    ctx.adapters.telephony = Unclear()
    tick(session, ctx, minutes=30)
    odd = session.scalars(select(Call).where(Call.blocked_reason == "place_unconfirmed")).all()
    assert len(odd) == 1 and sum(attempts(session)) == sum(base) + 1  # this one counts: the phone may have rung


def test_a_person_held_back_by_failures_can_be_put_back_by_the_owner_and_nobody_else(tmp_path):
    c = real_client(tmp_path)
    h = {**c.h, "x-ringlark": "1"}
    with c.ctx.factory() as s:
        agent = Agent(name="Sam"); s.add(agent); s.flush()
        camp = Campaign(name="C", agent_id=agent.id, status="running"); s.add(camp); s.flush()
        base = dict(campaign_id=camp.id, timezone="America/New_York", status="suppressed")
        failed_out = Target(phone="+12125550101", **base)
        on_dnc = Target(phone="+12125550102", **base)
        really_used = Target(phone="+12125550103", **base)
        s.add_all([failed_out, on_dnc, really_used]); s.flush()
        s.add(Suppression(phone="+12125550102", reason="asked", source="test"))
        for i in range(3):  # three real attempts: the person used their tries
            s.add(Call(campaign_id=camp.id, target_id=really_used.id, agent_id=agent.id, peer_phone=really_used.phone, status="completed", created_at=NOW - timedelta(days=i + 1)))
        for i in range(3):  # three vendor failures: these do not count
            s.add(Call(campaign_id=camp.id, target_id=failed_out.id, agent_id=agent.id, peer_phone=failed_out.phone, status="failed", blocked_reason="place_failed", created_at=NOW - timedelta(days=i + 1)))
        s.commit()
        cid, fid, did, uid = camp.id, failed_out.id, on_dnc.id, really_used.id
    out = c.post(f"/api/campaigns/{cid}/targets/restore", headers=h, json={}).json()
    assert out["restored"] == [fid] and out["skipped"] == {"do_not_call": 1, "max_attempts": 1}
    with c.ctx.factory() as s:
        assert s.get(Target, fid).status == "new" and s.get(Target, did).status == "suppressed" and s.get(Target, uid).status == "suppressed"
        assert s.scalar(select(func.count()).select_from(AuditEntry).where(AuditEntry.action == "targets.restored")) == 1
    assert c.post(f"/api/campaigns/{cid}/targets/restore", json={}).status_code in (401, 403)


def test_the_daily_cap_counts_from_the_business_midnight_not_from_utc(session, ctx, seeded):
    camp = session.get(Campaign, seeded["info"]["campaign_id"])
    late = datetime(2026, 12, 1, 3, 0, tzinfo=UTC)  # 22:00 in New York the evening before
    session.add(Call(campaign_id=camp.id, agent_id=camp.agent_id, status="completed", peer_phone="+12125550100", created_at=late))
    session.flush()
    assert dialer.calls_today(session, camp.id, NOW) >= 1  # by UTC midnight it is today
    assert dialer.calls_today(session, camp.id, NOW, "America/New_York") == dialer.calls_today(session, camp.id, NOW, "UTC") - 1  # by New York midnight it is yesterday
    assert dialer.day_start(NOW, "America/New_York") == datetime(2026, 12, 1, 5, 0, tzinfo=UTC)


# ---- M3. a CRM outage never costs a note
def queued_calls(session, seeded, n=13):
    camp = session.get(Campaign, seeded["info"]["campaign_id"])
    t = session.scalars(select(Target).order_by(Target.id)).first()
    rows = []
    for i in range(n):
        c = Call(campaign_id=camp.id, target_id=t.id, agent_id=camp.agent_id, peer_phone=t.phone, status="completed", summary=f"note {i + 1}")
        session.add(c); session.flush(); rows.append(c)
    session.commit()
    return rows


def test_the_queue_is_worked_in_the_order_the_calls_were_saved_by_number_not_by_text(session, ctx, seeded):
    live_ctx(ctx)
    rows = queued_calls(session, seeded)
    by_id = {c.id: c for c in rows}
    for cid in (rows[12].id, rows[8].id, rows[9].id):  # the 13th, 9th and 10th calls: as text "10" and "13" sort before "9"
        crmsync.queue(session, by_id[cid])
    session.commit()
    spy = SpyCrm()
    ctx.adapters.crm = spy
    assert crmsync.flush(session, ctx)["written"] == 3
    assert [w.extra["note"] for w in spy.writes] == ["note 9", "note 10", "note 13"]


class Refusing(SpyCrm):
    def upsert_person(self, person):
        raise AdapterError("Twenty said: the field is not allowed")


def test_notes_a_crm_refuses_give_up_after_three_tries_into_a_list_that_is_kept_and_can_be_retried(session, ctx, seeded):
    live_ctx(ctx)
    c = queued_calls(session, seeded, 1)[0]
    crmsync.queue(session, c); session.commit()
    ctx.adapters.crm = Refusing()
    results = [crmsync.flush(session, ctx) for _ in range(3)]
    assert [r["gave_up"] for r in results] == [0, 0, 1]
    assert [d["call_id"] for d in crmsync.dead_letters(session)] == [c.id] and "AdapterError" in crmsync.dead_letters(session)[0]["why"]
    assert session.scalar(select(func.count()).select_from(State).where(State.key == f"crm_pending:{c.id}")) == 0
    good = SpyCrm()
    ctx.adapters.crm = good
    assert crmsync.retry_dead(session, c.id) is True and crmsync.dead_letters(session) == []
    assert crmsync.flush(session, ctx)["written"] == 1 and len(good.writes) == 1


def test_a_note_that_waited_more_than_a_week_goes_to_the_dead_letters_and_the_owner_can_requeue_it(client):
    o = {**login(client), "x-ringlark": "1"}
    with client.ctx.factory() as s:
        t = s.scalars(select(Target)).first()
        camp = s.scalars(select(Campaign)).first()
        c = Call(campaign_id=camp.id, target_id=t.id, agent_id=camp.agent_id, peer_phone=t.phone, status="completed", summary="old note")
        s.add(c); s.flush()
        set_state(s, f"crm_pending:{c.id}", f"0|{(datetime.now(UTC) - timedelta(days=8)).isoformat()}")
        s.commit()
        cid = c.id
        out = crmsync.flush(s, client.ctx)
        s.commit()
        assert out["gave_up"] == 1
    listed = client.get("/api/crm/dead-letters", headers=o).json()
    assert [d["call_id"] for d in listed] == [cid] and listed[0]["why"] == "waited_too_long"
    assert client.get("/api/overview", headers=o).json()["crm_dead_letters"] == 1
    assert client.post(f"/api/crm/dead-letters/{cid}/retry", headers=o).status_code == 200
    assert client.post(f"/api/crm/dead-letters/{cid}/retry", headers=o).status_code == 404
    assert client.get("/api/crm/dead-letters", headers=o).json() == []


def test_an_unreadable_crm_answer_for_one_note_does_not_block_the_notes_after_it(session, ctx, seeded):
    live_ctx(ctx)
    rows = queued_calls(session, seeded, 3)
    for c in rows:
        crmsync.queue(session, c)
    session.commit()

    class Poison(SpyCrm):
        def upsert_person(self, person):
            if person.extra["note"] == "note 1":
                raise BadReply("Twenty sent an answer that is not JSON")
            return super().upsert_person(person)

    ctx.adapters.crm = Poison()
    out = crmsync.flush(session, ctx)
    assert out["written"] == 2 and out["left"] == 1  # the poison row stays, the others went through


# ---- M4. a country list that cannot be read allows nobody
@pytest.mark.parametrize("value", ["", "  ", "1,44", "US", "+", "+abc", "+12345", "usa, canada"])
def test_an_empty_or_unreadable_country_list_allows_no_country_and_says_so(tmp_path, value):
    st = make_settings(tmp_path, allowed_calling_countries=value)
    assert st.calling_codes == ()
    assert any("ALLOWED_CALLING_COUNTRIES" in p and "call nobody" in p for p in st.problems())
    assert compliance.country_allowed("+2348031234567", st.calling_codes) is False and compliance.country_allowed("+14155550100", st.calling_codes) is False


def test_a_list_with_one_bad_entry_keeps_the_good_ones_and_names_the_bad_one(tmp_path):
    st = make_settings(tmp_path, allowed_calling_countries="+1, 44 ,+1876")
    assert st.calling_codes == ("+1", "+1876") and any("(44)" in p for p in st.problems())
    assert not make_settings(tmp_path).calling_problems()


def test_the_dialer_calls_nobody_when_the_list_is_empty_and_places_no_call_to_a_nigerian_number(session, ctx, seeded):
    live_ctx(ctx)
    ctx.settings.allowed_calling_countries = ""
    camp = session.get(Campaign, seeded["info"]["campaign_id"])
    agent = session.get(Agent, camp.agent_id)
    ng = Target(phone="+2348031234567", first_name="X", timezone="Africa/Lagos", campaign_id=camp.id)
    session.add(ng); session.flush()
    assert dialer.decide(session, ctx.settings, camp, agent, ng, NOW, 0).reason == "country_not_allowed"
    res = tick(session, ctx)
    assert res.placed == 0 and res.reasons.get("country_not_allowed", 0) > 0 and not ctx.adapters.telephony.log


# ---- M5. a vendor reply nobody can read is an unknown outcome, never a crash
def calcom(tmp_path, handler):
    st = make_settings(tmp_path, calcom_api_key="test-only-key", calcom_event_type_id=1)
    return CalcomCalendar(st, vendor(handler))


BAD_BODIES = [dict(raw=b"<html>gateway</html>"), dict(body={}), dict(body={"data": None}), dict(body={"data": []}), dict(body={"data": {"start": 5}})]


@pytest.mark.parametrize("bad", BAD_BODIES)
def test_calcom_reads_no_unreadable_answer_as_a_booking_or_a_list_of_times(tmp_path, bad):
    cal = calcom(tmp_path, reply(**bad))
    with pytest.raises(BadReply):
        cal.book(start=NOW, name="Ava", email="ava@example.test", timezone="UTC")
    with pytest.raises(AdapterError):  # a read: a plain failure the caller turns into "no times"
        cal.slots(NOW, NOW + timedelta(days=3))


def test_a_booking_answered_with_an_unreadable_body_is_flagged_unconfirmed_and_never_repeated(tmp_path, session, ctx, seeded):
    c, t = a_call(session, seeded)
    ctx.adapters.calendar = calcom(tmp_path, reply(body={"status": "success"}))  # a 2xx with no data
    ctx.adapters.calendar.slots = lambda a, b: [NOW + timedelta(days=1)]
    svc = ToolService(session, ctx, c)
    svc.now = NOW
    args = {"slot": (NOW + timedelta(days=1)).isoformat(), "name": "Ava", "email": "ava@example.test"}
    out = svc.run("book_meeting", args)
    assert out["ok"] is False and out["failed"] is True and "could not confirm" in out["say"]  # not a 500
    assert session.scalar(select(Event.id).where(Event.kind == "meeting.unconfirmed", Event.entity_id == str(c.id))) is not None
    assert session.scalar(select(CallAction.id).where(CallAction.call_id == c.id, CallAction.kind == "book_meeting")) is not None  # the claim stays: no second booking on this call
    assert svc.run("book_meeting", args)["ok"] is False
    end = ToolService(session, ctx, c).run("end_call", {"disposition": "booked"})
    assert end["disposition"] == "needs_review"
    note = session.scalars(select(Disposition).where(Disposition.call_id == c.id)).one().note
    assert "could not be confirmed" in note and "no booking was made" not in note  # it says check the calendar, not that nothing was booked


def test_the_tool_endpoint_answers_200_when_cal_com_sends_an_unreadable_booking(client):
    cid, _ = a_live_call(client)
    st = client.ctx.settings
    when = datetime.now(UTC) + timedelta(days=1)
    client.ctx.adapters.calendar = CalcomCalendar(st.model_copy(update={"calcom_api_key": "k", "calcom_event_type_id": 1}), vendor(reply(body={"ok": True})))
    client.ctx.adapters.calendar.slots = lambda a, b: [when]
    slot = when.isoformat()
    tok = {"X-Tool-Token": tool_token(st.session_secret, cid)}
    r = client.post(f"/api/tools/{cid}/book_meeting", headers=tok, json={"slot": slot, "name": "Ava", "email": "ava@example.test"})
    assert r.status_code == 200 and r.json()["failed"] is True


@pytest.mark.parametrize("bad", [dict(raw=b"not json"), dict(body=[]), dict(body={"data": {"people": {}}}), dict(body={"data": {"people": {"edges": [5]}}}), dict(body={"data": None})])
def test_twenty_reads_no_unreadable_answer_and_never_lets_a_key_error_out(tmp_path, bad):
    crm = TwentyCrm(make_settings(tmp_path, twenty_base_url="https://crm.example.test", twenty_api_key="k"), vendor(reply(**bad)))
    with pytest.raises(UnknownOutcome):
        crm.find_by_phone("+14155550100")


def test_twenty_create_answered_without_an_id_is_an_unknown_outcome(tmp_path):
    from ringlark.adapters.base import PersonRecord

    def handler(request):
        body = request.content.decode()
        if "FindByPhone" in body:
            return httpx.Response(200, json={"data": {"people": {"edges": []}}})
        return httpx.Response(200, json={"data": {"createPerson": {}}})

    crm = TwentyCrm(make_settings(tmp_path, mode="live", twenty_base_url="https://crm.example.test", twenty_api_key="k"), vendor(handler))
    with pytest.raises(UnknownOutcome):
        crm.upsert_person(PersonRecord(first_name="A", phone="+14155550100"))


@pytest.mark.parametrize("bad", [dict(raw=b"{"), dict(body={}), dict(body={"data": {}}), dict(body={"data": "x"})])
def test_telnyx_texts_and_calls_with_unreadable_answers_are_unknown_outcomes(tmp_path, bad):
    st = make_settings(tmp_path, telnyx_from_number="+14155550190", public_base_url="https://app.example.test")
    with pytest.raises(UnknownOutcome):
        TelnyxSms(st, vendor(reply(**bad))).send(to="+14155550123", text="x")  # the text may have gone out
    with pytest.raises(UnknownOutcome):
        TelnyxCalls(st, vendor(reply(**bad))).place_call(to="+14155550123", from_number="+14155550190", client_state="x", amd=False)  # the phone may be ringing


def test_a_text_the_phone_company_answered_unreadably_is_held_as_unconfirmed_not_resent(session, ctx, seeded):
    c, t = a_call(session, seeded)
    t.sms_consent = True
    st = ctx.settings.model_copy(update={"telnyx_from_number": "+14155550190"})
    t.timezone = "America/New_York"
    ctx.adapters.sms = TelnyxSms(st, vendor(reply(body={"data": {}})))
    svc = ToolService(session, ctx, c)
    svc.now = NOW
    out = svc.run("send_sms", {"kind": "callback"})
    assert out["ok"] is False and out["failed"] is True
    fu = session.scalars(select(FollowUp).where(FollowUp.call_id == c.id)).one()
    assert fu.blocked_reason == "send_unconfirmed" and fu.status == "blocked"


@pytest.mark.parametrize("bad", [dict(raw=b"nope"), dict(body={}), dict(body=[1])])
def test_ultravox_with_unreadable_answers_fails_plainly(tmp_path, bad):
    v = UltravoxVoice(make_settings(tmp_path), vendor(reply(**bad)))
    with pytest.raises(AdapterError):
        v.create_call(system_prompt="x" * 50, voice="a", first_message="Hi", tools=[], max_seconds=60)
    if bad.get("body") != {}:  # an empty object is a valid answer for a transcript: nobody said anything yet
        with pytest.raises(AdapterError):
            v.transcript("c1")


def test_a_phone_company_answer_that_cannot_be_read_counts_as_an_attempt_because_the_phone_may_ring(session, ctx, seeded):
    live_ctx(ctx)

    class Unreadable(SpyTelephony):
        def place_call(self, **kw):
            raise BadReply("Telnyx sent an answer without the field 'call_control_id'")

    base = sum(attempts(session))
    ctx.adapters.telephony = Unreadable()
    ctx.settings.dial_failure_limit = 1
    tick(session, ctx)
    assert session.scalars(select(Call).where(Call.blocked_reason == "place_unconfirmed")).one() and sum(attempts(session)) == base + 1


# ---- M6. the documented setup path is the one that exists
def test_the_client_guide_sends_the_first_setup_to_the_machine_itself_not_to_a_host_the_proxy_does_not_forward():
    caddy = (ROOT / "deploy" / "hetzner" / "Caddyfile").read_text()
    forwarded = re.search(r"@vendor path ([^\n]+)", caddy).group(1).split()
    assert forwarded == ["/api/webhooks/*", "/api/tools/*"]
    for name in ("10-USING-IT-FOR-A-CLIENT.md", "13-SECURITY-AND-DATA.md"):
        text = (ROOT / "docs" / name).read_text()
        for url in re.findall(r"https?://api\.[^\s\"')`]+", text):
            assert url.endswith(("/api/webhooks/telnyx", "/api/webhooks/ultravox")) or "/api/tools/" in url, f"{name} sends {url} to a host that answers 404 for it"
    guide = (ROOT / "docs" / "10-USING-IT-FOR-A-CLIENT.md").read_text()
    assert "ssh -L 8000:127.0.0.1:8000" in guide and "http://127.0.0.1:8000/api/auth/login" in guide


# ---- M7. callers who withhold their number have a limit of their own
@pytest.mark.parametrize("withheld", ["", "anonymous", "restricted", "+266696687"])
def test_withheld_callers_do_not_use_up_the_limit_of_every_other_private_caller(session, ctx, seeded, withheld):
    live_ctx(ctx)
    ctx.settings.max_inbound_calls = 100
    ctx.settings.max_inbound_per_number_hour = 2
    ctx.settings.max_inbound_anonymous_hour = 4
    num = session.scalars(select(Number).where(Number.agent_id.is_not(None))).first()
    eff = ctx.effective(session)
    ask = lambda frm, i: live.handle_inbound(session, ctx, eff, {"to": num.e164, "from": frm, "call_control_id": f"v3:{withheld}{frm}{i}"})  # noqa: E731
    assert [ask(withheld, i) for i in range(5)] == ["answered"] * 4 + ["rate_limited"]  # their own shared limit, higher than the per number one
    assert ask("+14155550123", 0) == "answered"  # a caller with a number is not locked out by them
    assert [ask("+14155550123", i) for i in range(1, 3)] == ["answered", "rate_limited"]  # and the per number limit still holds for a real number
    assert session.scalars(select(Call).where(Call.direction == "inbound", Call.peer_phone == "")).all()  # stored as withheld, not as the placeholder


# ---- M8. a voicemail is spoken after the greeting and only counts as left when it finished
def voicemail_call(session, ctx, seeded, text="Hello, this is Casey, an AI assistant calling for Harbor Light Dental about your next check up. Please call the practice back."):
    live_ctx(ctx)
    camp = session.get(Campaign, seeded["info"]["campaign_id"])
    camp.allow_voicemail, camp.voicemail_text = True, text
    c = Call(campaign_id=camp.id, agent_id=camp.agent_id, peer_phone="+14155550123", status="placed", telnyx_call_id="cc-vm")
    session.add(c); session.flush()
    return c, ctx.effective(session)


def log_kinds(ctx):
    return [a for a, _ in ctx.adapters.telephony.log]


def test_the_message_is_not_spoken_and_the_line_not_closed_while_the_machine_greeting_plays(session, ctx, seeded):
    c, eff = voicemail_call(session, ctx, seeded)
    assert live.handle_machine(session, ctx, eff, c) == "voicemail_waiting_for_beep"
    assert log_kinds(ctx) == [] and not c.disposition  # nothing said, nothing hung up, nothing recorded
    assert live.handle_beep(session, ctx, eff, c) == "voicemail_speaking" and log_kinds(ctx) == ["speak"]
    assert not c.disposition and live.handle_speech_ended(session, ctx, c) == "voicemail_left" and log_kinds(ctx) == ["speak", "hangup"]
    assert c.disposition == "voicemail_left"


def test_a_call_that_ends_in_the_middle_of_the_message_is_not_recorded_as_a_message_left(client):
    cid, _ = a_live_call(client)
    with client.ctx.factory() as s:
        c = s.get(Call, cid); c.status = "placed"
        camp = s.get(Campaign, c.campaign_id); camp.allow_voicemail = True; s.commit()
    state = encode_state({"call": cid})
    telnyx_post(client, "call.machine.detection.ended", {"result": "machine", "client_state": state})
    telnyx_post(client, "call.machine.greeting.ended", {"client_state": state})
    assert telnyx_post(client, "call.hangup", {"client_state": state}).json()["result"] == "voicemail_no_message"
    with client.ctx.factory() as s:
        assert s.get(Call, cid).disposition == "voicemail_no_message"
        assert s.scalars(select(Disposition).where(Disposition.call_id == cid)).one().code == "voicemail_no_message"


def test_no_beep_means_nothing_is_said_and_a_message_never_confirmed_is_not_called_left(session, ctx, seeded):
    c, eff = voicemail_call(session, ctx, seeded)
    live.handle_machine(session, ctx, eff, c)
    assert live.settle_voicemail_waits(session, ctx, datetime.now(UTC) + timedelta(seconds=30)) == 0  # still inside the wait
    assert live.settle_voicemail_waits(session, ctx, datetime.now(UTC) + timedelta(seconds=live.BEEP_TIMEOUT_S + 5)) == 1
    assert log_kinds(ctx) == ["hangup"] and c.disposition == "voicemail_no_message"  # no beep: the line is closed and nothing was said
    c2, eff = voicemail_call(session, ctx, seeded)
    c2.telnyx_call_id = "cc-vm2"
    live.handle_machine(session, ctx, eff, c2); live.handle_beep(session, ctx, eff, c2)
    assert live.settle_voicemail_waits(session, ctx, datetime.now(UTC) + timedelta(seconds=live.SPEECH_TIMEOUT_S + 5)) == 1
    assert c2.disposition == "voicemail_no_message"
    note = session.scalars(select(Disposition).where(Disposition.call_id == c2.id)).one().note
    assert "never confirmed" in note


def test_the_kill_switch_stops_a_voicemail_before_and_after_the_beep(session, ctx, seeded):
    c, eff = voicemail_call(session, ctx, seeded)
    assert live.handle_machine(session, ctx, eff, c) == "voicemail_waiting_for_beep"
    set_state(session, "kill_switch", "1"); session.flush()
    assert live.handle_beep(session, ctx, ctx.effective(session), c) == "voicemail_no_message" and "speak" not in log_kinds(ctx)


def test_the_dialer_job_closes_stale_voicemails_outside_demo_mode(session, ctx, seeded):
    c, eff = voicemail_call(session, ctx, seeded)
    live.handle_machine(session, ctx, eff, c)
    row = session.get(State, f"vm_wait:{c.id}")
    row.value = f"beep|{(datetime.now(UTC) - timedelta(minutes=5)).isoformat()}"
    session.commit()
    job_dial_tick(session, ctx)
    assert c.disposition == "voicemail_no_message" and session.get(State, f"vm_wait:{c.id}") is None


# ---- M9. the time zone against the area code
def test_the_area_code_table_has_each_code_in_one_zone_only_and_checks_the_common_cases():
    codes = [c for v in areacodes.OFFSETS.values() for c in v.split()]
    assert len(codes) == len(set(codes)) and all(re.fullmatch(r"[2-9]\d\d", c) for c in codes)
    assert areacodes.mismatch("+14155550100", "America/New_York") == ("415", -8, -5)  # San Francisco with an Eastern zone
    assert areacodes.mismatch("+14155550100", "America/Los_Angeles") is None
    assert areacodes.mismatch("+16025550100", "America/Phoenix") is None  # Arizona has no daylight saving: still Mountain in winter
    assert areacodes.mismatch("+18085550100", "Pacific/Honolulu") is None and areacodes.mismatch("+19075550100", "America/Anchorage") is None
    assert areacodes.mismatch("+12125550100", "America/Chicago") == ("212", -5, -6)
    assert areacodes.mismatch("+13005550100", "America/Chicago") is None  # a code that is not in the table is not checked
    assert areacodes.mismatch("+442071838750", "America/Chicago") is None and areacodes.mismatch("+14155550100", "Nowhere/Land") is None


def test_an_import_flags_zones_that_do_not_fit_and_returns_the_rows_to_look_at(session, seeded):
    camp = seeded["info"]["campaign_id"]
    rep = intake.import_targets(session, camp, [{"phone": "+14155550177", "timezone": "America/New_York"}, {"phone": "+12125550177", "timezone": "America/New_York"}])
    assert rep.created == 2 and rep.flagged == {"timezone_area_code_mismatch": 1}
    assert rep.warnings == [{"phone": "+14155550177", "area_code": "415", "timezone": "America/New_York", "kind": "timezone_area_code_mismatch"}]
    assert "+14155550177" in [m["phone"] for m in intake.timezone_mismatches(session, camp)] and "+12125550177" not in [m["phone"] for m in intake.timezone_mismatches(session, camp)]


def real_campaign(c, h):
    body = "You are Sam, an AI assistant calling for Acme Dental. Be brief and kind. Offer the listed times. If the person asks you to stop, stop. " * 2
    agent = c.post("/api/agents", headers=h, json={"name": "Sam", "prompt": body}).json()
    c.post(f"/api/agents/{agent['id']}/activate", headers=h, json={"version_id": agent["versions"][0]["id"]})
    return c.post("/api/campaigns", headers=h, json={"name": "East", "agent_id": agent["id"]}).json()


def test_a_campaign_with_zones_that_do_not_fit_starts_only_after_the_owner_says_they_looked(tmp_path):
    c = real_client(tmp_path)
    h = {**c.h, "x-ringlark": "1"}
    camp = real_campaign(c, h)
    rows = [{"phone": "+14155550101", "first_name": "Ava", "timezone": "America/New_York", "call_consent": "yes"}, {"phone": "+12125550102", "first_name": "Ben", "timezone": "America/New_York", "call_consent": "yes"}]
    rep = c.post(f"/api/campaigns/{camp['id']}/targets", headers=h, json={"rows": rows}).json()
    assert rep["flagged"]["timezone_area_code_mismatch"] == 1 and rep["warnings"][0]["area_code"] == "415"
    listed = c.get(f"/api/campaigns/{camp['id']}/timezone-warnings", headers=h).json()
    assert [w["phone"] for w in listed] == ["+14155550101"]
    assert [x["timezone_warnings"] for x in c.get("/api/campaigns", headers=h).json()] == [1]
    refused = c.post(f"/api/campaigns/{camp['id']}/start", headers=h)
    assert refused.status_code == 409 and "acknowledge_timezone_warnings" in refused.json()["error"]["message"]
    assert c.post(f"/api/campaigns/{camp['id']}/start", headers=h, json={"acknowledge_timezone_warnings": False}).status_code == 409
    assert c.post(f"/api/campaigns/{camp['id']}/start", headers=h, json={"acknowledge_timezone_warnings": True}).status_code == 200
    with c.ctx.factory() as s:
        assert s.scalar(select(func.count()).select_from(AuditEntry).where(AuditEntry.action == "campaign.timezone_warnings_acknowledged")) == 1


def test_a_clean_list_starts_without_any_acknowledgement(tmp_path):
    c = real_client(tmp_path)
    h = {**c.h, "x-ringlark": "1"}
    camp = real_campaign(c, h)
    c.post(f"/api/campaigns/{camp['id']}/targets", headers=h, json={"rows": [{"phone": "+14155550101", "first_name": "Ava", "timezone": "America/Los_Angeles", "call_consent": "yes"}]})
    assert c.post(f"/api/campaigns/{camp['id']}/start", headers=h).status_code == 200


# ---- the smaller findings
def test_the_word_records_is_not_a_recording_notice():
    assert not disclosure.has_recording_notice("Hi, this is Casey, an AI assistant. I am calling about your medical records.")
    assert disclosure.has_recording_notice("This call may be recorded and transcribed.") and disclosure.has_recording_notice("Calls are recorded.")
    assert disclosure.greeting_problems("Hi, this is Casey, an AI assistant calling about your records.", True)


def test_the_qa_queue_can_be_read_page_by_page_past_the_first_thousand(client):
    o = {**login(client), "x-ringlark": "1"}
    with client.ctx.factory() as s:
        camp = s.scalars(select(Campaign)).first()
        for i in range(25):
            c = Call(campaign_id=camp.id, agent_id=camp.agent_id, status="completed", peer_phone=f"+1212555{i:04d}")
            s.add(c); s.flush()
            s.add(QAScore(call_id=c.id, score=50 + i, flagged=False, sampled=True, reviewed=False, checks={}))
        s.commit()
    first = client.get("/api/qa?limit=10&offset=0", headers=o).json()
    second = client.get("/api/qa?limit=10&offset=10", headers=o).json()
    assert len(first) == 10 and len(second) == 10 and not {r["call_id"] for r in first} & {r["call_id"] for r in second}
    assert client.get("/api/qa?limit=1001", headers=o).status_code == 422  # the server's page size limit is why the web page must use offsets


def test_the_updating_guide_no_longer_says_sqlite_cannot_be_updated():
    text = (ROOT / "docs" / "12-UPDATING.md").read_text()
    assert "does not change old ones" not in text and "upgrade_sqlite" in text or "adds the columns" in text


def test_the_docs_say_what_is_unverified_and_what_is_not_done_for_inbound_bookings_and_email_spoofing():
    notes = (ROOT / "docs" / "14-LIMITS-AND-HONEST-NOTES.md").read_text()
    for needle in ("list_times", "voicemail", "anonymous", "area code", "inbound booking", "spoofed", "UNVERIFIED"):
        assert needle.lower() in notes.lower(), needle
