"""Contract tests: the Tier A adapters against excerpts of the vendors' public docs saved in mock/contracts/.

The excerpts were read from public docs on 2026-11-23 (see each SOURCE.txt). They are field lists and examples, not the vendors'
machine readable spec files, and nothing here ran against a real service. Twenty publishes no static spec (per workspace only): see its SOURCE.txt.
The hangup action page could not be fetched, so that path is written by symmetry and stays UNVERIFIED.
"""

import base64
import json
import re
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from conftest import make_settings
from ringlark.adapters.calcom import CalcomCalendar
from ringlark.adapters.crm import TwentyCrm
from ringlark.adapters.telnyx import TelnyxCalls, TelnyxSms, parse_inbound_sms, verify_telnyx_webhook
from ringlark.adapters.ultravox import UltravoxVoice, tool_definitions
from sendora_core.adapters import AdapterError

C = Path(__file__).resolve().parents[3] / "mock" / "contracts"


def load(vendor: str, name: str) -> dict:
    return json.loads((C / vendor / name).read_text(encoding="utf-8"))


def client(handler) -> httpx.Client:
    return httpx.Client(base_url="https://api.example.test", transport=httpx.MockTransport(handler))


def test_every_contract_folder_says_where_it_came_from():
    folders = [d for d in C.iterdir() if d.is_dir()]
    assert {d.name for d in folders} == {"calcom", "telnyx", "twenty", "ultravox"}
    for d in folders:
        text = (d / "SOURCE.txt").read_text(encoding="utf-8")
        assert "2026-11-23" in text and "http" in text


# ---- Cal.com
def test_calcom_slots_request_and_response_match_the_docs(tmp_path):
    doc, seen = load("calcom", "slots.json"), {}

    def handler(req: httpx.Request):
        seen.update(path=req.url.path, params=dict(req.url.params), version=req.headers["cal-api-version"])
        return httpx.Response(200, json=doc["response_example"])

    s = make_settings(tmp_path, calcom_event_type_id="10", calcom_api_key="k")
    slots = CalcomCalendar(s, client(handler)).slots(datetime(2033, 9, 5, tzinfo=UTC), datetime(2033, 9, 6, tzinfo=UTC))
    assert seen["path"] == "/v2/slots" and set(seen["params"]) == set(doc["query"]) and seen["version"] == doc["header"]["cal-api-version"] == s.calcom_slots_version
    assert [d.astimezone(UTC).isoformat() for d in slots] == ["2033-09-05T07:00:00+00:00", "2033-09-05T08:00:00+00:00"]


def test_calcom_booking_request_and_response_match_the_docs(tmp_path):
    doc, seen = load("calcom", "booking.json"), {}

    def handler(req: httpx.Request):
        seen.update(path=req.url.path, body=json.loads(req.content), version=req.headers["cal-api-version"])
        return httpx.Response(201, json=doc["response_example"])

    s = make_settings(tmp_path, calcom_event_type_id="123", calcom_api_key="k")
    b = CalcomCalendar(s, client(handler)).book(start=datetime(2024, 8, 13, 9, 0, tzinfo=UTC), name="John Doe", email="john.doe@example.com", timezone="America/New_York")
    body = seen["body"]
    assert seen["path"] == "/v2/bookings" and seen["version"] == doc["header"]["cal-api-version"] == s.calcom_bookings_version
    assert all(k in body for k in doc["request_required"]) and all(k in body["attendee"] for k in doc["attendee_required"])
    assert body["attendee"] == doc["request_example"]["attendee"] and b.external_id == "booking_uid_123"
    assert b.starts_at.isoformat() == "2024-08-13T15:30:00+00:00" and b.ends_at.isoformat() == "2024-08-13T16:30:00+00:00"


# ---- Telnyx messaging
def test_telnyx_send_request_uses_only_documented_fields_and_reads_the_documented_response(tmp_path):
    doc, seen = load("telnyx", "send_message.json"), {}

    def handler(req: httpx.Request):
        seen.update(path=req.url.path, method=req.method, body=json.loads(req.content))
        return httpx.Response(200, json=doc["response_example"])

    s = make_settings(tmp_path, telnyx_api_key="k", telnyx_from_number="+15550100124")
    out = TelnyxSms(s, client(handler)).send(to="+15550100123", text="Hello")
    assert seen["path"] == doc["path"] and seen["method"] == doc["method"]
    assert set(seen["body"]) <= set(doc["request_fields"]) and all(r in seen["body"] for r in doc["request_required"]) and out == "40385f64-5717-4562-b3fc-2c963f66afa6"


