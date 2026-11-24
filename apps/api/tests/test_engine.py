import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from ringlark import demo, dialer, followups, intake, jobs, metrics, prompts, qa, waveform
from ringlark.agent_offline import prompt_flags
from ringlark.models import Agent, Call, Campaign, Disposition, FollowUp, PromptVersion, QAScore, Suppression, Target
from ringlark.personas import load_personas, run_suite
from ringlark.postcall import process_call, rule_disposition, store_turns
from ringlark.toolauth import check_token, tool_token
from ringlark.tools import ToolService
from sendora_core.models import Approval
from conftest import DATA, NOW

STRONG = next(a for a in json.loads((DATA / "seed.json").read_text())["agents"] if a["name"] == "Casey")["versions"][1]["body"]
WEAK = next(a for a in json.loads((DATA / "seed.json").read_text())["agents"] if a["name"] == "Casey")["versions"][0]["body"]


def casey(session):
    return session.scalars(select(Agent).where(Agent.name == "Casey")).one()


def a_call(session, seeded, **kw):
    camp = session.get(Campaign, seeded["info"]["campaign_id"])
    t = session.scalars(select(Target).where(Target.status == "new").order_by(Target.id)).first()
    c = Call(campaign_id=camp.id, target_id=t.id, agent_id=camp.agent_id, peer_phone=t.phone, status="in_progress", telnyx_call_id="seed-cc-1", **kw)
    session.add(c); session.flush()
    return c, t


# ---- persona suite
def test_prompt_flags_read_the_directives():
    assert all(prompt_flags(STRONG)[k] for k in ("stop_on_request", "admit_ai", "transfer_on_request", "no_pricing", "no_leak", "ivr_hangup", "callback_when_busy", "brief"))
    assert not any(prompt_flags(WEAK).values())


def test_a_strong_prompt_beats_a_weak_one_on_every_set():
    for name in ("dev", "heldout", "heldout2"):
        strong, weak = run_suite(load_personas(name), STRONG), run_suite(load_personas(name), WEAK)
        assert strong["passed"] > weak["passed"], name


def test_persona_files_have_the_required_categories_and_answer_keys():
    need = {"hostile", "rushed", "wrong_number", "stop_calling", "voicemail", "ivr", "robot_question"}
    for name in ("dev", "heldout", "heldout2"):
        ps = load_personas(name)
        assert len(ps) == 14 and need <= {p["category"] for p in ps}
        assert all("disposition" in p["expect"] and "suppress" in p["expect"] for p in ps)


def test_first_runs_were_saved_and_the_honest_numbers_are_in_them():
    h1 = json.loads((DATA / "eval" / "persona_heldout_first_run.json").read_text())
    h2 = json.loads((DATA / "eval" / "persona_heldout2_first_run.json").read_text())
    assert (h1["passed"], h1["personas"]) == (12, 14) and (h2["passed"], h2["personas"]) == (7, 14)


# ---- prompts
def test_versions_diff_activate_and_split(session, seeded):
    ag = casey(session)
    assert [v.version for v in ag.versions] == [1, 2] and ag.active_version_id == ag.versions[1].id
    v3 = prompts.add_version(session, ag, STRONG + "\n- Always offer a callback when asked.", "More callbacks", "tester")
    assert v3.version == 3
    d = prompts.diff(ag.versions[1].body, v3.body)
    assert [x for x in d if x["kind"] == "add"][0]["text"].startswith("- Always offer") and not [x for x in d if x["kind"] == "del"]
    with pytest.raises(prompts.PromptError):
        prompts.add_version(session, ag, "too short", "", "tester")
    prompts.set_split(session, ag, v3.id, 0.3, "tester")
    picks = [prompts.choose_version(ag, f"k{i}") for i in range(2000)]
    share = picks.count(v3.id) / 2000
    assert 0.25 < share < 0.35 and prompts.choose_version(ag, "k7") == prompts.choose_version(ag, "k7")
    with pytest.raises(prompts.PromptError):
        prompts.set_split(session, ag, ag.active_version_id, 0.3)
    prompts.activate(session, ag, v3.id, "tester")
    assert ag.active_version_id == v3.id and not ag.ab_enabled


# ---- tools
def test_tool_token_is_per_call():
    assert check_token("s", 5, tool_token("s", 5)) and not check_token("s", 6, tool_token("s", 5)) and not check_token("s", 5, None) and not check_token("t", 5, tool_token("s", 5))


def test_end_call_with_do_not_call_suppresses_and_stops_the_target(session, ctx, seeded):
    c, t = a_call(session, seeded)
    out = ToolService(session, ctx, c).run("end_call", {"disposition": "do_not_call"})
    assert out["ok"] and c.disposition == "do_not_call" and t.status == "suppressed"
    assert session.scalars(select(Suppression).where(Suppression.phone == c.peer_phone)).first()
    assert ToolService(session, ctx, c).run("end_call", {"disposition": "made up"})["disposition"] == "needs_review"


