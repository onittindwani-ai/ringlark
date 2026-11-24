import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_docs_pass_the_doc_checker():
    p = subprocess.run([sys.executable, str(ROOT / "tools" / "check_docs.py")], capture_output=True, text=True)
    assert p.returncode == 0, p.stdout


def test_measured_file_has_the_numbers_the_docs_quote():
    m = json.loads((ROOT / "data" / "measured.json").read_text())
    assert {"tests", "browser_tests", "screenshots", "adapters_registered", "contract_tests", "reader"} <= set(m)
    assert m["reader"]["set_b_first"]["lines"] == 137
