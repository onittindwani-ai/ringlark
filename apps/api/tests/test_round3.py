"""Round 3 audit fixes. Every test here fails on the code before the fix.

1 a timeout while sending or writing the CRM, 2 two requests at once, 3 the save before the answer, 5 the same text twice, 6 the tools on a fresh clone,
7 consent imports, 8 erasing a person and keeping old calls for a limited time, and the smaller findings."""

import re
import subprocess
import sys
import threading
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select, text

from testkit import NOW, make_settings
from ringlark import compliance, crmsync, erasure, followups, intake, retention
from ringlark.adapters.base import UNKNOWN_OUTCOME, UnknownOutcome
from ringlark.adapters.calcom import CalcomCalendar
from ringlark.adapters.telnyx import TelnyxSms
from ringlark.dbupgrade import upgrade_sqlite
from ringlark.disclosure import greeting_problems
from ringlark.jobs import job_postcall
from ringlark.live import inbound_greeting
from ringlark.models import Agent, Call, CallAction, Campaign, ConsentRecord, FollowUp, QAScore, State, Suppression, Target, Turn
from ringlark.postcall import process_call
from ringlark.suppression import add_suppression, is_suppressed, latest_consent
from ringlark.tools import ToolService
from ringlark.toolauth import tool_token
from ringlark.util import is_e164, normalize_phone
from sendora_core.db import Base
from sendora_core.jobs import Worker, enqueue
from sendora_core.models import AuditEntry, Event
from spies import SpyCrm, SpyEmail, SpySms
from test_api import a_live_call, client, login  # noqa: F401
from test_hardening_dialer import booked_call as dialer_booked_call, live_ctx
from test_hardening_sms import booked_call, sms_rows

ROOT = Path(__file__).resolve().parents[3]
ADAPTERS = lambda sms=None, email=None: type("A", (), {"sms": sms or SpySms(), "email": email or SpyEmail()})()  # noqa: E731


def owner_headers(client):
    return {**login(client), "x-ringlark": "1"}


def approver_headers(client):
    return {**login(client, "approver@example.test"), "x-ringlark": "1"}


# ---- 1. a timeout is not a rollback of everything sent before it
def pending_texts(session, seeded, n):
    camp = session.get(Campaign, seeded["info"]["campaign_id"])
    rows = []
    for t in session.scalars(select(Target).where(Target.sms_consent.is_(True), Target.timezone == "America/New_York").order_by(Target.id).limit(n)):
        c = Call(campaign_id=camp.id, target_id=t.id, agent_id=camp.agent_id, peer_phone=t.phone, status="completed")
        session.add(c); session.flush()
        fu = FollowUp(call_id=c.id, channel="sms", to=t.phone, body="Harbor Light Dental: your visit is booked. Reply STOP to opt out.", status="pending")
        session.add(fu); session.flush()
        rows.append(fu)
    session.commit()
    return [r.id for r in rows]


def test_a_timeout_on_one_text_keeps_the_texts_sent_before_it_and_nothing_is_sent_twice(session, ctx, seeded):
    ctx.settings.follow_ups_need_approval = False
    ids = pending_texts(session, seeded, 3)
    second = session.get(FollowUp, ids[1]).to

    class Flaky(SpySms):
        def send(self, *, to, text):
            if to == second:
                raise httpx.ReadTimeout("slow")
            return super().send(to=to, text=text)

    sms = Flaky()
    worker = Worker(ctx.factory, {"followups": lambda s, payload: followups.send_due(s, ctx.settings, ADAPTERS(sms), NOW)})
    for _ in range(2):  # the second run must not send anything again
        with ctx.factory() as s:
            enqueue(s, "followups"); s.commit()
        assert worker.run_once()
    with ctx.factory() as s:
        rows = [s.get(FollowUp, i) for i in ids]
        assert [r.status for r in rows] == ["sent", "blocked", "sent"]
        assert rows[1].blocked_reason == "send_unconfirmed"  # a person looks at it, nothing sends it again by itself
    assert [to for to, _ in sms.sent] == [session.get(FollowUp, ids[0]).to, session.get(FollowUp, ids[2]).to]


