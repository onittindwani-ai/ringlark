"""Property tests on seeded random worlds. Each world is a random mix of times, time zones, rules and flags. The invariants must hold in every one."""

import random
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from ringlark import dialer
from ringlark.compliance import DialRequest, Rules, evaluate, in_calling_window, voicemail_allowed
from ringlark.models import Agent, Call, Campaign, ConsentRecord, Number, Suppression, Target
from ringlark.util import aware, zone
from ringlark.seeding import load_seed
from sendora_core.models import Event  # noqa: F401
from testkit import NOW, DATA, make_settings
from ringlark.seeding import read_seed

ZONES = ["America/New_York", "America/Chicago", "America/Los_Angeles", "Europe/London", "Asia/Kolkata", "Australia/Sydney", "Pacific/Auckland", "Mars/Olympus", ""]
PHONES = ["+14155550123"] * 8 + ["+442071838750"] * 4 + ["555-0100", "", "+0123"]
ZONES = ZONES[:5] * 3 + ZONES[5:]


def world(rnd: random.Random) -> DialRequest:
    start = rnd.randint(6, 12)
    rules = Rules(start, rnd.randint(start + 1, 21), rnd.random() < 0.7, rnd.randint(4, 10), rnd.randint(2, 5), rnd.randint(1, 2), rnd.random() < 0.1)
    now = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=rnd.randint(0, 60 * 24 * 365))
    last = now - timedelta(hours=rnd.randint(26, 100)) if rnd.random() < 0.4 else None
    dates = ()
    z = zone(rnd.choice(ZONES))
    tzname = rnd.choice(ZONES)
    if last and zone(tzname):
        dates = (last.astimezone(zone(tzname)).date().isoformat(),)
    return DialRequest(rnd.choice(PHONES), tzname, now, rules, kill_switch=rnd.random() < 0.04, draft_mode=rnd.random() < 0.05, greeting_has_disclosure=rnd.random() < 0.95, on_dnc_list=rnd.random() < 0.06,
                       call_consent=rnd.choice([None, None, "granted", "revoked"]), calls_today=rnd.randint(0, 9), attempts_before=rnd.randint(0, 4), last_attempt_local_dates=dates, last_attempt_utc=last, in_flight=rnd.random() < 0.03)


@pytest.mark.parametrize("seed", range(5))
def test_never_allowed_when_any_rule_is_broken(seed):
    rnd = random.Random(seed)
    allowed = 0
    for _ in range(600):
        r = world(rnd)
        d = evaluate(r)
        if d.allowed:
            allowed += 1
            loc = aware(r.now_utc).astimezone(zone(r.timezone))
            assert r.rules.window_start_hour <= loc.hour < r.rules.window_end_hour, "dialled outside the callee's hours"
            assert not (r.rules.weekdays_only and loc.weekday() >= 5)
            assert not r.kill_switch and not r.draft_mode and r.greeting_has_disclosure
            assert not r.on_dnc_list and r.call_consent != "revoked" and not (r.rules.require_prior_consent and r.call_consent != "granted")
            assert r.calls_today < r.rules.daily_cap and r.attempts_before < r.rules.max_attempts and not r.in_flight
            assert loc.date().isoformat() not in r.last_attempt_local_dates
            assert r.last_attempt_utc is None or (aware(r.now_utc) - aware(r.last_attempt_utc)).total_seconds() / 86400 >= r.rules.retry_gap_days
    assert allowed > 5, "the random worlds should include some allowed calls, or the test proves nothing"


def test_kill_switch_wins_over_everything():
    rnd = random.Random(99)
    for _ in range(300):
        r = world(rnd)
        assert not evaluate(DialRequest(**{**r.__dict__, "kill_switch": True})).allowed


def test_a_clean_world_is_allowed():
    now = datetime(2026, 12, 1, 17, 0, tzinfo=UTC)
    d = evaluate(DialRequest("+14155550123", "America/New_York", now, Rules()))
    assert d.allowed and d.reason == "ok"


