import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import scan_secrets  # noqa: E402

REAL = "sk-ant-" + "A1b2C3d4E5f6G7h8I9j0K1l2"  # built in two parts so this file is not a hit itself


def test_a_real_looking_key_is_found_even_when_the_line_also_says_example():
    assert scan_secrets.kinds_in(f"ANTHROPIC_API_KEY={REAL}  # see https://example.test/docs") == ["Anthropic key"]


def test_a_fixture_value_that_is_marked_as_stub_is_let_through():
    assert scan_secrets.kinds_in('secret = "test-only-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"') == []
    assert scan_secrets.kinds_in("key: sk-ant-stub-aaaaaaaaaaaaaaaaaaaaaaaa") == []


def test_the_shared_packages_are_scanned_but_not_their_test_fixtures():
    root = scan_secrets.ROOT
    files = [f.relative_to(root).as_posix() for f in scan_secrets.tracked()]
    assert any(f.startswith("packages/core-py/src/") for f in files)
    assert scan_secrets.main() == 0