def test_a_follow_up_that_may_have_gone_out_is_resolved_by_a_person_and_never_sent_by_the_job(client):
    with client.ctx.factory() as s:
        c = s.scalars(select(Call)).first()
        fu = FollowUp(call_id=c.id, channel="sms", to=c.peer_phone, body="x", status="blocked", blocked_reason="send_unconfirmed")
        done = FollowUp(call_id=c.id, channel="sms", to=c.peer_phone, body="y", status="sent")
        s.add_all([fu, done]); s.commit()
        fid, did = fu.id, done.id
    o = owner_headers(client)
    assert client.post(f"/api/followups/{did}/resolve", headers=o, json={"sent": True}).status_code == 409  # only an unconfirmed one
    r = client.post(f"/api/followups/{fid}/resolve", headers=o, json={"sent": False, "note": "carrier shows no delivery"})
    assert r.status_code == 200 and r.json()["status"] == "failed"
    with client.ctx.factory() as s:
        assert s.scalar(select(func.count()).select_from(AuditEntry).where(AuditEntry.action == "followup.resolved")) == 1


def test_a_server_error_from_a_vendor_is_an_unknown_outcome_not_a_definite_failure(tmp_path):
    st = make_settings(tmp_path, telnyx_from_number="+14155550190", calcom_api_key="test-only-key", calcom_event_type_id=1)
    boom = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(503, json={"errors": [{"detail": "busy"}]})), base_url="https://vendor.example.test")
    refuse = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(422, json={"errors": [{"detail": "bad number"}], "error": {"message": "bad"}})), base_url="https://vendor.example.test")
    with pytest.raises(UnknownOutcome):
        TelnyxSms(st, boom).send(to="+14155550123", text="x")
    with pytest.raises(UnknownOutcome):
        CalcomCalendar(st, boom).book(start=NOW, name="Ava", email="ava@example.test", timezone="UTC")
    from sendora_core.adapters import AdapterError

    for call in (lambda: TelnyxSms(st, refuse).send(to="+14155550123", text="x"), lambda: CalcomCalendar(st, refuse).book(start=NOW, name="Ava", email="ava@example.test", timezone="UTC")):
        with pytest.raises(AdapterError) as exc:
            call()
        assert not isinstance(exc.value, UnknownOutcome)  # a refusal is a definite no, so it may be tried again
    assert UnknownOutcome in UNKNOWN_OUTCOME


def test_a_booking_answered_with_a_server_error_is_not_booked_twice(session, ctx, seeded):
    from test_engine import a_call

    c, t = a_call(session, seeded)
    calls = []

    class Down:
        def slots(self, a, b):
            return [NOW + timedelta(days=1)]

        def book(self, **kw):
            calls.append(kw)
            raise UnknownOutcome("Cal.com answered 503")

        def healthcheck(self):
            return True, "x"

    ctx.adapters.calendar = Down()
    svc = ToolService(session, ctx, c)
    args = {"slot": (NOW + timedelta(days=1)).isoformat(), "name": "Ava Alder", "email": "ava@example.test"}
    svc.now = NOW
    assert svc.run("book_meeting", args)["failed"] is True
    assert svc.run("book_meeting", args)["ok"] is False and len(calls) == 1


def test_a_refused_booking_gives_the_right_back_so_another_time_can_be_tried(session, ctx, seeded):
    from sendora_core.adapters import AdapterError
    from test_engine import a_call

    c, t = a_call(session, seeded)
    outcomes = [AdapterError("Cal.com could not book the call: that time is taken"), None]
    booked = []

    class Cal:
        def slots(self, a, b):
            return [NOW + timedelta(days=1), NOW + timedelta(days=2)]

        def book(self, *, start, **kw):
            if outcomes.pop(0):
                raise AdapterError("Cal.com could not book the call: that time is taken")
            booked.append(start)
            from ringlark.adapters.base import Booking

            return Booking("b-1", start, start + timedelta(minutes=30))

        def healthcheck(self):
            return True, "x"

    ctx.adapters.calendar = Cal()
    svc = ToolService(session, ctx, c)
    svc.now = NOW
    first = svc.run("book_meeting", {"slot": (NOW + timedelta(days=1)).isoformat(), "name": "Ava", "email": "ava@example.test"})
    assert first["ok"] is False and first["failed"] is True
    second = svc.run("book_meeting", {"slot": (NOW + timedelta(days=2)).isoformat(), "name": "Ava", "email": "ava@example.test"})
    assert second["ok"] is True and len(booked) == 1


class HungCrm(SpyCrm):
    """A CRM that never answers. Each call looks at the database through a second connection, to see what was already saved when the CRM was asked."""

    def __init__(self, factory):
        super().__init__()
        self.factory, self.attempts, self.processed_when_asked = factory, 0, []

    def upsert_person(self, person):
        self.attempts += 1
        with self.factory() as other:
            self.processed_when_asked.append(other.scalar(select(func.count()).select_from(Call).where(Call.processed.is_(True))))
        raise httpx.ReadTimeout("the CRM does not answer")