def test_window_edges_in_callee_time():
    r = Rules(9, 17)
    assert in_calling_window(datetime(2026, 12, 1, 14, 0, tzinfo=UTC), "America/New_York", r)  # 09:00 local
    assert not in_calling_window(datetime(2026, 12, 1, 13, 59, tzinfo=UTC), "America/New_York", r)
    assert not in_calling_window(datetime(2026, 12, 1, 22, 0, tzinfo=UTC), "America/New_York", r)  # 17:00 local
    assert in_calling_window(datetime(2026, 12, 4, 17, 0, tzinfo=UTC), "America/New_York", r)  # Friday
    assert not in_calling_window(datetime(2026, 12, 5, 17, 0, tzinfo=UTC), "America/New_York", r)  # Saturday
    assert not in_calling_window(datetime(2026, 12, 6, 17, 0, tzinfo=UTC), "America/New_York", r)  # Sunday


def test_voicemail_rules():
    ok = "Hello, this is Casey, an AI assistant calling for Harbor Light Dental about your check up. Please call back."
    assert voicemail_allowed(True, ok) == (True, "ok")
    assert voicemail_allowed(False, ok) == (False, "voicemail_off")
    assert not voicemail_allowed(True, "Call us back soon please do")[0]


def build_world(session, rnd: random.Random):
    seed = read_seed(DATA)
    info = load_seed(session, seed, NOW, with_targets=False)
    camp = session.get(Campaign, info["campaign_id"])
    camp.daily_cap, camp.max_attempts, camp.retry_gap_days = rnd.randint(1, 6), rnd.randint(1, 3), rnd.randint(1, 2)
    camp.window_start_hour, camp.window_end_hour = rnd.randint(7, 11), rnd.randint(14, 19)
    for i in range(rnd.randint(8, 25)):
        phone = f"+1415555{100 + i:04d}"
        session.add(Target(campaign_id=camp.id, first_name="T", phone=rnd.choice([phone, phone, "555-0100"]), timezone=rnd.choice(ZONES), email="t@example.test"))
        if rnd.random() < 0.15:
            session.add(Suppression(phone=phone, reason="test", source="test"))
        if rnd.random() < 0.15:
            session.add(ConsentRecord(phone=phone, kind="call", status=rnd.choice(["granted", "revoked"]), source="test"))
    session.flush()
    return camp


@pytest.mark.parametrize("seed", range(12))
def test_dialer_worlds_keep_every_promise(seed, ctx, session):
    rnd = random.Random(1000 + seed)
    camp = build_world(session, rnd)
    now = datetime(2026, 1, 5, 0, 0, tzinfo=UTC) + timedelta(hours=rnd.randint(0, 24 * 40))
    settings = ctx.settings
    placed_total = 0
    for step in range(6):
        res = dialer.dial_tick(session, settings, ctx.adapters, now)
        placed_total += res.placed
        now += timedelta(hours=rnd.choice([1, 5, 23, 26]))
    calls = list(session.scalars(select(Call).where(Call.status == "placed")))
    assert len(calls) == placed_total
    per_day: dict[str, int] = {}
    for c in calls:
        t = session.get(Target, c.target_id)
        loc = aware(c.created_at).astimezone(zone(t.timezone))
        assert camp.window_start_hour <= loc.hour < camp.window_end_hour and loc.weekday() < 5
        assert not session.scalars(select(Suppression).where(Suppression.phone == c.peer_phone)).first()
        last = session.scalars(select(ConsentRecord).where(ConsentRecord.phone == c.peer_phone, ConsentRecord.kind == "call").order_by(ConsentRecord.id.desc())).first()
        assert last is None or last.status != "revoked"
        per_day[aware(c.created_at).date().isoformat()] = per_day.get(aware(c.created_at).date().isoformat(), 0) + 1
        assert c.attempt <= camp.max_attempts
    assert all(v <= camp.daily_cap for v in per_day.values())
    by_target: dict[int, list] = {}
    for c in calls:
        by_target.setdefault(c.target_id, []).append(c)
    for cs in by_target.values():
        assert len(cs) <= camp.max_attempts
        for a, b in zip(cs, cs[1:]):
            assert (aware(b.created_at) - aware(a.created_at)).total_seconds() >= camp.retry_gap_days * 86400 - 1


def open_time() -> datetime:
    return datetime(2026, 12, 1, 17, 0, tzinfo=UTC)


