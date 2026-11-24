import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import score_tools  # noqa: E402

DATA = json.loads(score_tools.DATA.read_text(encoding="utf-8"))


def test_real_data_is_valid_and_the_document_is_current():
    assert score_tools.validate(DATA) == []
    assert score_tools.main(["--check"]) == 0


def test_every_tool_has_six_scores_with_evidence_and_a_dated_source():
    for g in DATA["groups"]:
        for t in g["tools"]:
            assert set(t["scores"]) == set(score_tools.EXPECTED_WEIGHTS)
            assert all(len(c["evidence"]) >= 20 for c in t["scores"].values())
            assert all(s["checked"] == DATA["dated"] for s in t["sources"])


def test_weighted_total_and_closeness_by_hand():
    tool = {"scores": {"fit": {"score": 80}, "setup": {"score": 60}, "reliability": {"score": 50}, "cost": {"score": 100}, "data": {"score": 0}, "integration": {"score": 40}}}
    # 80*.35 + 60*.15 + 50*.15 + 100*.15 + 0 + 40*.10 = 28 + 9 + 7.5 + 15 + 4 = 63.5
    assert score_tools.total(tool, score_tools.EXPECTED_WEIGHTS) == 63.5
    ref = {"scores": {"fit": {"score": 90}}}
    assert score_tools.closeness(tool, ref) == 89


def test_validation_catches_bad_weights_ranges_and_missing_evidence():
    bad = copy.deepcopy(DATA)
    bad["weights"]["fit"] = 30
    assert any("weights" in e for e in score_tools.validate(bad))
    bad = copy.deepcopy(DATA)
    bad["groups"][0]["tools"][0]["scores"]["fit"]["score"] = 101
    assert any("0 to 100" in e for e in score_tools.validate(bad))
    bad = copy.deepcopy(DATA)
    bad["groups"][0]["tools"][0]["scores"]["cost"]["evidence"] = ""
    assert any("evidence" in e for e in score_tools.validate(bad))
    bad = copy.deepcopy(DATA)
    del bad["groups"][0]["tools"][0]["scores"]["data"]
    assert any("missing criterion" in e for e in score_tools.validate(bad))


def test_every_tool_named_in_the_adapter_registry_is_scored():
    ids = {t["id"] for g in DATA["groups"] for t in g["tools"]}
    for name in ("smtp_imap", "sendkit", "telnyx", "calcom", "google_calendar", "twenty", "hubspot", "notion"):
        assert name in ids


@pytest.mark.parametrize("tool_id", ["hubspot", "twenty"])
def test_crm_pair_is_present_for_the_hub_first_pass_comparison(tool_id):
    assert tool_id in score_tools.compute(DATA)["crm"]