def test_a_hung_crm_never_holds_up_post_call_work_and_the_notes_are_written_later(session, ctx, seeded):
    live_ctx(ctx)
    dialer_booked_call(session, seeded)
    dialer_booked_call(session, seeded)
    session.commit()
    ctx.adapters.crm = HungCrm(ctx.factory)
    out = job_postcall(session, ctx)
    session.commit()
    assert out["processed"] == 2
    assert ctx.adapters.crm.attempts == 1  # the first timeout ends the pass: the second call does not wait for the same hung CRM
    assert ctx.adapters.crm.processed_when_asked == [2]  # both calls (and any stop request in them) were saved before the CRM was asked
    assert session.scalar(select(func.count()).select_from(State).where(State.key.startswith("crm_pending:", autoescape=True))) == 2
    good = SpyCrm()
    ctx.adapters.crm = good
    assert crmsync.flush(session, ctx) == {"written": 2, "left": 0, "gave_up": 0}
    assert len(good.writes) == 2 and session.scalar(select(func.count()).select_from(State).where(State.key.startswith("crm_pending:", autoescape=True))) == 0


def test_the_crm_pass_stops_when_its_time_is_used_and_gives_up_after_three_tries(session, ctx, seeded):
    live_ctx(ctx)
    dialer_booked_call(session, seeded)
    session.commit()
    job_postcall(session, ctx)  # queues the note with the working CRM already in place: written at once
    crmsync.queue(session, session.scalars(select(Call)).first())
    session.commit()
    spy = SpyCrm()
    ctx.adapters.crm = spy
    assert crmsync.flush(session, ctx, budget_s=-1) == {"written": 0, "left": 1, "gave_up": 0} and spy.writes == []  # no time left: nothing is asked
    ctx.adapters.crm = HungCrm(ctx.factory)
    results = [crmsync.flush(session, ctx) for _ in range(3)]
    assert [r["gave_up"] for r in results] == [0, 0, 1]
    assert session.scalar(select(Event.id).where(Event.kind == "crm.write_gave_up")) is not None


# ---- 2. two requests at the same time make one booking and one text
def slow_calendar(counter, when):
    class Cal:
        def slots(self, a, b):
            return [when]

        def book(self, **kw):
            time.sleep(0.4)  # long enough for the second request to arrive while the first waits for Cal.com
            counter.append(kw)
            from ringlark.adapters.base import Booking

            return Booking(f"b-{len(counter)}", kw["start"], kw["start"] + timedelta(minutes=30))

        def healthcheck(self):
            return True, "x"

    return Cal()


def together(ctx, call_id, tool, args, setup=None):
    """Run the same tool call from two threads, each with its own session, started at the same moment."""
    gate, out = threading.Barrier(2), []

    def work():
        with ctx.factory() as s:
            svc = ToolService(s, ctx, s.get(Call, call_id), {"x": NOW + timedelta(days=1)})
            svc.now = NOW
            gate.wait()
            out.append(svc.run(tool, args))
            s.commit()

    threads = [threading.Thread(target=work) for _ in range(2)]
    [t.start() for t in threads]
    [t.join(20) for t in threads]
    return out


def test_two_parallel_booking_requests_make_one_booking(session, ctx, seeded):
    from test_engine import a_call

    c, _ = a_call(session, seeded)
    session.commit()
    made = []
    ctx.adapters.calendar = slow_calendar(made, NOW + timedelta(days=1))
    out = together(ctx, c.id, "book_meeting", {"slot": "x", "name": "Ava Alder", "email": "ava@example.test"})
    assert len(out) == 2 and sorted(o["ok"] for o in out) == [False, True]
    assert len(made) == 1  # before the fix both requests passed the check and Cal.com was asked twice


def test_two_parallel_text_requests_send_one_text(session, ctx, seeded):
    from test_engine import a_call

    c, t = a_call(session, seeded)
    t.sms_consent, t.timezone = True, "America/New_York"
    session.commit()
    sent = []

    class Slow(SpySms):
        def send(self, *, to, text):
            time.sleep(0.4)
            sent.append(to)
            return "ok"

    ctx.adapters.sms = Slow()
    out = together(ctx, c.id, "send_sms", {"kind": "confirmation"})
    assert sorted(o["ok"] for o in out) == [False, True] and len(sent) == 1
    with ctx.factory() as s:
        assert [f.status for f in s.scalars(select(FollowUp).where(FollowUp.call_id == c.id))] == ["sent"]


# ---- 3. the save happens before the answer is sent
def fail_next_commit(ctx):
    state = {"on": True}

    def boom(session):
        if state["on"]:
            raise RuntimeError("disk full")

    event.listen(ctx.factory, "before_commit", boom)
    return state