def test_telnyx_error_shape_is_read_into_a_plain_message(tmp_path):
    doc = load("telnyx", "send_message.json")
    s = make_settings(tmp_path, telnyx_api_key="k", telnyx_from_number="+15550100124")
    with pytest.raises(AdapterError, match="The 'to' address is invalid"):
        TelnyxSms(s, client(lambda r: httpx.Response(400, json=doc["error_example"]))).send(to="bad", text="x")


def test_telnyx_inbound_webhook_and_signature_follow_the_documented_scheme():
    doc = load("telnyx", "inbound_webhook.json")
    sms = parse_inbound_sms(doc["example_shape"])
    assert (sms.from_number, sms.to_number, sms.text) == ("+15550100124", "+15550100123", "Yes please")
    key = Ed25519PrivateKey.generate()
    pub = base64.b64encode(key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)).decode()
    body = json.dumps(doc["example_shape"], separators=(",", ":")).encode()
    ts = str(int(time.time()))
    sig = base64.b64encode(key.sign(ts.encode() + b"|" + body)).decode()
    assert verify_telnyx_webhook(pub, body, sig, ts)
    assert not verify_telnyx_webhook(pub, json.dumps(doc["example_shape"], indent=2).encode(), sig, ts)
    old = str(int(time.time()) - doc["max_age_seconds"] - 5)
    assert not verify_telnyx_webhook(pub, body, base64.b64encode(key.sign(old.encode() + b"|" + body)).decode(), old)


# ---- Telnyx Call Control
def calls(tmp_path, handler):
    s = make_settings(tmp_path, telnyx_api_key="k", telnyx_connection_id="conn-1", telnyx_from_number="+15550100124", public_base_url="https://app.example.test")
    return TelnyxCalls(s, client(handler))


def test_telnyx_dial_request_matches_the_documented_fields_and_the_response_is_read(tmp_path):
    doc, seen = load("telnyx", "call_control.json")["dial"], {}

    def handler(req: httpx.Request):
        seen.update(path=req.url.path, body=json.loads(req.content))
        return httpx.Response(200, json=doc["response_example"])

    placed = calls(tmp_path, handler).place_call(to="+15550100123", from_number="+15550100124", client_state="e30=", amd=True)
    assert seen["path"] == "/v2/calls" or seen["path"] == doc["path"]
    assert all(r in seen["body"] for r in doc["required"]) and set(seen["body"]) <= set(doc["sent_by_ringlark"])
    assert seen["body"]["answering_machine_detection"] in doc["amd_values"] and seen["body"]["webhook_url"] == "https://app.example.test/api/webhooks/telnyx"
    assert (placed.call_control_id, placed.call_session_id) == ("v3:example-call-control-id", "2dc1b3c8-f9e0-11ea-bc5a-02420a0f7768")
    seen.clear()
    calls(tmp_path, handler).place_call(to="+15550100123", from_number="+15550100124", client_state="e30=", amd=False)
    assert seen["body"]["answering_machine_detection"] == "disabled" and "disabled" in doc["amd_values"]


def test_telnyx_call_actions_use_the_documented_paths_and_fields(tmp_path):
    doc, seen = load("telnyx", "call_control.json"), []

    def handler(req: httpx.Request):
        seen.append((req.url.path, json.loads(req.content) if req.content else {}))
        return httpx.Response(200, json={"data": {"result": "ok"}})

    c = calls(tmp_path, handler)
    c.start_stream("cc1", "wss://join.example.test/x")
    c.send_dtmf("cc1", "5")
    c.speak("cc1", "Hello, this is an AI assistant.")
    c.transfer("cc1", "+15550100199")
    by_name = {p.rsplit("/", 1)[-1]: (p, b) for p, b in seen}
    for name in ("streaming_start", "send_dtmf", "speak", "transfer"):
        assert by_name[name][0] == "/v2" + doc[name]["path"].format(call_control_id="cc1") or by_name[name][0].endswith(doc[name]["path"].format(call_control_id="cc1"))
    ss = by_name["streaming_start"][1]
    assert set(ss) <= set(doc["streaming_start"]["fields"]) and ss["stream_url"].startswith("wss://") and ss["stream_track"] in doc["streaming_start"]["stream_track"]
    assert ss["stream_bidirectional_mode"] in doc["streaming_start"]["stream_bidirectional_mode"]
    dt = by_name["send_dtmf"][1]
    assert all(r in dt for r in doc["send_dtmf"]["required"]) and re.fullmatch(r"[0-9A-D*#wW]+", dt["digits"])
    sp = by_name["speak"][1]
    assert all(r in sp for r in doc["speak"]["required"]) and re.fullmatch(r"\w+\.\w+\.\w+", sp["voice"])  # <Provider>.<Model>.<VoiceId>, found by this test: the old value was "female"
    assert len(sp["payload"]) <= doc["speak"]["payload_max_chars"] and all(r in by_name["transfer"][1] for r in doc["transfer"]["required"])


