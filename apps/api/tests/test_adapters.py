"""Each real adapter against the fake vendor server written from the public docs. This proves our requests and our reading of the replies agree, NOT that the real vendor behaves the same."""

import base64
import json
import time
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from mock.calcom_mock import CalcomMock
from mock.telnyx_mock import TelnyxMock
from mock.twenty_mock import TwentyMock
from mock.ultravox_mock import UltravoxMock
from ringlark.adapters.base import PersonRecord, safe_base_url
from ringlark.adapters.calcom import CalcomCalendar
from ringlark.adapters.crm import TwentyCrm
from ringlark.adapters.telnyx import TelnyxCalls, TelnyxSms, decode_state, encode_state, parse_inbound_sms, verify_telnyx_webhook
from ringlark.adapters.ultravox import UltravoxVoice, sign_ultravox, tool_definitions, verify_ultravox_webhook
from testkit import make_settings
from sendora_core.adapters import AdapterError
from sendora_core.safety import DraftModeError


@pytest.fixture
def live(tmp_path):
    return make_settings(tmp_path, telnyx_connection_id="conn-1", telnyx_from_number="+14155550190", public_base_url="https://app.example.test")


def test_telnyx_calls_dial_transfer_dtmf_hangup(live):
    m = TelnyxMock()
    calls = TelnyxCalls(live, TestClient(m.app, headers={"Authorization": "Bearer mock-telnyx-key"}))
    placed = calls.place_call(to="+14155550123", from_number="+14155550190", client_state=encode_state({"call": 7}), amd=True)
    req = m.calls[placed.call_control_id]["request"]
    assert req["connection_id"] == "conn-1" and req["answering_machine_detection"] == "detect_words" and req["webhook_url"].endswith("/api/webhooks/telnyx")
    assert decode_state(req["client_state"]) == {"call": 7}
    calls.transfer(placed.call_control_id, "+14155550199"); calls.send_dtmf(placed.call_control_id, "1"); calls.hangup(placed.call_control_id)
    assert [a[1] for a in m.actions] == ["transfer", "send_dtmf", "hangup"]
    with pytest.raises(AdapterError):
        calls.hangup("gone")
    assert calls.healthcheck()[0]


def test_telnyx_wrong_key_and_bad_number(live):
    bad = TelnyxCalls(live, TestClient(TelnyxMock().app, headers={"Authorization": "Bearer nope"}))
    with pytest.raises(AdapterError, match="rejected the API key"):
        bad.place_call(to="+14155550123", from_number="+1", client_state="", amd=False)
    ok = TelnyxCalls(live, TestClient(TelnyxMock().app, headers={"Authorization": "Bearer mock-telnyx-key"}))
    with pytest.raises(AdapterError, match="Invalid 'to'|E.164"):
        ok.place_call(to="555", from_number="+1", client_state="", amd=False)


def test_draft_mode_blocks_every_telnyx_write(tmp_path):
    s = make_settings(tmp_path, mode="draft")
    c = TestClient(TelnyxMock().app, headers={"Authorization": "Bearer mock-telnyx-key"})
    with pytest.raises(DraftModeError):
        TelnyxCalls(s, c).place_call(to="+14155550123", from_number="+1", client_state="", amd=False)
    with pytest.raises(DraftModeError):
        TelnyxSms(s, c).send(to="+14155550123", text="x")


def test_telnyx_sms_and_signed_webhooks(live):
    m = TelnyxMock()
    assert TelnyxSms(live, TestClient(m.app, headers={"Authorization": "Bearer mock-telnyx-key"})).send(to="+14155550123", text="hello")
    body, h = m.signed_inbound("+14155550123", "+14155550190", "STOP")
    assert verify_telnyx_webhook(m.public_key_b64, body, h["telnyx-signature-ed25519"], h["telnyx-timestamp"])
    assert not verify_telnyx_webhook(m.public_key_b64, body + b" ", h["telnyx-signature-ed25519"], h["telnyx-timestamp"])
    assert not verify_telnyx_webhook(m.public_key_b64, body, h["telnyx-signature-ed25519"], str(int(h["telnyx-timestamp"]) - 4000)), "an old timestamp is refused"
    assert not verify_telnyx_webhook("", body, "x", "1") and parse_inbound_sms(json.loads(body)).text == "STOP"
    old_body, old_h = m.signed_inbound("+1", "+1", "x", timestamp=int(time.time()) - 4000)
    assert not verify_telnyx_webhook(m.public_key_b64, old_body, old_h["telnyx-signature-ed25519"], old_h["telnyx-timestamp"])