def test_a_change_that_cannot_be_saved_is_an_error_not_a_success_message(client):
    h, quiet = owner_headers(client), TestClient(client.app, raise_server_exceptions=False)
    state = fail_next_commit(client.ctx)
    r = quiet.post("/api/settings", headers=h, json={"kill_switch": True})
    assert r.status_code == 500  # before the fix FastAPI sent the 200 first and saved afterwards
    state["on"] = False
    with client.ctx.factory() as s:
        assert s.get(State, "kill_switch") is None


def test_a_stop_text_that_cannot_be_saved_is_refused_so_telnyx_sends_it_again(client):
    quiet = TestClient(client.app, raise_server_exceptions=False)
    state = fail_next_commit(client.ctx)
    from test_api import TX

    body, h = TX.signed_event("message.received", {"id": "m-r3", "from": {"phone_number": "+14155550177"}, "text": "STOP"})
    assert quiet.post("/api/webhooks/telnyx", content=body, headers=h).status_code == 500
    state["on"] = False
    assert quiet.post("/api/webhooks/telnyx", content=body, headers=h).status_code == 200
    with client.ctx.factory() as s:
        assert latest_consent(s, "+14155550177", "sms") == "revoked"


def test_a_booking_that_cannot_be_saved_never_reaches_cal_com_and_is_not_reported_as_done(client):
    cid, _ = a_live_call(client)
    quiet = TestClient(client.app, raise_server_exceptions=False)
    asked = []
    client.ctx.adapters.calendar = slow_calendar(asked, NOW + timedelta(days=1))
    state = fail_next_commit(client.ctx)
    tok = {"X-Tool-Token": tool_token(client.ctx.settings.session_secret, cid)}
    r = quiet.post(f"/api/tools/{cid}/book_meeting", headers=tok, json={"slot": (NOW + timedelta(days=1)).isoformat(), "name": "Ava", "email": "ava@example.test"})
    state["on"] = False
    assert r.status_code == 500 and asked == []


def test_every_route_asks_for_its_session_with_the_function_scope():
    bare = []
    for f in (ROOT / "apps" / "api" / "src" / "ringlark" / "api").glob("*.py"):
        bare += [f.name for m in re.finditer(r"Depends\(db\)", f.read_text())]
    assert bare == []  # `Depends(db)` saves AFTER the answer has gone out


# ---- 5. the confirmation said on the call is not queued again after it
def test_the_confirmation_text_sent_on_the_call_is_not_queued_again_after_it(session, ctx, seeded):
    c, t = booked_call(session, seeded)
    sms = SpySms()
    ctx.adapters.sms = sms
    svc = ToolService(session, ctx, c)
    svc.now = NOW
    assert svc.run("send_sms", {"kind": "confirmation"})["ok"] is True
    process_call(session, ctx, c)
    assert [f.status for f in sms_rows(session, c)] == ["sent"] and len(sms.sent) == 1  # before the fix a second, pending copy was queued for approval


def test_a_confirmation_that_may_have_gone_out_is_not_queued_again_either(session, ctx, seeded):
    c, t = booked_call(session, seeded)

    class Slow(SpySms):
        def send(self, *, to, text):
            raise httpx.ReadTimeout("slow")

    ctx.adapters.sms = Slow()
    svc = ToolService(session, ctx, c)
    svc.now = NOW
    assert svc.run("send_sms", {"kind": "confirmation"})["failed"] is True
    process_call(session, ctx, c)
    assert [f.blocked_reason for f in sms_rows(session, c)] == ["send_unconfirmed"]


# ---- 6. the tools work on a fresh clone
def test_the_tools_put_the_shared_packages_on_their_own_path():
    code = "import sys; sys.path.insert(0, 'tools'); import _common, sendora_core; print(sendora_core.__file__)"
    r = subprocess.run([sys.executable, "-S", "-E", "-c", code], cwd=ROOT, capture_output=True, text=True)  # -S: no installed packages at all, -E: no PYTHONPATH
    assert r.returncode == 0 and "core-py" in r.stdout, r.stderr


def test_hash_password_runs_with_a_clean_python_path():
    code = ("import sys, getpass, runpy; sys.path.insert(0, 'tools'); getpass.getpass = lambda prompt='': 'test-only-a-long-password'; runpy.run_path('tools/hash_password.py', run_name='__main__')")
    env = {"PATH": "/usr/bin:/bin"}
    r = subprocess.run([sys.executable, "-E", "-c", code], cwd=ROOT, capture_output=True, text=True, env=env)
    assert r.returncode == 0 and "OWNER_PASSWORD_HASH='$argon2" in r.stdout, r.stderr


