"""The independent evaluation tool, on a tiny set written for this test (not one of the real sets)."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
import eval_independent as ev  # noqa: E402


def make_set(tmp_path):
    inp = {"set": "T", "utterances": [
        {"id": "T-U1", "channel": "voice", "language": "en", "industry": "x", "agent_line": "Hi?", "caller_utterance": "Please stop calling me."},
        {"id": "T-U2", "channel": "voice", "language": "en", "industry": "x", "agent_line": "Hi?", "caller_utterance": "Can I speak to a manager?"},
        {"id": "T-U3", "channel": "voice", "language": "en", "industry": "x", "agent_line": "(call connects)", "caller_utterance": "Leave a message after the beep."},
    ], "scripts": [
        {"id": "T-S1", "channel": "voice", "industry": "x", "language": "en", "caller_turns": ["Hello?", "Yes sure.", "Tuesday at 3 works, I'm Sam Park."]},
        {"id": "T-S2", "channel": "voice", "industry": "x", "language": "en", "caller_turns": ["Hello?", "Stop calling me.", "I said stop."]},
    ]}
    key = {"set": "T", "utterances": {
        "T-U1": {"label": "do_not_call", "acceptable_labels": ["do_not_call"], "ambiguous": False, "must_stop": "stop_at_once", "tags": []},
        "T-U2": {"label": "transfer_request", "acceptable_labels": ["transfer_request", "interest"], "ambiguous": True, "must_stop": "no", "tags": []},
        "T-U3": {"label": "voicemail", "acceptable_labels": ["voicemail"], "ambiguous": False, "must_stop": "end_politely", "tags": ["machine"]},
    }, "scripts": {
        "T-S1": {"expected_outcome": "booked", "acceptable_outcomes": ["booked"], "ambiguous": False, "required_compliance": ["DISCLOSE_AI_AT_OPENING", "HONOR_CALLBACK_TIME"], "stop_after_turn": None},
        "T-S2": {"expected_outcome": "do_not_call", "acceptable_outcomes": ["do_not_call"], "ambiguous": False, "required_compliance": ["STOP_IMMEDIATELY", "ADD_TO_SUPPRESSION"], "stop_after_turn": 2},
    }}
    (tmp_path / "input.json").write_text(json.dumps(inp))
    (tmp_path / "key.json").write_text(json.dumps(key))
    return tmp_path


def test_loader_joins_input_and_key(tmp_path):
    data = ev.load_set(make_set(tmp_path))
    assert [u["id"] for u in data["utterances"]] == ["T-U1", "T-U2", "T-U3"]
    assert data["utterances"][1]["acceptable"] == ["interest", "transfer_request"] and data["scripts"][1]["stop_after_turn"] == 2


def test_loader_refuses_mismatched_ids(tmp_path):
    folder = make_set(tmp_path)
    key = json.loads((folder / "key.json").read_text())
    del key["utterances"]["T-U3"]
    (folder / "key.json").write_text(json.dumps(key))
    try:
        ev.load_set(folder)
    except KeyError:
        return
    raise AssertionError("a missing key entry must fail loudly")


def test_scoring_runs_and_reports_the_compliance_slice(tmp_path):
    r = ev.evaluate(make_set(tmp_path), "t")
    u, s = r["utterances"], r["scripts"]
    assert u["total"] == 3 and u["compliance"]["stop_at_once_items"] == 1 and u["compliance"]["stop_at_once_stopped"] == 1
    assert s["total"] == 2 and s["stop_scripts"] == 1 and s["stop_scripts_stopped_in_time"] == 1
    assert "HONOR_CALLBACK_TIME" in s["codes_not_measured_by_this_harness"]  # an unchecked code is never counted as passed
    assert ev.headline(r)["utterances"] == 3


def test_a_stop_request_wins_even_with_a_prompt_that_says_nothing_about_stopping(tmp_path):
    data = ev.load_set(make_set(tmp_path))
    weak = "You are Casey. Call patients and book them."  # no stop directive: the code stop guard still ends the call
    r = ev.score_scripts(data["scripts"], weak)
    assert r["stop_scripts_stopped_in_time"] == 1 and r["stop_scripts_not_stopped_ids"] == []


def test_a_script_where_the_agent_goes_on_after_the_stop_is_a_failure(tmp_path, monkeypatch):
    class Stubborn:  # never ends the call
        def open(self):
            return []

        def reply(self, text):
            return []

    monkeypatch.setattr(ev, "new_agent", lambda prompt, tools: Stubborn())
    r = ev.score_scripts(ev.load_set(make_set(tmp_path))["scripts"], "x")
    assert r["stop_scripts_stopped_in_time"] == 0 and r["stop_scripts_not_stopped_ids"] == ["T-S2"]


def test_outcome_table_covers_every_agent_ending_that_has_a_reading():
    assert ev.OUTCOME_OF_DISPOSITION["transferred"] == "transferred_to_human" and ev.OUTCOME_OF_DISPOSITION["ivr_no_human"] == "phone_menu_navigated"


def test_a_model_run_works_against_a_local_fake_and_a_stop_request_is_never_left_to_the_model(tmp_path, monkeypatch):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from mock.anthropic_mock import FakeAnthropic
    from sendora_core.llm import build_llm, reset_budgets
    from sendora_core.settings import BaseAppSettings

    folder = make_set(tmp_path)
    answers = {"agent": json.dumps({"say": "Sure.", "tool_calls": []}), "read": json.dumps({"label": "interest", "confidence": 0.5, "reason": "x"})}
    with FakeAnthropic(lambda b: answers["read"] if "[task:read_caller]" in b["messages"][0]["content"] else answers["agent"]) as fake:
        reset_budgets()
        cfg = BaseAppSettings(_env_file=None, llm_backend="anthropic", anthropic_api_key="fake-key-for-local-server", anthropic_base_url=fake.url)
        monkeypatch.setattr(ev, "LLM_OBJ", build_llm(cfg, None))
        r = ev.evaluate(folder, "t")
    u = r["utterances"]
    assert u["compliance"]["stop_at_once_stopped"] == 1  # the stop line was handled by the rules, whatever the model said
    assert r["engine"].startswith("language model") and fake.requests