def test_ultravox_create_call_with_tools_and_transcript(live):
    u = UltravoxMock()
    v = UltravoxVoice(live, TestClient(u.app, headers={"X-API-Key": "mock-ultravox-key"}))
    tools = tool_definitions("https://app.example.test", 12, "tok")
    vc = v.create_call(system_prompt="You are Casey. " * 5, voice="Mark", first_message="Hi, an AI assistant here.", tools=tools, max_seconds=600)
    sent = u.calls[vc.call_id]["request"]
    assert sent["voice"] == "Mark" and sent["maxDuration"] == "600s" and sent["medium"] == {"telnyx": {}}
    names = [t["temporaryTool"]["modelToolName"] for t in sent["selectedTools"]]
    assert names == ["book_meeting", "list_times", "lookup_crm", "transfer_to_human", "send_sms", "press_digit", "end_call"]  # list_times: the open times the agent may offer
    assert sent["selectedTools"][0]["temporaryTool"]["http"]["baseUrlPattern"] == "https://app.example.test/api/tools/12/book_meeting"
    assert sent["selectedTools"][0]["temporaryTool"]["staticParameters"][0]["value"] == "tok"
    vc2 = v.create_call(system_prompt="x" * 50, voice="", first_message="Hi", tools=[], max_seconds=60, external_voice={"elevenLabs": {"voiceId": "abc"}})
    assert "voice" not in u.calls[vc2.call_id]["request"] and u.calls[vc2.call_id]["request"]["externalVoice"]
    u.messages[vc.call_id] = [{"role": "MESSAGE_ROLE_AGENT", "text": "Hi", "startMs": 0, "endMs": 900}, {"role": "MESSAGE_ROLE_USER", "text": "Hello", "startMs": 1000, "endMs": 1500}]
    assert [t["speaker"] for t in v.transcript(vc.call_id)] == ["agent", "caller"]
    with pytest.raises(AdapterError):
        UltravoxVoice(live, TestClient(u.app, headers={"X-API-Key": "bad"})).create_call(system_prompt="x" * 50, voice="a", first_message="", tools=[], max_seconds=1)


def test_ultravox_webhook_signature():
    u = UltravoxMock()
    body, h = u.signed_webhook("call.ended", {"callId": "1"})
    ts, sig = h["X-Ultravox-Webhook-Timestamp"], h["X-Ultravox-Webhook-Signature"]
    assert verify_ultravox_webhook("mock-uv-webhook-secret", body, sig, ts)
    assert verify_ultravox_webhook("mock-uv-webhook-secret", body, "deadbeef," + sig, ts), "any of several signatures may match (rotation)"
    assert not verify_ultravox_webhook("other", body, sig, ts) and not verify_ultravox_webhook("", body, sig, ts)
    assert not verify_ultravox_webhook("mock-uv-webhook-secret", body + b"x", sig, ts)
    assert not verify_ultravox_webhook("mock-uv-webhook-secret", body, sig, str(int(ts) - 120)), "older than a minute"
    assert sign_ultravox("s", b"b", "1") == sign_ultravox("s", b"b", "1")


def test_twenty_find_upsert_and_note(live):
    t = TwentyMock()
    live.twenty_base_url = "https://crm.example.test"
    crm = TwentyCrm(live, TestClient(t.app, headers={"Authorization": "Bearer mock-twenty-key"}))
    assert crm.find_by_phone("+14155550123") is None
    pid = crm.upsert_person(PersonRecord(first_name="Ava", last_name="Alder", phone="+14155550123", extra={"note": "Booked."}))
    assert pid and crm.find_by_phone("+14155550123").first_name == "Ava" and len(t.notes) == 1
    assert crm.upsert_person(PersonRecord(first_name="Ava", phone="+14155550123")) == pid, "the same phone is not duplicated"
    assert crm.healthcheck()[0]
    assert not TwentyCrm(live, TestClient(t.app, headers={"Authorization": "Bearer bad"})).healthcheck()[0]


def test_calcom_slots_and_booking(live):
    m = CalcomMock()
    live.calcom_event_type_id = 1001
    cal = CalcomCalendar(live, TestClient(m.app, headers={"Authorization": "Bearer mock-cal-key"}))
    start = datetime(2026, 12, 1, tzinfo=UTC)
    slots = cal.slots(start, start + timedelta(days=4))
    assert slots
    b = cal.book(start=slots[0], name="Ava Alder", email="ava@example.test", timezone="America/New_York")
    assert b.external_id


def test_the_url_guard_refuses_local_addresses():
    for u in ("http://127.0.0.1:9", "https://localhost/x", "ftp://example.test", "https://user:pw@example.test"):
        with pytest.raises(AdapterError):
            safe_base_url(u)
