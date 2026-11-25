"""Texts: nobody who said stop is texted, by any path (follow ups, the in call tool, the queue after a call)."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from conftest import NOW
from ringlark import followups, live, sms_rules
from ringlark.models import Agent, Call, Campaign, ConsentRecord, Disposition, FollowUp, Target
from ringlark.postcall import process_call, store_turns
from ringlark.suppression import add_suppression, latest_consent
from ringlark.tools import ToolService
from sendora_core.approvals import decide
from sendora_core.models import Approval
from spies import SpyEmail, SpySms


def booked_call(session, seeded, line="Yes, Tuesday works. Thank you."):
    camp = session.get(Campaign, seeded["info"]["campaign_id"])
    t = session.scalars(select(Target).where(Target.status == "new", Target.sms_consent.is_(True), Target.timezone == "America/New_York").order_by(Target.id)).first()
    c = Call(campaign_id=camp.id, target_id=t.id, agent_id=camp.agent_id, peer_phone=t.phone, status="in_progress", telnyx_call_id="seed-cc-9")
    session.add(c); session.flush()
    session.add(Disposition(call_id=c.id, code="booked", set_by="agent"))
    store_turns(session, c, [("agent", "Hi, this is Casey, an AI assistant."), ("caller", line), ("agent", "Great, you are booked.")])
    return c, t


def sms_rows(session, call):
    return list(session.scalars(select(FollowUp).where(FollowUp.call_id == call.id, FollowUp.channel == "sms")))


def test_a_person_who_says_do_not_text_me_on_the_call_gets_no_text_queued(session, ctx, seeded):
    c, t = booked_call(session, seeded, "Don't text me anymore, but yes, book Tuesday.")
    process_call(session, ctx, c)
    assert sms_rows(session, c) == []


def test_a_person_who_agreed_gets_the_text_queued_in_the_businesses_words(session, ctx, seeded):
    c, t = booked_call(session, seeded)
    process_call(session, ctx, c)
    (fu,) = sms_rows(session, c)
    assert fu.body.startswith("Harbor Light Dental:") and fu.body.endswith("Reply STOP to opt out.")


def test_a_stop_text_that_arrives_after_approval_blocks_the_send(session, ctx, seeded):
    c, t = booked_call(session, seeded)
    process_call(session, ctx, c)
    (fu,) = sms_rows(session, c)
    decide(session, fu.approval_id, True, "owner@example.test", "owner", None)
    assert live.handle_sms(session, {"id": "m-1", "from": {"phone_number": t.phone}, "text": "STOP"}) == "sms_opt_out"
    sms = SpySms()
    adapters = type("A", (), {"sms": sms, "email": SpyEmail()})()
    out = followups.send_due(session, ctx.settings, adapters, NOW)
    assert sms.sent == [] and out["blocked"] >= 1
    assert session.get(FollowUp, fu.id).status == "blocked" and session.get(FollowUp, fu.id).blocked_reason == "sms_revoked"


def test_an_approved_text_to_someone_who_agreed_is_sent_once_with_the_stop_line(session, ctx, seeded):
    c, t = booked_call(session, seeded)
    process_call(session, ctx, c)
    (fu,) = sms_rows(session, c)
    decide(session, fu.approval_id, True, "owner@example.test", "owner", None)
    sms = SpySms()
    out = followups.send_due(session, ctx.settings, type("A", (), {"sms": sms, "email": SpyEmail()})(), NOW)
    assert out["sent"] >= 1 and len(sms.sent) == 1 and "Reply STOP" in sms.sent[0][1]
    followups.send_due(session, ctx.settings, type("A", (), {"sms": sms, "email": SpyEmail()})(), NOW)
    assert len(sms.sent) == 1


def test_the_do_not_call_list_also_stops_the_email_follow_up(session, ctx, seeded):
    c, t = booked_call(session, seeded)
    t.email = "ava@example.test"
    process_call(session, ctx, c)
    add_suppression(session, t.phone, "asked later", "test")
    for fu in session.scalars(select(FollowUp).where(FollowUp.call_id == c.id)):
        decide(session, fu.approval_id, True, "owner@example.test", "owner", None) if session.get(Approval, fu.approval_id).status == "pending" else None
    mail = SpyEmail()
    followups.send_due(session, ctx.settings, type("A", (), {"sms": SpySms(), "email": mail})(), NOW)
    assert mail.sent == []


def test_a_person_with_no_time_zone_is_never_texted(session, ctx, seeded):
    c, t = booked_call(session, seeded)
    t.timezone = ""
    d = sms_rules.sms_decision(session, ctx.settings, t.phone, t, NOW)
    assert not d and d.reason == "sms_no_timezone"
    out = ToolService(session, ctx, c).run("send_sms", {"kind": "confirmation"})
    assert out["ok"] is False


def test_quiet_hours_wait_instead_of_blocking(session, ctx, seeded):
    c, t = booked_call(session, seeded)
    night = datetime(2026, 12, 1, 3, 0, tzinfo=UTC)  # 22:00 in New York
    d = sms_rules.sms_decision(session, ctx.settings, t.phone, t, night)
    assert not d and d.later and d.reason == "sms_quiet_hours"


def test_the_in_call_tool_asks_the_same_rule_and_sends_each_kind_once(session, ctx, seeded):
    c, t = booked_call(session, seeded)
    sms = SpySms()
    ctx.adapters.sms = sms
    svc = ToolService(session, ctx, c)
    svc.now = NOW
    assert svc.run("send_sms", {"kind": "confirmation"})["ok"] is True
    again = svc.run("send_sms", {"kind": "confirmation"})
    assert again["ok"] is False and len(sms.sent) == 1
    add_suppression(session, t.phone, "asked", "test")
    assert svc.run("send_sms", {"kind": "callback"})["ok"] is False and len(sms.sent) == 1


def test_a_bare_yes_never_gives_texting_consent_and_start_only_after_stop(session):
    phone = "+14155550142"
    assert live.handle_sms(session, {"id": "a", "from": {"phone_number": phone}, "text": "yes"}) == "ignored"
    assert latest_consent(session, phone, "sms") is None
    assert live.handle_sms(session, {"id": "b", "from": {"phone_number": phone}, "text": "START"}) == "ignored"  # never stopped, nothing to restart
    live.handle_sms(session, {"id": "c", "from": {"phone_number": phone}, "text": "please stop texting me"})
    assert latest_consent(session, phone, "sms") == "revoked"
    assert live.handle_sms(session, {"id": "d", "from": {"phone_number": phone}, "text": "START"}) == "sms_opt_in"
    assert latest_consent(session, phone, "sms") == "granted"


def test_wider_stop_wording_is_read(session):
    for i, text in enumerate(["STOP ALL", "Please stop texting me", "opt out"]):
        phone = f"+1415555020{i}"
        assert live.handle_sms(session, {"id": f"s{i}", "from": {"phone_number": phone}, "text": text}).startswith("sms_")
        assert latest_consent(session, phone, "sms") == "revoked"


def test_a_stop_asking_to_stop_calling_puts_the_number_on_the_do_not_call_list(session):
    from ringlark.suppression import is_suppressed

    assert live.handle_sms(session, {"id": "z", "from": {"phone_number": "+14155550143"}, "text": "stop calling me"}) == "sms_do_not_call"
    assert is_suppressed(session, "+14155550143")


def test_a_replayed_message_changes_nothing_and_an_older_start_cannot_undo_a_newer_stop(session):
    phone = "+14155550144"
    now = datetime.now(UTC)
    live.handle_sms(session, {"id": "m1", "from": {"phone_number": phone}, "text": "STOP", "received_at": (now - timedelta(minutes=10)).isoformat()})
    live.handle_sms(session, {"id": "m2", "from": {"phone_number": phone}, "text": "START", "received_at": (now - timedelta(minutes=5)).isoformat()})
    live.handle_sms(session, {"id": "m3", "from": {"phone_number": phone}, "text": "STOP", "received_at": (now - timedelta(minutes=1)).isoformat()})
    assert latest_consent(session, phone, "sms") == "revoked"
    # the older START is delivered again, late: same id, so nothing happens; a copy with a new id but its old time is ordered by that time
    assert live.handle_sms(session, {"id": "m2", "from": {"phone_number": phone}, "text": "START", "received_at": (now - timedelta(minutes=5)).isoformat()}) == "duplicate"
    live.handle_sms(session, {"id": "m4", "from": {"phone_number": phone}, "text": "START", "received_at": (now - timedelta(minutes=4)).isoformat()})
    assert latest_consent(session, phone, "sms") == "revoked"
    assert len(list(session.scalars(select(ConsentRecord).where(ConsentRecord.phone == phone)))) == 4


def test_the_email_follow_up_names_the_business_and_carries_the_footer(session, ctx, seeded):
    c, t = booked_call(session, seeded)
    t.email = "ava@example.test"
    ctx.settings.company_address = "1 Harbor Road, Portland"
    process_call(session, ctx, c)
    (fu,) = list(session.scalars(select(FollowUp).where(FollowUp.call_id == c.id, FollowUp.channel == "email")))
    assert "Harbor Light Dental" in fu.subject and "1 Harbor Road, Portland" in fu.body and "Do not want these texts or emails?" in fu.body and "we will stop sending them" in fu.body and "contact you again" not in fu.body


def test_a_stop_text_after_approval_also_stops_the_email_because_the_footer_promises_it(session, ctx, seeded):
    c, t = booked_call(session, seeded)
    t.email = "ava@example.test"
    process_call(session, ctx, c)
    (fu,) = list(session.scalars(select(FollowUp).where(FollowUp.call_id == c.id, FollowUp.channel == "email")))
    decide(session, fu.approval_id, True, "owner@example.test", "owner", None)
    live.handle_sms(session, {"id": "m-stop", "from": {"phone_number": t.phone}, "text": "STOP"})
    email = SpyEmail()
    out = followups.send_due(session, ctx.settings, type("A", (), {"sms": SpySms(), "email": email})(), NOW)
    assert email.sent == [] and out["blocked"] >= 1
    assert session.get(FollowUp, fu.id).status == "blocked" and session.get(FollowUp, fu.id).blocked_reason == "stop_requested"


def test_a_follow_up_that_cannot_be_sent_does_not_hold_back_the_next_one(session, ctx, seeded):
    c, t = booked_call(session, seeded)
    session.add(FollowUp(call_id=c.id, channel="sms", to="+14155550301", body="Harbor Light Dental: hello. Reply STOP to opt out.", status="pending"))
    session.add(FollowUp(call_id=c.id, channel="sms", to=t.phone, body="Harbor Light Dental: your appointment is booked. Reply STOP to opt out.", status="pending"))
    session.flush()
    ctx.settings.follow_ups_need_approval = False
    sms = SpySms(fail_for={"+14155550301"})
    out = followups.send_due(session, ctx.settings, type("A", (), {"sms": sms, "email": SpyEmail()})(), NOW)
    assert out["failed"] == 1 and out["sent"] == 1 and len(sms.sent) == 1
