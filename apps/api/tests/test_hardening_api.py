"""The API: sign in, demo shortcuts, body sizes, tool tokens, a real (non demo) install, configuration."""

import re
import shutil
import smtplib
import ssl
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from testkit import DATA, NOW, make_settings
from ringlark import dialer, datadir, demo
from ringlark.adapters.smtp_imap import SmtpImapEmail
from ringlark.adapters.ultravox import verify_ultravox_webhook
from ringlark.api.app import create_app, seed_empty_demo
from ringlark.config import Settings
from ringlark.context import Ctx
from ringlark.models import Call, Campaign, FollowUp, Target
from ringlark.toolauth import check_token, tool_token
from sendora_core.adapters import AdapterError
from sendora_core.auth import hash_password
from sendora_core.db import Base, make_engine, make_session_factory
from spies import SpyTelephony, SpyVoice
from test_api import client, login  # noqa: F401  (the demo API client)

STRONG = "test-only-Rt7Kq2Vw9Xm4Zc8Lb3Nf6Hy1Js5Dp0Ga2Ue7Tq4Wi9"
PASSWORD = "test-only-owner-password"


def real_client(tmp_path, **kw):
    """A real install: demo mode off, an owner password, the business named, drafts allowed to go live."""
    kw.setdefault("public_base_url", "https://ringlark.example.test")  # outside demo mode a call needs the address its tools are reached at
    st = make_settings(tmp_path, demo_mode=False, session_secret=STRONG, owner_password_hash=hash_password(PASSWORD), company_name="Acme Dental", **kw)
    eng = make_engine(st.database_url)
    Base.metadata.create_all(eng)
    ctx = Ctx(st, make_session_factory(eng))
    ctx.adapters.telephony, ctx.adapters.voice = SpyTelephony(), SpyVoice(ctx.factory)
    c = TestClient(create_app(st, ctx))
    c.ctx = ctx  # type: ignore[attr-defined]
    r = c.post("/api/auth/login", json={"email": "owner@example.test", "password": PASSWORD})
    assert r.status_code == 200, r.text
    c.h = {"x-session": r.json()["token"]}  # type: ignore[attr-defined]
    return c


# ---- sign in
def test_spellings_of_one_email_share_one_set_of_tries(tmp_path):
    st = make_settings(tmp_path, login_burst=3)
    ctx = Ctx(st, make_session_factory(make_engine(st.database_url)))
    Base.metadata.create_all(ctx.factory.kw["bind"])
    c = TestClient(create_app(st, ctx))
    codes = [c.post("/api/auth/login", json={"email": e, "password": "wrong-password"}).status_code for e in ("owner@example.test", " owner@example.test", "OWNER@example.test ", "\towner@example.test", "owner@EXAMPLE.test")]
    assert codes[:3] == [401, 401, 401] and 429 in codes[3:]


def test_one_address_trying_many_accounts_is_slowed_and_so_is_one_account_from_many(tmp_path):
    st = make_settings(tmp_path, login_burst=2)
    ctx = Ctx(st, make_session_factory(make_engine(st.database_url)))
    Base.metadata.create_all(ctx.factory.kw["bind"])
    c = TestClient(create_app(st, ctx))
    codes = [c.post("/api/auth/login", json={"email": f"user{i}@example.test", "password": "wrong-password"}).status_code for i in range(12)]
    assert 429 in codes  # the address bucket (8 tries) ran out although every account name was new
    c2 = TestClient(create_app(st, ctx))
    app = c2.app
    for host in ("1.1.1.1", "2.2.2.2", "3.3.3.3", "4.4.4.4", "5.5.5.5"):  # the account bucket holds 4 tries whoever asks
        try:
            app.state.login_account_bucket.check("owner@example.test")
            blocked = False
        except Exception:
            blocked = True
    assert blocked


def test_email_and_password_have_a_length_limit(client):
    assert client.post("/api/auth/login", json={"email": "a" * 300 + "@x.test", "password": "x"}).status_code == 422
    assert client.post("/api/auth/login", json={"email": "owner@example.test", "password": "p" * 2000}).status_code == 422


