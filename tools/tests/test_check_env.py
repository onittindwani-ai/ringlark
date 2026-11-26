"""check_env on the settings a real install uses: the example file must not report problems on a correctly filled copy."""

import re
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check_env  # noqa: E402

EXAMPLE = (Path(__file__).resolve().parents[2] / ".env.example").read_text(encoding="utf-8")


def with_values(**values: str) -> str:
    text = EXAMPLE
    for key, value in values.items():
        text = re.sub(rf"^{key}=.*$", f"{key}={value}", text, count=1, flags=re.M)
    return text


def real_install(**more: str) -> str:
    return with_values(DEMO_MODE="false", DATABASE_URL="postgresql+psycopg://ringlark:abc123@db:5432/ringlark", SESSION_SECRET=secrets.token_hex(24),
                       OWNER_PASSWORD_HASH="'pbkdf2$test-only'", COMPANY_NAME="Harbor Light Dental", POSTGRES_PASSWORD="abc123", **more)


def test_the_example_file_checks_clean_against_itself():
    assert check_env.check(EXAMPLE, EXAMPLE) == []


def test_a_correctly_filled_real_install_reports_no_problem_even_with_optional_settings_left_empty():
    assert check_env.check(EXAMPLE, real_install()) == []


def test_a_real_install_with_a_telephony_group_filled_in_completely_is_clean():
    env = real_install(TELNYX_API_KEY="KEYtest-only", TELNYX_PUBLIC_KEY="pubtest-only", TELNYX_CONNECTION_ID="123", TELNYX_FROM_NUMBER="+14155550190", PUBLIC_BASE_URL="https://calls.example.test")
    assert check_env.check(EXAMPLE, env) == []


def test_a_service_group_filled_in_halfway_is_reported_by_name():
    problems = check_env.check(EXAMPLE, real_install(TELNYX_API_KEY="KEYtest-only"))
    assert any("Phone calls and texts" in p and "TELNYX_PUBLIC_KEY" in p for p in problems)


def test_a_mail_group_filled_in_completely_is_clean_but_a_missing_host_is_reported():
    full = real_install(SMTP_HOST="smtp.example.test", SMTP_USER="calls@example.test", SMTP_PASSWORD="test-only-pw", IMAP_HOST="imap.example.test")
    assert check_env.check(EXAMPLE, full) == []
    assert any("SMTP_HOST" in p for p in check_env.check(EXAMPLE, real_install(SMTP_USER="calls@example.test")))


def test_a_placeholder_secret_is_a_problem_when_demo_mode_is_off():
    env = real_install().replace("SESSION_SECRET=", "SESSION_SECRET=change-me-", 1)
    assert any("SESSION_SECRET" in p for p in check_env.check(EXAMPLE, env))