def test_the_tools_name_the_project_python_when_a_library_is_missing(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "tools"))
    import _common
    err = _common.need_libraries(ModuleNotFoundError("no", name="argon2"))
    assert ".venv/bin/python" in str(err) and "argon2" in str(err)


# ---- 7. only the owner imports call consents, and a consent keeps its date, source and note
def new_campaign(client, o):
    agent = client.get("/api/agents", headers=o).json()[0]
    return client.post("/api/campaigns", headers=o, json={"name": "Consent test", "agent_id": agent["id"]}).json()["id"]


def test_an_approver_cannot_import_a_call_consent_and_the_owner_stores_its_date_source_and_note(client):
    o, a = owner_headers(client), approver_headers(client)
    cid = new_campaign(client, o)
    row = {"phone": "+12065550151", "first_name": "Cleo", "timezone": "America/New_York", "call_consent": "yes", "consent_date": "2026-10-01", "consent_source": "booking page form", "consent_note": "ticked the call box"}
    assert client.post(f"/api/campaigns/{cid}/targets", headers=a, json={"rows": [row]}).status_code == 403
    plain = {k: v for k, v in row.items() if not k.startswith("consent") and k != "call_consent"}
    assert client.post(f"/api/campaigns/{cid}/targets", headers=a, json={"rows": [{**plain, "phone": "+12065550152"}]}).status_code == 200  # no consent column: still allowed
    r = client.post(f"/api/campaigns/{cid}/targets", headers=o, json={"rows": [row]})
    assert r.status_code == 200 and r.json()["call_consents"] == 1
    with client.ctx.factory() as s:
        rec = s.scalars(select(ConsentRecord).where(ConsentRecord.phone == "+12065550151", ConsentRecord.kind == "call")).one()
        assert rec.status == "granted" and rec.source == "import:booking page form" and rec.note == "ticked the call box"
        assert rec.created_at.date() == date(2026, 10, 1)


def test_a_row_for_a_person_already_in_the_list_still_records_its_consent_and_is_audited(client):
    o = owner_headers(client)
    cid = new_campaign(client, o)
    with client.ctx.factory() as s:
        known = s.scalars(select(Target).where(Target.phone.like("+1%"))).first().phone
    r = client.post(f"/api/campaigns/{cid}/targets", headers=o, json={"rows": [{"phone": known, "call_consent": "true", "consent_source": "paper form", "consent_date": "2026-09-30"}]})
    assert r.status_code == 200 and r.json()["duplicates"] == 1 and r.json()["call_consents"] == 1 and r.json()["consent_updates"] == 1
    with client.ctx.factory() as s:
        assert s.scalar(select(func.count()).select_from(AuditEntry).where(AuditEntry.action == "consent.imported")) == 1


def test_a_consent_with_a_bad_or_future_date_is_not_recorded_and_is_flagged(session, seeded):
    rep = intake.import_targets(session, seeded["info"]["campaign_id"], [
        {"phone": "+12065550161", "call_consent": "yes", "consent_date": "someday"},
        {"phone": "+12065550162", "call_consent": "yes", "consent_date": "2099-01-01"},
        {"phone": "+12065550163", "call_consent": "yes"},
    ])
    assert rep.consents == 1 and rep.flagged["consent_bad_date"] == 1 and rep.flagged["consent_future_date"] == 1 and rep.flagged["consent_without_date"] == 1


# ---- 8. erasing a person and keeping call content for a limited time
def test_erasing_a_person_removes_every_copy_and_keeps_only_a_hash_on_the_do_not_call_list(session, ctx, seeded):
    c, t = booked_call(session, seeded)
    t.email = "erase.me@example.test"
    phone, call_id, target_id = t.phone, c.id, t.id
    process_call(session, ctx, c)
    svc = ToolService(session, ctx, c)
    svc.now = NOW
    ctx.adapters.sms = SpySms()
    svc.run("send_sms", {"kind": "callback"})
    session.add(CallAction(call_id=call_id, kind="probe"))
    session.add(State(key=f"postcall_empty:{call_id}", value="x"))
    add_suppression(session, phone, "asked", "test")
    session.add(ConsentRecord(phone=phone, kind="call", status="granted", source="import:form", note="said yes"))
    session.commit()
    assert session.scalar(select(func.count()).select_from(Turn).where(Turn.call_id == call_id)) > 0

    counts = erasure.erase_person(session, phone, "owner@example.test")
    session.commit()
    assert counts["calls"] == 1 and counts["people"] == 1 and counts["kept"] == "do_not_call_hash"
    assert session.get(Call, call_id) is None and session.get(Target, target_id) is None
    for table in Base.metadata.sorted_tables:
        if table.name == "core_audit":
            continue  # the audit chain cannot be edited: it holds the last four digits and counts only
        dump = " ".join(str(r) for r in session.execute(select(table)).all())
        assert phone not in dump and phone[1:] not in dump and "erase.me@example.test" not in dump, table.name
    last = session.scalar(select(AuditEntry).where(AuditEntry.action == "person.erased"))
    assert phone not in str(last.detail) and last.target == f"phone:{phone[-4:]}"
    # the stop survives, as a hash
    assert is_suppressed(session, phone) and latest_consent(session, phone, "call") == "revoked" and latest_consent(session, phone, "sms") == "revoked"
    stored = [s.phone for s in session.scalars(select(Suppression)) if s.source == "erase"]
    assert len(stored) == 1 and stored[0].startswith("sha:") and len(stored[0]) <= 32 and phone not in stored[0]
    # and a second erase of the same number is quiet and keeps one row
    erasure.erase_person(session, phone, "owner@example.test")
    assert len([s for s in session.scalars(select(Suppression)) if s.source == "erase"]) == 1