def test_an_unknown_account_does_the_same_password_work(client, monkeypatch):
    seen = []
    import ringlark.api.routes_auth as ra

    real = ra.verify_password_or_dummy
    monkeypatch.setattr(ra, "verify_password_or_dummy", lambda pw, h: seen.append(h) or real(pw, h))
    assert client.post("/api/auth/login", json={"email": "nobody@example.test", "password": "whatever-it-is"}).status_code == 401
    assert seen == [None]


def test_an_oversized_login_body_is_refused_before_it_is_read(client):
    r = client.post("/api/auth/login", content=b'{"email":"a@b.test","password":"' + b"x" * 20000 + b'"}', headers={"content-type": "application/json"})
    assert r.status_code == 413


def test_oversized_webhook_and_tool_bodies_are_refused_before_they_are_read(client):
    assert client.post("/api/webhooks/telnyx", content=b"x" * 1_100_000).status_code == 413
    assert client.post("/api/tools/1/end_call", content=b"x" * 30_000, headers={"X-Tool-Token": "1.x"}).status_code == 413


# ---- demo shortcuts exist only while no owner password is set
def test_an_owner_password_switches_every_demo_shortcut_off(tmp_path):
    st = make_settings(tmp_path, demo_mode=True, owner_password_hash=hash_password(PASSWORD))  # DEMO_MODE left on by mistake
    eng = make_engine(st.database_url)
    Base.metadata.create_all(eng)
    ctx = Ctx(st, make_session_factory(eng))
    app = create_app(st, ctx)
    c = TestClient(app)
    assert not st.demo_shortcuts
    for email in ("approver@example.test", "viewer@example.test", "owner@example.test"):
        assert c.post("/api/auth/login", json={"email": email, "password": "demo-password-1"}).status_code == 401, email
    token = c.post("/api/auth/login", json={"email": "owner@example.test", "password": PASSWORD}).json()["token"]
    h = {"x-session": token, "x-ringlark": "1"}
    assert c.post("/api/demo/reset", headers=h).status_code == 404
    assert c.post("/api/demo/advance", headers=h, json={"hours": 1}).status_code == 404
    assert c.get("/api/auth/me", headers=h).json()["demo_mode"] is False
    assert seed_empty_demo(app) is False
    with ctx.factory() as s:
        assert s.scalar(select(Campaign.id)) is None  # nothing fictional was written into this database


def test_the_demo_still_works_without_an_owner_password(client):
    assert client.post("/api/demo/reset", headers=login(client)).status_code == 200


def test_the_worker_refuses_an_unsafe_configuration_and_reads_the_same_env_file(tmp_path, monkeypatch):
    from ringlark import worker
    from sendora_core.settings import ConfigError

    env = tmp_path / "w.env"
    env.write_text(f"DATABASE_URL=sqlite:///{tmp_path / 'w.sqlite3'}\nDEMO_MODE=false\nSESSION_SECRET=change-me-but-long-enough-1234\n")
    monkeypatch.setenv("ENV_FILE", str(env))
    with pytest.raises(ConfigError):
        worker.main()


# ---- tool tokens
def test_a_tool_token_is_for_one_call_and_runs_out():
    t = tool_token("s" * 40, 5, now=1000.0)
    assert check_token("s" * 40, 5, t, now=1100.0)
    assert not check_token("s" * 40, 6, t, now=1100.0)
    assert not check_token("s" * 40, 5, t, now=1000.0 + 21 * 60)
    assert not check_token("other" * 8, 5, t, now=1100.0)
    assert not check_token("s" * 40, 5, "5." + t.split(".")[1], now=1100.0)  # the expiry cannot be edited


def test_the_tool_key_is_not_the_session_key():
    import hashlib, hmac

    secret, exp = "k" * 40, 9999999999
    old_style = hmac.new(secret.encode(), f"tool:5".encode(), hashlib.sha256).hexdigest()[:40]
    assert not check_token(secret, 5, f"{exp}.{old_style}")
    assert tool_token("a" * 40, 5, now=1.0) != tool_token("b" * 40, 5, now=1.0)