def test_the_machine_detection_event_is_read_from_the_documented_field(session, settings, ctx, seeded):
    from ringlark import live
    from ringlark.adapters.telnyx import encode_state

    ev = load("telnyx", "call_control.json")["machine_detection_event"]
    assert ev["event_type"] == "call.machine.detection.ended" and ev["result_field"] == "data.payload.result"
    from sqlalchemy import select

    from ringlark.models import Call

    c = Call(agent_id=1, peer_phone="+15550100123", status="placed", direction="outbound", telnyx_call_id="cc-md")
    session.add(c)
    session.flush()
    out = live.handle_telnyx_event(session, ctx, settings, ev["event_type"], {"result": "human", "call_control_id": "cc-md", "client_state": encode_state({"call": c.id, "join": ""})})
    assert out == "streaming" and session.scalar(select(Call.answered_by).where(Call.id == c.id)) == "human"


# ---- Ultravox
def test_ultravox_create_call_request_matches_the_documented_fields(tmp_path, monkeypatch):
    doc, seen = load("ultravox", "calls_post.json"), {}

    def handler(req: httpx.Request):
        seen.update(path=req.url.path, body=json.loads(req.content))
        return httpx.Response(doc["response_status"], json=doc["response_example"])

    s = make_settings(tmp_path, ultravox_api_key="k")
    v = UltravoxVoice(s, client(handler))
    call = v.create_call(system_prompt="You are Casey.", voice="Mark", first_message="Hi, I'm an AI.", tools=tool_definitions("https://app.example.test", 1, "tok"), max_seconds=600)
    body = seen["body"]
    assert seen["path"] == doc["path"] and set(body) <= set(doc["request_fields"])
    assert body["medium"] == doc["telnyx_medium_example"]["medium"] and re.fullmatch(doc["max_duration_pattern"], body["maxDuration"])
    assert list(body["firstSpeakerSettings"]) == ["agent"] and "text" in body["firstSpeakerSettings"]["agent"] and "externalVoice" not in body  # voice and externalVoice are never combined
    assert isinstance(body["recordingEnabled"], bool) and (call.call_id, call.join_url) == (doc["response_example"]["callId"], doc["response_example"]["joinUrl"])
    monkeypatch.setattr("ringlark.adapters.ultravox.safe_base_url", lambda u, **k: u)
    assert UltravoxVoice(s).client.headers[doc["auth_header"]] == "k"


def test_ultravox_never_sends_voice_and_external_voice_together(tmp_path):
    seen = {}

    def handler(req: httpx.Request):
        seen.update(body=json.loads(req.content))
        return httpx.Response(201, json={"callId": "c1", "joinUrl": "wss://x.test/j"})

    UltravoxVoice(make_settings(tmp_path, ultravox_api_key="k"), client(handler)).create_call(system_prompt="x" * 50, voice="Mark", first_message="Hi", tools=[], max_seconds=60, external_voice={"elevenLabs": {"voiceId": "v"}})
    assert "externalVoice" in seen["body"] and "voice" not in seen["body"]


# ---- Twenty
def test_twenty_uses_the_documented_auth_and_core_path_and_has_no_static_spec_to_test_against(tmp_path, monkeypatch):
    monkeypatch.setattr("ringlark.adapters.crm.safe_base_url", lambda u, **k: u)
    doc, seen = load("twenty", "auth.json"), {}

    def handler(req: httpx.Request):
        seen.update(path=req.url.path)
        return httpx.Response(200, json={"data": {"people": {"edges": []}}})

    s = make_settings(tmp_path, twenty_base_url="https://crm.example.test", twenty_api_key="k")
    assert TwentyCrm(s, client(handler)).find_by_phone("+15550100123") is None
    assert seen["path"].rstrip("/") == "/graphql" and doc["static_reference"] is False and "/graphql/" in doc["core_paths"]
    assert TwentyCrm(s).client.headers[doc["auth_header"]] == f"{doc['scheme']} k"