def test_text_only_goes_to_the_person_on_the_call_and_only_with_consent(session, ctx, seeded):
    c, t = a_call(session, seeded)
    t.sms_consent, t.timezone = False, "America/New_York"
    svc = ToolService(session, ctx, c)
    svc.now = datetime(2026, 12, 1, 17, 0, tzinfo=UTC)
    assert not svc.run("send_sms", {"kind": "callback"})["ok"]
    assert session.scalars(select(FollowUp)).first().blocked_reason == "no_sms_consent"
    t.sms_consent = True
    assert svc.run("send_sms", {"kind": "callback", "to": "+14155550183"})["ok"], "a number in the arguments is ignored"
    assert session.scalars(select(FollowUp).where(FollowUp.status == "sent")).one().to == c.peer_phone
    assert not svc.run("send_sms", {"kind": "write_anything"})["ok"]
    svc.now = datetime(2026, 12, 1, 3, 0, tzinfo=UTC)  # 22:00 in New York
    assert svc.run("send_sms", {"kind": "callback"})["ok"] is False


def test_transfer_goes_only_to_the_configured_number_and_only_in_office_hours(session, ctx, seeded):
    c, _ = a_call(session, seeded)
    svc = ToolService(session, ctx, c)
    svc.now = datetime(2026, 12, 1, 17, 0, tzinfo=UTC)
    assert svc.run("transfer_to_human", {"reason": "x", "to": "+14155550185"})["ok"]
    assert ctx.adapters.telephony.log[-1] == ("transfer", "+14155550199")
    svc.now = datetime(2026, 12, 6, 17, 0, tzinfo=UTC)  # Sunday
    assert not svc.run("transfer_to_human", {})["ok"]
    for closed in (datetime(2026, 12, 1, 13, 59, tzinfo=UTC), datetime(2026, 12, 1, 22, 0, tzinfo=UTC)):  # 08:59 and 17:00 in New York
        svc.now = closed
        assert not svc.run("transfer_to_human", {})["ok"]
    svc.now = datetime(2026, 12, 1, 14, 0, tzinfo=UTC)  # 09:00 in New York, open
    assert svc.run("transfer_to_human", {})["ok"]


def test_press_digit_obeys_the_campaign_and_works_once(session, ctx, seeded):
    c, _ = a_call(session, seeded)
    camp = session.get(Campaign, c.campaign_id)
    svc = ToolService(session, ctx, c)
    assert not svc.run("press_digit", {"digit": "1"})["ok"]
    camp.ivr_policy, camp.ivr_extension = "press_once", "1"
    assert svc.run("press_digit", {"digit": "2"})["ok"] is False
    assert svc.run("press_digit", {"digit": "1"})["ok"] and not svc.run("press_digit", {"digit": "1"})["ok"]


def test_booking_needs_a_name_and_an_email_and_is_blocked_in_draft_mode(session, ctx, seeded):
    c, t = a_call(session, seeded)
    svc = ToolService(session, ctx, c, {"Tuesday at 3 pm": NOW + timedelta(days=1)})
    assert not svc.run("book_meeting", {"slot": "Tuesday at 3 pm"})["ok"]
    assert svc.run("book_meeting", {"slot": "Tuesday at 3 pm", "name": "Ava Alder"})["ok"]
    ctx.settings = ctx.settings.model_copy(update={"mode": "draft"})
    svc2 = ToolService(session, ctx, c, {"Tuesday at 3 pm": NOW + timedelta(days=1)})
    out = svc2.run("book_meeting", {"slot": "Tuesday at 3 pm", "name": "Ava Alder"})
    assert out["ok"] is False and out["blocked"] is True


# ---- post call, QA, follow ups
def test_postcall_sets_disposition_qa_followups_and_approval(session, ctx, seeded):
    c, t = a_call(session, seeded)
    t.sms_consent = True
    store_turns(session, c, [("agent", "Hi, this is Casey, an AI assistant calling for Harbor Light Dental. This call may be recorded and transcribed. Is now okay?"), ("caller", "Yes please"), ("agent", "Great, booked.")])
    ToolService(session, ctx, c).run("end_call", {"disposition": "booked"})
    r = process_call(session, ctx, c)
    assert r["disposition"] == "booked" and r["qa"] == 100 and r["followups"] >= 1
    assert c.processed and "booked" in c.summary
    assert session.scalars(select(Approval).where(Approval.action == "followup.send")).first()
    assert process_call(session, ctx, c) == {"skipped": True}