def test_odd_characters_in_a_header_are_a_plain_no(client):
    assert client.post("/api/tools/1/end_call", headers={"X-Tool-Token": "é.é".encode("latin-1")}, json={}).status_code == 401
    assert verify_ultravox_webhook("secret", b"{}", "é", str(int(datetime.now(UTC).timestamp()))) is False
    r = client.post("/api/webhooks/ultravox", content=b"{}", headers={"X-Ultravox-Webhook-Signature": "é".encode("latin-1"), "X-Ultravox-Webhook-Timestamp": str(int(datetime.now(UTC).timestamp()))})
    assert r.status_code == 401


def test_the_tools_per_call_rate_limit(client):
    from test_api import a_live_call

    cid, _ = a_live_call(client)
    h = {"X-Tool-Token": tool_token(client.ctx.settings.session_secret, cid)}
    codes = [client.post(f"/api/tools/{cid}/lookup_crm", headers=h, json={}).status_code for _ in range(40)]
    assert 429 in codes and codes[0] == 200


def test_booking_once_a_valid_email_and_an_offered_time(session, ctx, seeded):
    from ringlark.tools import ToolService

    camp = session.get(Campaign, seeded["info"]["campaign_id"])
    t = session.scalars(select(Target).where(Target.status == "new")).first()
    c = Call(campaign_id=camp.id, target_id=t.id, agent_id=camp.agent_id, peer_phone=t.phone, status="in_progress", telnyx_call_id="cc-1")
    session.add(c); session.flush()
    svc = ToolService(session, ctx, c)
    svc.now = NOW
    slot = ctx.adapters.calendar.slots(NOW, NOW.replace(day=20))[0].isoformat()
    assert not svc.run("book_meeting", {"slot": "2026-12-03T03:00:00+00:00", "name": "Ava", "email": "ava@example.test"})["ok"]  # not an offered time
    assert not svc.run("book_meeting", {"slot": slot, "name": "Ava", "email": "a@x.test, b@y.test"})["ok"]  # two recipients
    assert svc.run("book_meeting", {"slot": slot, "name": "Ava", "email": "ava@example.test"})["ok"]
    assert not svc.run("book_meeting", {"slot": slot, "name": "Ava", "email": "ava@example.test"})["ok"]  # one booking per call


def test_an_inbound_caller_is_not_told_a_name(session, ctx, seeded):
    from ringlark.tools import ToolService

    t = session.scalars(select(Target).where(Target.status == "new")).first()
    camp = session.get(Campaign, seeded["info"]["campaign_id"])
    c = Call(agent_id=camp.agent_id, direction="inbound", peer_phone=t.phone, status="in_progress")
    session.add(c); session.flush()
    out = ToolService(session, ctx, c).run("lookup_crm", {})
    assert out["found"] is False and out["first_name"] == ""


