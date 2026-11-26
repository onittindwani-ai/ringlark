"""Record the model answers for the persona sets into data/llm_fixtures/, so the demo can replay them with LLM_BACKEND=fixture.

IMPORTANT: these are NOT answers of a real model. The recording goes through the real anthropic code path (request building, schema,
response parsing, the guards around the agent) against a local mock server that answers with the offline stand in. So the fixtures prove the
replay path and the request shape, not model quality. Replace them with a recording from a real key (LLM_RECORD=true) when you have one.

Run: python tools/record_llm_fixtures.py
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "apps" / "api" / "src"))
sys.path.insert(0, str(ROOT))

from mock.anthropic_mock import StubAnthropic  # noqa: E402
from ringlark.agent_live import LiveModelAgent  # noqa: E402
from ringlark.config import Settings  # noqa: E402
from ringlark.offline_llm import OfflineBackend  # noqa: E402
from ringlark.personas import load_personas, run_persona  # noqa: E402
from sendora_core.llm import build_llm, reset_budgets  # noqa: E402

OUT = ROOT / "data" / "llm_fixtures"


def strong_prompt() -> str:
    agent = next(a for a in json.loads((ROOT / "data" / "seed.json").read_text(encoding="utf-8"))["agents"] if a["name"] == "Casey")
    return agent["versions"][agent["active_version"] - 1]["body"]


def answer_like_the_offline_agent(body: dict) -> str:
    return OfflineBackend().complete(model=body["model"], system=body.get("system", ""), prompt=body["messages"][0]["content"], max_tokens=body["max_tokens"]).text


def record() -> dict:
    if OUT.exists():
        shutil.rmtree(OUT)
    prompt, runs = strong_prompt(), 0
    with StubAnthropic(answer_like_the_offline_agent) as stub:
        settings = Settings(_env_file=None, llm_backend="anthropic", anthropic_api_key="stub-key-for-local-server", anthropic_base_url=stub.url, llm_record=True,
                            llm_fixtures_dir=str(OUT), database_url="sqlite://")
        reset_budgets()
        llm = build_llm(settings, None)
        for name in ("dev", "heldout", "heldout2"):
            for persona in load_personas(name):
                run_persona(persona, prompt, backend_factory=lambda tools, c: LiveModelAgent(llm, prompt, dict(c), tools))
                runs += 1
    files = len(list(OUT.glob("*.json")))
    (OUT / "README.txt").write_text(
        "Recorded from a LOCAL MOCK server that answers with the offline stand in. Not answers of a real model.\n"
        "They prove the replay path and the request shape only. Regenerate: python tools/record_llm_fixtures.py\n", encoding="utf-8")
    return {"personas_played": runs, "files": files, "requests_to_mock_server": len(stub.requests)}


if __name__ == "__main__":
    print(json.dumps(record()))