def test_a_person_who_asked_only_to_be_erased_can_be_removed_without_a_do_not_call_entry_but_a_stop_on_record_is_kept(session, ctx, seeded):
    c, t = booked_call(session, seeded)
    phone = t.phone
    session.commit()
    out = erasure.erase_person(session, phone, "owner@example.test", keep_do_not_call=False)
    assert out["kept"] == "none" and not is_suppressed(session, phone)
    c2, t2 = booked_call(session, seeded)
    session.add(ConsentRecord(phone=t2.phone, kind="sms", status="revoked", source="inbound STOP m1"))
    session.commit()
    out = erasure.erase_person(session, t2.phone, "owner@example.test", keep_do_not_call=False)
    assert out["kept"] == "stop_hash" and latest_consent(session, t2.phone, "sms") == "revoked"


def test_the_erase_route_is_owner_only_and_checks_the_number(client):
    o, a = owner_headers(client), approver_headers(client)
    with client.ctx.factory() as s:
        phone = s.scalars(select(Target)).first().phone
    assert client.post("/api/people/erase", headers=a, json={"phone": phone}).status_code == 403
    assert client.post("/api/people/erase", headers=o, json={"phone": "12"}).status_code == 422
    r = client.post("/api/people/erase", headers=o, json={"phone": phone})
    assert r.status_code == 200 and r.json()["people"] >= 1
    with client.ctx.factory() as s:
        assert s.scalar(select(func.count()).select_from(Target).where(Target.phone == phone)) == 0 and is_suppressed(s, phone)
    shown = client.get("/api/suppressions", headers=o).json()
    assert phone not in str(shown)


def old_and_new_calls(session, ctx, seeded):
    camp = session.get(Campaign, seeded["info"]["campaign_id"])
    t = session.scalars(select(Target).order_by(Target.id)).first()
    made = []
    for days in (400, 10):
        c = Call(campaign_id=camp.id, target_id=t.id, agent_id=camp.agent_id, peer_phone=t.phone, status="completed", processed=True, summary=f"Summary {days}", created_at=datetime.now(UTC) - timedelta(days=days))
        session.add(c); session.flush()
        session.add(Turn(call_id=c.id, position=0, speaker="caller", text=f"words {days}"))
        session.add(FollowUp(call_id=c.id, channel="sms", to=t.phone, body=f"text {days}", status="sent"))
        made.append(c.id)
    session.commit()
    return made


def test_old_call_content_is_deleted_after_the_retention_period_and_recent_content_is_kept(session, ctx, seeded):
    ctx.settings.demo_mode, ctx.settings.retention_days = False, 365
    old, new = old_and_new_calls(session, ctx, seeded)
    out = retention.run(session, ctx)
    session.commit()
    assert out == {"turns": 1, "summaries": 1, "followups": 1}
    assert session.scalar(select(func.count()).select_from(Turn).where(Turn.call_id == old)) == 0 and session.get(Call, old).summary == ""
    assert session.scalar(select(func.count()).select_from(FollowUp).where(FollowUp.call_id == old)) == 0
    assert session.get(Call, old).peer_phone  # the call row and the number stay: the attempt and do not call rules need them
    assert session.scalar(select(func.count()).select_from(Turn).where(Turn.call_id == new)) == 1 and session.get(Call, new).summary == "Summary 10"
    assert session.scalar(select(func.count()).select_from(AuditEntry).where(AuditEntry.action == "retention.run")) == 1
    assert retention.run(session, ctx) == {"turns": 0, "summaries": 0, "followups": 0}