# ---- a real install can do the job end to end
def test_a_real_install_can_make_an_agent_a_number_a_campaign_and_place_a_call(tmp_path):
    c = real_client(tmp_path)
    h = {**c.h, "x-ringlark": "1"}
    assert c.get("/api/agents", headers=h).json() == []
    body = "You are Sam, an AI assistant calling for Acme Dental. Be brief and kind. Offer the listed times. If the person asks you to stop, stop. " * 2
    r = c.post("/api/agents", headers=h, json={"name": "Sam", "prompt": body, "transfer_number": "+14155550199"})
    assert r.status_code == 200, r.text
    agent = r.json()
    assert agent["versions"][0]["version"] == 1 and agent["active_version_id"] is None
    assert c.post("/api/agents", headers=h, json={"name": "Sam", "prompt": body}).status_code == 409
    assert c.post(f"/api/agents/{agent['id']}/activate", headers=h, json={"version_id": agent["versions"][0]["id"]}).status_code == 200
    n = c.post("/api/numbers", headers=h, json={"e164": "+1 (415) 555-0190", "agent_id": agent["id"]})
    assert n.status_code == 200 and n.json()["e164"] == "+14155550190" and n.json()["checklist"]["caller_id_registered"] is False
    assert c.post("/api/numbers", headers=h, json={"e164": "+14155550190"}).status_code == 409
    camp = c.post("/api/campaigns", headers=h, json={"name": "First", "agent_id": agent["id"], "number_id": n.json()["id"]}).json()
    rep = c.post(f"/api/campaigns/{camp['id']}/targets", headers=h, json={"rows": [{"phone": "+14155550101", "first_name": "Ava", "timezone": "America/New_York", "call_consent": "yes"}]}).json()
    assert rep["created"] == 1 and rep["call_consents"] == 1  # a campaign made with no flag requires a call consent, so the import gives one
    assert rep["warnings"][0]["area_code"] == "415"  # a San Francisco number with a New York zone: a warning, kept in the list
    assert c.post(f"/api/campaigns/{camp['id']}/start", headers=h).status_code == 409  # until the owner says they looked at it
    assert c.post(f"/api/campaigns/{camp['id']}/start", headers=h, json={"acknowledge_timezone_warnings": True}).status_code == 200
    with c.ctx.factory() as s:
        res = dialer.dial_tick(s, c.ctx.effective(s), c.ctx.adapters, NOW)
        s.commit()
        assert res.placed == 1 and c.ctx.adapters.telephony.log == [("place", "+14155550101")]
        assert c.ctx.adapters.voice.prompts[0].startswith("## Rules for every call") and "Acme Dental" in c.ctx.adapters.voice.prompts[0]


def test_a_call_consent_column_lets_a_consent_only_campaign_call_exactly_those_people(tmp_path):
    c = real_client(tmp_path)
    h = {**c.h, "x-ringlark": "1"}
    body = "You are Sam, an AI assistant calling for Acme Dental. Be brief and kind. Offer the listed times. If the person asks you to stop, stop. " * 2
    agent = c.post("/api/agents", headers=h, json={"name": "Sam", "prompt": body}).json()
    c.post(f"/api/agents/{agent['id']}/activate", headers=h, json={"version_id": agent["versions"][0]["id"]})
    n = c.post("/api/numbers", headers=h, json={"e164": "+14155550190", "agent_id": agent["id"]}).json()
    camp = c.post("/api/campaigns", headers=h, json={"name": "Opted in", "agent_id": agent["id"], "number_id": n["id"], "require_prior_consent": True}).json()
    rows = [
        {"phone": "+14155550101", "first_name": "Ava", "timezone": "America/New_York", "call_consent": "yes"},
        {"phone": "+14155550102", "first_name": "Ben", "timezone": "America/New_York", "call_consent": "no"},
        {"phone": "+14155550103", "first_name": "Cy", "timezone": "America/New_York"},
    ]
    rep = c.post(f"/api/campaigns/{camp['id']}/targets", headers=h, json={"rows": rows}).json()
    assert rep["created"] == 3 and rep["call_consents"] == 1
    assert c.post(f"/api/campaigns/{camp['id']}/start", headers=h, json={"acknowledge_timezone_warnings": True}).status_code == 200  # 415 numbers with a New York zone
    with c.ctx.factory() as s:
        res = dialer.dial_tick(s, c.ctx.effective(s), c.ctx.adapters, NOW)
        s.commit()
        assert res.placed == 1 and c.ctx.adapters.telephony.log == [("place", "+14155550101")]


def test_a_call_consent_column_never_overrides_a_refusal(session, seeded):
    from ringlark import intake
    from ringlark.models import Campaign
    from ringlark.suppression import add_suppression, latest_consent

    camp = session.scalars(select(Campaign)).first()
    add_suppression(session, "+12065550141", "asked to stop", "test")
    rep = intake.import_targets(session, camp.id, [{"phone": "+12065550141", "timezone": "America/Los_Angeles", "call_consent": "true"}])
    assert rep.consents == 0 and rep.flagged == {"consent_not_recorded_refused_before": 1} and latest_consent(session, "+12065550141", "call") != "granted"