def test_kill_switch_stops_dialing_and_draft_places_no_call(ctx, session, seeded):
    s_kill = ctx.settings.model_copy(update={"kill_switch": True})
    r = dialer.dial_tick(session, s_kill, ctx.adapters, open_time())
    assert r.halted and r.placed == 0 and not any(a == "place" for a, _ in ctx.adapters.telephony.log)
    s_draft = ctx.settings.model_copy(update={"mode": "draft"})
    r = dialer.dial_tick(session, s_draft, ctx.adapters, open_time())
    assert r.placed == 0 and r.drafted > 0 and not any(a == "place" for a, _ in ctx.adapters.telephony.log)
    assert session.scalar(select(Call).where(Call.status == "placed")) is None
    again = dialer.dial_tick(session, s_draft, ctx.adapters, open_time())
    assert again.drafted == 0, "a draft is made once per target, not on every tick"


def test_no_call_without_the_ai_disclosure(ctx, session, seeded):
    agent = session.scalars(select(Agent).where(Agent.name == "Casey")).one()
    agent.greeting = "Hello there! We have a special offer on cleaning."
    r = dialer.dial_tick(session, ctx.settings, ctx.adapters, open_time())
    assert r.placed == 0 and r.reasons.get("no_ai_disclosure", 0) > 20


def test_the_demo_hour_places_the_expected_calls(ctx, session, seeded):
    r = dialer.dial_tick(session, ctx.settings, ctx.adapters, open_time(), limit=100)
    # The cap is 25 a day and two people were already tried this morning (seed), so 23 more calls fit.
    assert r.placed == 23 and r.reasons["daily_cap"] > 0 and r.reasons["outside_hours"] == 6
    assert dialer.calls_today(session, seeded["info"]["campaign_id"], open_time()) == 25
    assert sum(1 for a, _ in ctx.adapters.telephony.log if a == "place") == 23


MESSAGES = ["", "Call us back", "Hello, this is Casey, an AI assistant calling for Harbor Light Dental about your next check up. Please call the practice back.",
            "Hi, it is Casey from Harbor Light Dental calling about your check up, please ring us back soon.", "This is an automated call from Harbor Light Dental about your check up. Call back when you can."]


@pytest.mark.parametrize("seed", range(6))
def test_no_voicemail_unless_allowed_and_the_message_says_who_and_why(seed, ctx, session, seeded):
    from ringlark import live
    from ringlark.models import Campaign

    rnd = random.Random(seed)
    for i in range(40):
        camp = session.get(Campaign, seeded["info"]["campaign_id"])
        camp.allow_voicemail, camp.voicemail_text = rnd.random() < 0.5, rnd.choice(MESSAGES)
        eff = ctx.settings.model_copy(update={"kill_switch": rnd.random() < 0.2, "mode": rnd.choice(["live", "draft"])})
        c = Call(campaign_id=camp.id, agent_id=camp.agent_id, peer_phone="+14155550123", status="placed", telnyx_call_id=f"cc-{seed}-{i}")
        session.add(c); session.flush()
        before = len([a for a, _ in ctx.adapters.telephony.log if a == "speak"])
        code = live.handle_machine(session, ctx, eff, c)
        spoke = len([a for a, _ in ctx.adapters.telephony.log if a == "speak"]) > before
        ok, _ = voicemail_allowed(camp.allow_voicemail, camp.voicemail_text)
        if spoke:
            assert camp.allow_voicemail and ok and not eff.kill_switch and eff.mode.value == "live"
        assert (code == "voicemail_left") == spoke
        if not camp.allow_voicemail:
            assert code == "voicemail_no_message"


def test_the_offline_agent_leaves_a_voicemail_only_when_the_message_says_who_and_why():
    from ringlark.agent_offline import OfflineAgent

    text = "Hello, this is Casey, an AI assistant calling for Harbor Light Dental about your next check up. Please call back."
    ctx = {"agent_name": "Casey", "company": "Harbor Light Dental", "purpose": "a check up", "ivr_policy": "hangup", "ivr_extension": ""}
    for allow, body, code in ((True, text, "voicemail_left"), (True, "Please call us back.", "voicemail_no_message"), (False, text, "voicemail_no_message")):
        agent = OfflineAgent("You are Casey.", {**ctx, "allow_voicemail": allow, "voicemail_text": body}, None)
        turns = agent.first_contact("Please leave a message after the beep.")
        assert turns[-1].tool == "end_call" and turns[-1].args["disposition"] == code
        assert (turns[0].text == text) is (code == "voicemail_left")
