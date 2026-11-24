#!/usr/bin/env python3
"""Measure the numbers the docs quote and write them to data/measured.json.

Every count in README and docs/ comes from this file (the docs mark them as <!--n:path-->value<!--/n-->; tools/check_docs.py compares them).
  python3 tools/make_counts.py            measure and write (runs the Python tests once, with coverage)
  python3 tools/make_counts.py --fast     skip the test run and keep the last test and coverage numbers
The browser test count comes from `playwright test --list`; the number of browser runs and the screenshot check are not measured here.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "measured.json"
PY = str(ROOT / ".venv" / "bin" / "python") if (ROOT / ".venv" / "bin" / "python").exists() else sys.executable


def run_tests() -> dict:
    cov = ROOT / ".coverage-counts.json"
    p = subprocess.run([PY, "-m", "pytest", "-o", "addopts=", "-q", "-p", "no:warnings", "-p", "no:cacheprovider", "--cov=apps/api/src/ringlark", f"--cov-report=json:{cov}"],
                       cwd=ROOT, capture_output=True, text=True)
    grab = lambda word: int(m.group(1)) if (m := re.search(rf"(\d+) {word}", p.stdout)) else 0  # noqa: E731
    pct = None
    if cov.exists():
        pct = round(json.loads(cov.read_text())["totals"]["percent_covered"])
        cov.unlink()
    return {"passed": grab("passed"), "skipped": grab("skipped"), "failed": grab("failed"), "coverage_percent": pct}


def adapters() -> int:
    sys.path.insert(0, str(ROOT / "apps" / "api" / "src"))
    from ringlark.config import Settings
    from ringlark.registry import build_registry

    reg = build_registry(Settings(_env_file=None))
    return len(reg.describe())


def reader() -> dict:
    ind = ROOT / "data" / "eval" / "independent"
    load = lambda n: json.loads((ind / n).read_text(encoding="utf-8"))  # noqa: E731

    def row(name: str) -> dict:
        r = load(name)
        u, s, c = r["utterances"], r["scripts"], r["utterances"]["compliance"]
        return {"lines": u["total"], "strict": u["strict_correct"], "strict_percent": round(100 * u["strict_correct"] / u["total"], 1), "lenient": u["lenient_correct"],
                "must_stop": c["stop_at_once_items"], "must_stop_stopped": c["stop_at_once_stopped"], "clear_stop": c["clear_stop_items"], "clear_stop_stopped": c["clear_stop_stopped"],
                "scripts": s["total"], "outcome_strict": s["outcome_strict_correct"]}

    return {"set_a_first": row("set_a_first_run.json"), "set_a_after": row("set_a_after_tuning.json"), "set_b_first": row("set_b_first_run.json"),
            "set_a_final": row("set_a_final_offline.json"), "set_b_final": row("set_b_final_offline.json")}


def main(argv: list[str]) -> int:
    old = json.loads(OUT.read_text()) if OUT.exists() else {}
    scores = json.loads((ROOT / "data" / "tool_scores.json").read_text())
    lst = subprocess.run(["pnpm", "exec", "playwright", "test", "--list"], cwd=ROOT / "apps" / "web", capture_output=True, text=True).stdout
    mm = re.search(r"Total: (\d+) tests? in (\d+) files?", lst)
    contracts = len(re.findall(r"^def test_", (ROOT / "apps/api/tests/test_contracts.py").read_text(), re.M))
    data = {
        "measured_on": date.today().isoformat(),
        "tests": old.get("tests") if "--fast" in argv else run_tests(),
        "browser_tests": int(mm.group(1)) if mm else old.get("browser_tests"),
        "screenshots": len(list((ROOT / "docs" / "screenshots").glob("*.png"))),
        "adapters_registered": adapters(),
        "contract_tests": contracts,
        "tool_groups": len(scores["groups"]), "tools_scored": sum(len(g["tools"]) for g in scores["groups"]),
        "seed": json.loads((ROOT / "data" / "counts.json").read_text()),
        "reader": reader(),
    }
    OUT.write_text(json.dumps(data, indent=1) + "\n")
    print("OK wrote", OUT.relative_to(ROOT), json.dumps({k: data[k] for k in ("tests", "browser_tests", "screenshots", "adapters_registered", "contract_tests")}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