def test_the_share_of_a_split_test_survives_a_save_and_a_read_back(client):
    o = {**login(client), "x-ringlark": "1"}
    agent = client.get("/api/agents", headers=o).json()[0]
    other = next(v for v in agent["versions"] if v["id"] != agent["active_version_id"])
    for share in (0.2, 0.3, 0.5, 0.1):
        r = client.post(f"/api/agents/{agent['id']}/split", headers=o, json={"candidate_id": other["id"], "share_b": share})
        assert r.status_code == 200, r.text
        back = next(a for a in client.get("/api/agents", headers=o).json() if a["id"] == agent["id"])
        assert back["candidate_version_id"] == other["id"] and back["ab_share_b"] == share
    assert client.post(f"/api/agents/{agent['id']}/split", headers=o, json={"candidate_id": other["id"], "share_b": 0.9}).status_code == 422


def test_agents_and_numbers_are_owner_only(client):
    a = login(client, "approver@example.test")
    body = "x" * 60
    assert client.post("/api/agents", headers={**a, "x-ringlark": "1"}, json={"name": "Z1", "prompt": body}).status_code == 403
    assert client.post("/api/numbers", headers={**a, "x-ringlark": "1"}, json={"e164": "+14155550177"}).status_code == 403


def test_a_do_not_call_list_can_be_imported(client):
    o = login(client)
    rows = [{"phone": "+14155550301", "reason": "From my old list"}, {"phone": "(415) 555-0302"}, {"phone": "+14155550301"}, {"phone": "nope"}]
    out = client.post("/api/suppressions/import", headers=o, json={"rows": rows}).json()
    assert out == {"added": 1, "already_listed": 1, "bad_number": 2}
    assert any(s["phone"] == "+14155550301" for s in client.get("/api/suppressions", headers=o).json())
    assert client.post("/api/suppressions/import", headers=login(client, "viewer@example.test"), json={"rows": rows}).status_code == 403


def test_only_the_owner_adds_people_to_a_running_campaign_and_only_one_plain_email_is_kept(client):
    o, a = login(client), login(client, "approver@example.test")
    camp = next(c for c in client.get("/api/campaigns", headers=o).json() if c["status"] == "running")
    row = {"rows": [{"phone": "+14155550311", "timezone": "America/New_York", "email": "a@x.test, b@y.test"}]}
    assert client.post(f"/api/campaigns/{camp['id']}/targets", headers=a, json=row).status_code == 403
    rep = client.post(f"/api/campaigns/{camp['id']}/targets", headers=o, json=row).json()
    assert rep["created"] == 1 and rep["flagged"]["bad_email"] == 1
    with client.ctx.factory() as s:
        assert s.scalars(select(Target).where(Target.phone == "+14155550311")).one().email == ""


def test_calling_hours_are_held_to_the_legal_window(client):
    o = login(client)
    agent = client.get("/api/agents", headers=o).json()[0]
    assert client.post("/api/campaigns", headers=o, json={"name": "Night", "agent_id": agent["id"], "window_start_hour": 0, "window_end_hour": 24}).status_code == 422
    client.ctx.settings.allow_extended_hours = True
    assert client.post("/api/campaigns", headers=o, json={"name": "Night", "agent_id": agent["id"], "window_start_hour": 6, "window_end_hour": 22}).status_code == 200


def test_a_rejected_follow_up_follows_the_decision_that_was_saved(client):
    o = login(client)
    with client.ctx.factory() as s:
        fu = s.scalars(select(FollowUp).where(FollowUp.status == "pending", FollowUp.approval_id.is_not(None))).first()
        aid, fid = fu.approval_id, fu.id
    assert client.post(f"/api/approvals/{aid}/decide", headers=o, json={"approve": False}).status_code == 200
    assert client.post(f"/api/approvals/{aid}/decide", headers=o, json={"approve": True}).status_code == 409
    with client.ctx.factory() as s:
        assert s.get(FollowUp, fid).status == "rejected"