def test_retention_is_off_in_demo_mode_and_at_zero_days(session, ctx, seeded):
    old_and_new_calls(session, ctx, seeded)
    ctx.settings.demo_mode, ctx.settings.retention_days = True, 365
    assert "skipped" in retention.run(session, ctx)
    ctx.settings.demo_mode, ctx.settings.retention_days = False, 0
    assert "skipped" in retention.run(session, ctx)
    assert session.scalar(select(func.count()).select_from(Turn)) >= 2


def test_the_retention_job_is_scheduled_daily():
    from ringlark import jobs

    assert jobs.INTERVALS["retention"] == 24 * 3600 and "retention" in jobs.JOBS


# ---- the smaller findings
def test_an_extension_is_never_glued_to_a_number_and_a_plus_one_number_must_have_ten_digits():
    assert normalize_phone("+1 415 555 0100 ext 22") == "" and normalize_phone("+14155550100 x22") == "" and normalize_phone("+1 (415) 555-0100 #5") == ""
    assert normalize_phone("+1 (415) 555-0100") == "+14155550100" and normalize_phone("+44 20 7946 0958") == "+442079460958"
    assert normalize_phone("+1415555010022") == "" and normalize_phone("+141555501") == "" and normalize_phone("+10155550100") == ""
    assert not is_e164("+1415555010022") and is_e164("+14155550100")


def test_caribbean_numbers_need_their_own_area_code_in_the_allowed_list():
    assert not compliance.country_allowed("+18765550100", ("+1",)) and not compliance.country_allowed("+18095550100", ("+1",))
    assert compliance.country_allowed("+18765550100", ("+1", "+1876")) and compliance.country_allowed("+14155550100", ("+1",))
    assert compliance.country_allowed("+17875550100", ("+1",))  # Puerto Rico is a US territory
    assert compliance.country_allowed("+442079460958", ()) is True


def test_a_custom_greeting_must_say_it_is_an_ai_and_that_the_call_may_be_recorded(client):
    o = owner_headers(client)
    body = {"name": "Greeter", "kind": "inbound", "prompt": "You are an assistant for Acme. Be brief. Offer the listed times. Stop when asked. " * 2}
    r = client.post("/api/agents", headers=o, json={**body, "greeting": "Hello, Acme here, how can I help?"})
    assert r.status_code == 422 and "AI" in r.text and "recorded" in r.text
    ok = "Hello, this is Greeter, an AI assistant for Acme. This call may be recorded. How can I help?"
    assert client.post("/api/agents", headers=o, json={**body, "greeting": ok}).status_code == 200
    assert greeting_problems("Hi, I am an AI. Calls are recorded.", True) == [] and len(greeting_problems("Hello", True)) == 2 and len(greeting_problems("Hello", False)) == 1


def test_a_stored_greeting_without_the_notice_is_never_spoken_to_a_caller(session, ctx, seeded):
    agent = session.scalars(select(Agent).where(Agent.kind == "inbound")).first()
    agent.greeting = "Welcome to Harbor Light Dental. How can I help?"
    assert "an AI assistant" in inbound_greeting(agent, ctx.settings) and "recorded" in inbound_greeting(agent, ctx.settings)
    agent.greeting = "Hi, this is Riley, an AI assistant. This call may be recorded. Go ahead."
    assert inbound_greeting(agent, ctx.settings) == agent.greeting
    agent.greeting = "Hi, this is Riley, an AI assistant. Go ahead."
    ctx.settings.recording_notice_required = False
    assert inbound_greeting(agent, ctx.settings) == agent.greeting


def test_the_dialer_holds_a_campaign_whose_greeting_has_no_recording_notice(session, ctx, seeded):
    from ringlark import dialer

    camp = session.get(Campaign, seeded["info"]["campaign_id"])
    agent = session.get(Agent, camp.agent_id)
    t = session.scalars(select(Target).where(Target.status == "new", Target.timezone == "America/New_York")).first()
    agent.greeting = "Hi, this is Casey, an AI assistant calling for Harbor Light Dental. Is now a good time?"
    d = dialer.decide(session, ctx.settings, camp, agent, t, NOW, 0)
    assert d.reason == "no_recording_notice"
    ctx.settings.recording_notice_required = False
    assert dialer.decide(session, ctx.settings, camp, agent, t, NOW, 0).reason != "no_recording_notice"


def test_the_api_host_of_the_hetzner_proxy_forwards_only_webhooks_and_tools():
    caddy = (ROOT / "deploy" / "hetzner" / "Caddyfile").read_text()
    api_block = caddy[caddy.index("api.example.com {"):]
    assert "@vendor path /api/webhooks/* /api/tools/*" in api_block and "respond" in api_block and "404" in api_block
    assert api_block.count("reverse_proxy") == 1  # one proxy line, inside the handle for those two paths; everything else is answered 404