def test_postcall_catches_a_stop_request_the_agent_missed(session, ctx, seeded):
    c, t = a_call(session, seeded)
    store_turns(session, c, [("agent", "Hi, this is Casey, an AI assistant. This call may be recorded."), ("caller", "Please stop calling me."), ("agent", "Sure, but can I offer a cleaning first?")])
    process_call(session, ctx, c)
    assert c.disposition == "do_not_call" and t.status == "suppressed"
    q = session.scalars(select(QAScore).where(QAScore.call_id == c.id)).one()
    assert q.flagged and "honoured_stop" in q.flag_note


def test_qa_scores_are_code(session):
    good = [{"speaker": "agent", "text": "Hi, this is Casey, an AI assistant. This call may be recorded."}, {"speaker": "caller", "text": "ok"}, {"speaker": "agent", "text": "Thanks."}]
    assert qa.score_call(good, "booked")["score"] == 100
    bad = [{"speaker": "agent", "text": "Hi, I am a real person from the practice and it costs $80."}]
    s = qa.score_call(bad, "needs_review")
    assert s["flagged"] and not s["checks"]["disclosed_ai"] and not s["checks"]["no_invented_price"] and not s["checks"]["no_human_claim"]
    assert rule_disposition([{"speaker": "caller", "text": "remove me from your list"}]) == "do_not_call" and rule_disposition([]) == "no_answer"
    assert sum(qa.sampled(i) for i in range(1000)) in range(150, 260)


def test_followups_wait_for_approval_then_respect_the_do_not_call_list(session, ctx, seeded):
    c, t = a_call(session, seeded)
    t.sms_consent, t.timezone = True, "America/New_York"
    store_turns(session, c, [("agent", "Hi, this is Casey, an AI assistant. Recorded."), ("caller", "Book me")])
    ToolService(session, ctx, c).run("end_call", {"disposition": "interested_callback"})
    process_call(session, ctx, c)
    now = datetime(2026, 12, 1, 17, 0, tzinfo=UTC)
    assert followups.send_due(session, ctx.settings, ctx.adapters, now)["waiting"] == 1
    ap = session.scalars(select(Approval).where(Approval.action == "followup.send")).first()
    from sendora_core.approvals import decide
    decide(session, ap.id, True, "o@x", "owner")
    from ringlark.suppression import add_suppression
    add_suppression(session, c.peer_phone, "later", "test")
    assert followups.send_due(session, ctx.settings, ctx.adapters, now)["blocked"] == 1


# ---- misc
def test_waveform_is_labelled_synthetic_and_follows_the_turns():
    turns = [{"speaker": "agent", "text": "hello there friend", "start_ms": 0, "end_ms": 2000}, {"speaker": "caller", "text": "hi", "start_ms": 3000, "end_ms": 4000}]
    w = waveform.build(turns, 5000)
    assert w["synthetic"] and len(w["agent"]) == 120 and max(w["agent"][:48]) > 0 and max(w["caller"][:60]) == 0 and max(w["caller"][72:96]) > 0


def test_import_flags_bad_rows_and_drops_duplicates(session, seeded):
    camp = seeded["info"]["campaign_id"]
    rep = intake.import_targets(session, camp, [{"phone": "+14155550100"}, {"phone": "+14155550188", "timezone": "Europe/London"}, {"phone": "12", "timezone": "x"}])
    assert rep.duplicates == 1 and rep.created == 2 and rep.flagged == {"bad_number": 1, "unknown_timezone": 1}


def test_demo_cycle_places_answers_and_processes(session, ctx):
    with ctx.factory() as s:
        out = demo.reset(s, ctx)
    with ctx.factory() as s:
        r = jobs.run_cycle(s, ctx)
        s.commit()
        assert r["dial"]["placed"] > 15 and r["answered"] == r["dial"]["placed"] and r["postcall"]["processed"] >= r["answered"]
        m = metrics.overview(s, ctx.now(s))
        assert m["booked"] > 0 and m["avg_qa"] and m["calls"] > 30
        ev = demo.replay_events(s.scalars(select(Call).where(Call.processed.is_(True)).order_by(Call.id.desc())).first())
        assert ev[0]["state"] == "ringing" and ev[-1]["state"] == "ended" and any(e["type"] == "word" for e in ev)


def test_model_backend_follows_llm_backend(ctx, session):
    from ringlark.offline_llm import OfflineBackend

    assert ctx.settings.effective_llm_backend.value == "offline"
    assert isinstance(ctx.llm(session).backend, OfflineBackend)
    from sendora_core.llm import FixtureLLM
    from sendora_core.settings import LLMBackendKind

    ctx.settings.llm_backend = LLMBackendKind.FIXTURE
    ctx.settings.llm_fixtures_dir = str(DATA / "no_such_fixture_folder")

    assert isinstance(ctx.llm(session).backend, FixtureLLM)