# ---- names of the business and the placeholders
def test_placeholders_keep_a_real_install_in_draft_mode(tmp_path):
    st = make_settings(tmp_path, demo_mode=False, session_secret=STRONG, owner_password_hash="x", mode="live")
    ctx = Ctx(st, make_session_factory(make_engine(st.database_url)))
    Base.metadata.create_all(ctx.factory.kw["bind"])
    with ctx.factory() as s:
        assert ctx.effective(s).mode.value == "draft"
        assert any("COMPANY_NAME" in p for p in st.problems())
    st.company_name = "Acme Dental"
    with ctx.factory() as s:
        assert ctx.effective(s).mode.value == "live" and not st.identity_problems()
    st.email_adapter = "smtp_imap"
    assert any("COMPANY_ADDRESS" in p for p in st.identity_problems())


def test_a_follow_up_that_still_names_the_demo_practice_is_never_sent_to_a_real_person(session, ctx, seeded):
    from ringlark import followups
    from spies import SpySms

    ctx.settings.demo_mode = False
    ctx.settings.follow_ups_need_approval = False
    camp = session.get(Campaign, seeded["info"]["campaign_id"])
    t = session.scalars(select(Target).where(Target.sms_consent.is_(True), Target.timezone == "America/New_York")).first()
    c = Call(campaign_id=camp.id, target_id=t.id, agent_id=camp.agent_id, peer_phone=t.phone, status="completed")
    session.add(c); session.flush()
    fu = FollowUp(call_id=c.id, channel="sms", to=t.phone, body="Hi. Here: https://example.test/book (fictional demo link). Reply STOP to opt out.", status="pending")
    session.add(fu); session.flush()
    sms = SpySms()
    followups.send_due(session, ctx.settings, type("A", (), {"sms": sms, "email": None})(), NOW)
    assert sms.sent == [] and fu.blocked_reason == "demo_text"


# ---- mail: certificates are checked, plain text only on this computer
def test_mail_connections_check_certificates(tmp_path, monkeypatch):
    seen = {}

    class FakeSmtp:
        def __init__(self, host, port, timeout=None, context=None):
            seen["ssl_ctx"] = context

        def starttls(self, context=None):
            seen["starttls"] = context

        def login(self, *a):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def send_message(self, m, to_addrs=None):
            seen["to"] = to_addrs

    monkeypatch.setattr(smtplib, "SMTP", FakeSmtp)
    monkeypatch.setattr(smtplib, "SMTP_SSL", FakeSmtp)
    s = make_settings(tmp_path, smtp_host="smtp.example.test", smtp_port=587, smtp_user="u", smtp_password="test-only-pw", imap_host="imap.example.test")
    a = SmtpImapEmail(s)
    a.send(from_addr="calls@example.test", to="ava@example.test", subject="Hi", body="x")
    assert isinstance(seen["starttls"], ssl.SSLContext) and seen["starttls"].verify_mode == ssl.CERT_REQUIRED and seen["starttls"].check_hostname
    assert seen["to"] == ["ava@example.test"]
    s.smtp_port = 465
    a.send(from_addr="calls@example.test", to="ava@example.test", subject="Hi", body="x")
    assert seen["ssl_ctx"].verify_mode == ssl.CERT_REQUIRED
    captured = {}

    class FakeImap:
        def __init__(self, host, port, ssl_context=None):
            captured["ctx"] = ssl_context

        def login(self, *a):
            pass

        def logout(self):
            pass

    import imaplib

    monkeypatch.setattr(imaplib, "IMAP4_SSL", FakeImap)
    a._imap()
    assert captured["ctx"].verify_mode == ssl.CERT_REQUIRED