def test_a_booking_email_that_is_not_text_is_a_polite_no_not_a_server_error(client):
    cid, _ = a_live_call(client)
    tok = {"X-Tool-Token": tool_token(client.ctx.settings.session_secret, cid)}
    slot = (NOW + timedelta(days=1)).isoformat()
    for bad in (12345, ["a@b.co"], {"x": 1}, True):
        r = client.post(f"/api/tools/{cid}/book_meeting", headers=tok, json={"slot": slot, "name": "Ava", "email": bad})
        assert r.status_code == 200 and r.json()["ok"] is False, bad
    r = client.post(f"/api/tools/{cid}/book_meeting", headers=tok, json={"slot": slot, "name": ["Ava"], "email": "ava@example.test"})
    assert r.status_code == 200 and r.json()["ok"] is False


def test_an_owner_can_take_a_number_off_the_do_not_call_list_with_a_reason_and_nothing_is_granted(client):
    o, a = owner_headers(client), approver_headers(client)
    phone = "+12065550171"
    assert client.post("/api/suppressions", headers=o, json={"phone": phone}).json()["added"] is True
    with client.ctx.factory() as s:
        sid = s.scalars(select(Suppression).where(Suppression.phone == phone)).one().id
    assert client.post(f"/api/suppressions/{sid}/remove", headers=a, json={"note": "it was a spoof"}).status_code == 403
    assert client.post(f"/api/suppressions/{sid}/remove", headers=o, json={"note": "no"}).status_code == 422  # a reason is required
    assert client.post(f"/api/suppressions/{sid}/remove", headers=o, json={"note": "A stranger spoofed this caller ID"}).status_code == 200
    assert client.post(f"/api/suppressions/{sid}/remove", headers=o, json={"note": "again, once more"}).status_code == 404
    with client.ctx.factory() as s:
        assert not is_suppressed(s, phone) and latest_consent(s, phone, "call") is None and latest_consent(s, phone, "sms") is None  # not blocked, and never granted either
        assert s.scalar(select(func.count()).select_from(AuditEntry).where(AuditEntry.action == "suppression.removed")) == 1


def test_the_qa_queue_can_be_paged_so_no_held_call_is_out_of_reach(client):
    with client.ctx.factory() as s:
        camp = s.scalars(select(Campaign)).first()
        ids = []
        for i in range(5):
            c = Call(campaign_id=camp.id, agent_id=camp.agent_id, peer_phone=f"+1206555018{i}", status="completed", processed=True, disposition="needs_review")
            s.add(c); s.flush()
            s.add(QAScore(call_id=c.id, score=10 + i, checks={}, flagged=True, flag_note="x", sampled=True))
            ids.append(c.id)
        s.commit()
    o = owner_headers(client)
    full = [r["call_id"] for r in client.get("/api/qa?show=all&limit=1000", headers=o).json()]
    first = [r["call_id"] for r in client.get("/api/qa?show=all&limit=2", headers=o).json()]
    second = [r["call_id"] for r in client.get("/api/qa?show=all&limit=2&offset=2", headers=o).json()]
    assert first == full[:2] and second == full[2:4] and set(ids) <= set(full)
    assert client.get("/api/qa?limit=0", headers=o).status_code == 422


def test_an_old_sqlite_file_gets_the_new_column_and_indexes_at_start(tmp_path):
    from sqlalchemy import create_engine, inspect

    eng = create_engine(f"sqlite:///{tmp_path / 'old.sqlite3'}")
    Base.metadata.create_all(eng)
    with eng.begin() as conn:  # make it look like a file written by 1.0.0
        conn.execute(text("DROP INDEX ix_rm_call_external_id"))
        conn.execute(text("DROP INDEX ix_rm_call_telnyx_call_id"))
        conn.execute(text("ALTER TABLE rm_consent DROP COLUMN note"))
        conn.execute(text("DROP TABLE rm_call_action"))
    done = upgrade_sqlite(eng)
    insp = inspect(eng)
    assert "note" in {c["name"] for c in insp.get_columns("rm_consent")} and insp.has_table("rm_call_action")
    assert {"ix_rm_call_external_id", "ix_rm_call_telnyx_call_id"} <= {i["name"] for i in insp.get_indexes("rm_call")}
    assert "rm_consent.note" in done and upgrade_sqlite(eng) == []  # and running it again does nothing


def test_the_core_test_count_is_a_measured_number_in_the_docs():
    counts = (ROOT / "tools" / "make_counts.py").read_text()
    docs = (ROOT / "docs" / "14-LIMITS-AND-HONEST-NOTES.md").read_text()
    assert "core_tests" in counts and "<!--n:core_tests-->" in docs
