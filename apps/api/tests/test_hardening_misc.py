"""Smaller checks: inbound failure, recipients, the backup script."""

import os
import stat
import subprocess
from pathlib import Path

from sqlalchemy import select

from testkit import NOW
from ringlark import followups, live
from ringlark.models import Call, Campaign, FollowUp, Number, Target
from spies import SpyEmail, SpySms, SpyTelephony, SpyVoice

ROOT = Path(__file__).resolve().parents[3]


def test_an_inbound_call_whose_voice_engine_fails_ends_failed_and_is_hung_up(session, ctx, seeded):
    ctx.adapters.telephony, ctx.adapters.voice = SpyTelephony(), SpyVoice(fail=True)
    num = session.scalars(select(Number).where(Number.agent_id.is_not(None))).first()
    out = live.handle_inbound(session, ctx, ctx.effective(session), {"to": num.e164, "from": "+14155550123", "call_control_id": "v3:boom"})
    assert out == "failed"
    row = session.scalars(select(Call).where(Call.telnyx_call_id == "v3:boom")).one()
    assert row.status == "failed" and row.blocked_reason == "answer_failed"
    assert ("hangup", "v3:boom") in ctx.adapters.telephony.log


def test_a_follow_up_to_something_that_is_not_one_address_or_number_is_blocked(session, ctx, seeded):
    camp = session.get(Campaign, seeded["info"]["campaign_id"])
    t = session.scalars(select(Target).where(Target.status == "new", Target.timezone == "America/New_York")).first()
    c = Call(campaign_id=camp.id, target_id=t.id, agent_id=camp.agent_id, peer_phone=t.phone, status="completed")
    session.add(c); session.flush()
    ctx.settings.follow_ups_need_approval = False
    mail, sms = SpyEmail(), SpySms()
    bad_mail = FollowUp(call_id=c.id, channel="email", to="a@x.test, b@y.test", subject="s", body="b", status="pending")
    bad_sms = FollowUp(call_id=c.id, channel="sms", to="555-0100", body="b. Reply STOP to opt out.", status="pending")
    session.add_all([bad_mail, bad_sms]); session.flush()
    out = followups.send_due(session, ctx.settings, type("A", (), {"sms": sms, "email": mail})(), NOW)
    assert out["blocked"] == 2 and mail.sent == [] and sms.sent == []
    assert bad_mail.blocked_reason == bad_sms.blocked_reason == "bad_recipient"


def fake_docker(tmp_path: Path, body: str) -> dict:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    exe = bin_dir / "docker"
    exe.write_text(f"#!/bin/sh\n{body}\n")
    exe.chmod(0o755)
    return {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "BACKUP_DIR": str(tmp_path / "out")}


def test_the_backup_script_runs_from_any_folder_and_writes_a_private_file(tmp_path):
    env = fake_docker(tmp_path, "echo dump-bytes")
    r = subprocess.run(["sh", str(ROOT / "deploy" / "hetzner" / "backup.sh")], cwd=tmp_path, env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    (dump,) = list((tmp_path / "out").glob("ringlark-*.dump"))
    assert dump.read_text() == "dump-bytes\n" and stat.S_IMODE(dump.stat().st_mode) == 0o600


def test_a_failed_dump_leaves_no_empty_file_and_keeps_the_old_ones(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    for i in range(14):
        (out / f"ringlark-2026010{i % 10}-000{i}.dump").write_text("old")
    env = fake_docker(tmp_path, "exit 1")
    r = subprocess.run(["sh", str(ROOT / "deploy" / "hetzner" / "backup.sh")], cwd=tmp_path, env=env, capture_output=True, text=True)
    assert r.returncode != 0
    assert len(list(out.glob("ringlark-*"))) == 14 and not list(out.glob("*.part"))