def test_plain_text_mail_is_refused_for_a_server_that_is_not_this_computer(tmp_path):
    s = make_settings(tmp_path, smtp_host="smtp.example.test", smtp_use_tls=False, imap_host="imap.example.test", imap_use_ssl=False, smtp_user="u")
    a = SmtpImapEmail(s)
    with pytest.raises(AdapterError):
        a._smtp()
    with pytest.raises(AdapterError):
        a._imap()
    with pytest.raises(AdapterError):
        SmtpImapEmail(make_settings(tmp_path, smtp_host="smtp.example.test")).send(from_addr="a@b.test", to="x@y.test, z@w.test", subject="s", body="b")


# ---- configuration and the data folder
def test_every_setting_is_in_env_example_and_in_the_environment_variables_guide():
    root = Path(__file__).resolve().parents[3]
    example, guide = (root / ".env.example").read_text(), (root / "docs" / "04-ENVIRONMENT-VARIABLES.md").read_text()
    missing_example = [n.upper() for n in Settings.model_fields if not re.search(rf"^{n.upper()}=", example, re.M)]
    missing_guide = [n.upper() for n in Settings.model_fields if f"`{n.upper()}`" not in guide]
    assert not missing_example, f"not in .env.example: {missing_example}"
    assert not missing_guide, f"not in docs/04-ENVIRONMENT-VARIABLES.md: {missing_guide}"
    assert Settings(_env_file=root / ".env.example").demo_mode is True  # the example file itself loads


def test_the_app_finds_its_data_through_seed_dir_not_through_where_the_package_is(tmp_path, monkeypatch):
    data = tmp_path / "copy-of-data"
    shutil.copytree(DATA, data)
    monkeypatch.setattr(datadir, "CHECKOUT_DATA", tmp_path / "no-such-folder")  # an installed package has no data folder next to it
    st = make_settings(tmp_path, seed_dir=str(data))
    eng = make_engine(st.database_url)
    Base.metadata.create_all(eng)
    ctx = Ctx(st, make_session_factory(eng))
    app = create_app(st, ctx)
    assert seed_empty_demo(app) is True
    c = TestClient(app)
    token = c.post("/api/auth/login", json={"email": "owner@example.test", "password": "demo-password-1"}).json()["token"]
    h = {"x-session": token, "x-ringlark": "1"}
    assert len(c.get("/api/personas", headers=h).json()) == 14
    assert c.post("/api/demo/tick", headers=h).status_code == 200
    with ctx.factory() as s:
        assert s.scalar(select(Campaign.id)) is not None


def test_alembic_reads_the_same_settings_as_the_app_and_never_falls_back_to_sqlite(tmp_path, monkeypatch):
    from alembic import command
    from alembic.config import Config

    api = Path(__file__).resolve().parents[1]

    def cfg():
        c = Config(str(api / "alembic.ini"))
        c.set_main_option("script_location", str(api / "alembic"))
        return c

    monkeypatch.delenv("DATABASE_URL", raising=False)
    empty = tmp_path / "empty.env"
    empty.write_text("MODE=draft\n")
    monkeypatch.setenv("ENV_FILE", str(empty))
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        command.upgrade(cfg(), "head")
    db = tmp_path / "from-env-file.sqlite3"
    envf = tmp_path / "real.env"
    envf.write_text(f"DATABASE_URL=sqlite:///{db}\n")
    monkeypatch.setenv("ENV_FILE", str(envf))
    command.upgrade(cfg(), "head")
    assert db.exists()


def test_the_version_is_one_number_everywhere(tmp_path):
    import json
    import tomllib

    root = Path(__file__).resolve().parents[3]
    py = tomllib.loads((root / "apps" / "api" / "pyproject.toml").read_text())["project"]["version"]
    assert py == json.loads((root / "package.json").read_text())["version"] == json.loads((root / "apps" / "web" / "package.json").read_text())["version"] == "1.0.1"
    from ringlark.api.app import create_app as ca

    assert ca(Settings(_env_file=None, database_url=f"sqlite:///{tmp_path / 'version.sqlite3'}")).version == py
