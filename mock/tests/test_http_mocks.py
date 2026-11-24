from fastapi.testclient import TestClient

from mock.calcom_mock import CalcomMock
from mock.telnyx_mock import TelnyxMock
from mock.twenty_mock import TwentyMock
from mock.ultravox_mock import UltravoxMock

AUTH = {"authorization": "Bearer mock-telnyx-key"}


def test_telnyx_send_requires_key_and_e164():
    t = TelnyxMock()
    c = TestClient(t.app)
    assert c.post("/v2/messages", json={"to": "+14155550100", "text": "hi"}).status_code == 401
    assert c.post("/v2/messages", headers=AUTH, json={"to": "555-0100", "text": "hi"}).status_code == 422
    r = c.post("/v2/messages", headers=AUTH, json={"from": "+14155550181", "to": "+14155550100", "text": "hi"})
    assert r.status_code == 200 and r.json()["data"]["to"][0]["status"] == "queued"
    assert c.get(f"/v2/messages/{r.json()['data']['id']}", headers=AUTH).status_code == 200


def test_telnyx_signed_inbound_has_headers():
    t = TelnyxMock()
    body, headers = t.signed_inbound("+14155550100", "+14155550181", "STOP")
    assert b"message.received" in body and "telnyx-signature-ed25519" in headers


def test_calcom_slots_and_booking_conflict():
    cal = CalcomMock()
    c = TestClient(cal.app)
    h = {"authorization": "Bearer mock-cal-key", "cal-api-version": "2024-09-04"}
    assert c.get("/v2/slots", params={"eventTypeId": 1001, "start": "2026-12-01", "end": "2026-12-05"}).status_code == 401
    r = c.get("/v2/slots", headers=h, params={"eventTypeId": 1001, "start": "2026-12-01", "end": "2026-12-05"})
    first = next(iter(r.json()["data"].values()))[0]["start"]
    body = {"start": first, "eventTypeId": 1001, "attendee": {"name": "Ava Alder", "email": "ava@x.example.test", "timeZone": "America/New_York"}}
    assert c.post("/v2/bookings", headers=h, json=body).status_code == 201
    assert c.post("/v2/bookings", headers=h, json=body).status_code == 409
    assert c.post("/v2/bookings", headers={"authorization": "Bearer mock-cal-key"}, json=body).status_code == 400


def test_twenty_create_find_by_phone_and_note():
    tw = TwentyMock()
    c = TestClient(tw.app)
    h = {"authorization": "Bearer mock-twenty-key"}
    data = {"name": {"firstName": "Ava", "lastName": "Alder"}, "phones": {"primaryPhoneNumber": "+14155550111"}}
    assert c.post("/graphql", json={"operationName": "CreatePerson", "variables": {"data": data}}).status_code == 401
    ok = c.post("/graphql", headers=h, json={"operationName": "CreatePerson", "variables": {"data": data}}).json()
    assert ok["data"]["createPerson"]["id"]
    dup = c.post("/graphql", headers=h, json={"operationName": "CreatePerson", "variables": {"data": data}}).json()
    assert "Duplicate" in dup["errors"][0]["message"]
    found = c.post("/graphql", headers=h, json={"operationName": "FindByPhone", "variables": {"phone": "+14155550111"}}).json()
    assert len(found["data"]["people"]["edges"]) == 1
    note = c.post("/graphql", headers=h, json={"operationName": "CreateNote", "variables": {"data": {"title": "t"}}}).json()
    assert note["data"]["createNote"]["id"] and len(tw.notes) == 1


def test_telnyx_dial_and_actions():
    t = TelnyxMock()
    c = TestClient(t.app)
    body = {"connection_id": "c1", "to": "+14155550100", "from": "+14155550181"}
    assert c.post("/v2/calls", json=body).status_code == 401
    assert c.post("/v2/calls", headers=AUTH, json={"to": "+14155550100"}).status_code == 422
    assert c.post("/v2/calls", headers=AUTH, json={**body, "to": "555"}).status_code == 422
    cid = c.post("/v2/calls", headers=AUTH, json=body).json()["data"]["call_control_id"]
    assert c.post(f"/v2/calls/{cid}/actions/transfer", headers=AUTH, json={}).status_code == 422
    assert c.post(f"/v2/calls/{cid}/actions/transfer", headers=AUTH, json={"to": "+14155550199"}).status_code == 200
    assert c.post("/v2/calls/nope/actions/hangup", headers=AUTH, json={}).status_code == 404
    assert t.actions[0][1] == "transfer"
    body2, headers = t.signed_event("call.hangup", {"call_control_id": cid})
    assert b"call.hangup" in body2 and "telnyx-timestamp" in headers


def test_ultravox_create_and_messages():
    u = UltravoxMock()
    c = TestClient(u.app)
    assert c.post("/api/calls", json={"systemPrompt": "x"}).status_code == 403
    h = {"X-API-Key": "mock-ultravox-key"}
    assert c.post("/api/calls", headers=h, json={}).status_code == 400
    assert c.post("/api/calls", headers=h, json={"systemPrompt": "x", "voice": "a", "externalVoice": {"elevenLabs": {"voiceId": "v"}}}).status_code == 400
    r = c.post("/api/calls", headers=h, json={"systemPrompt": "x", "voice": "a"})
    assert r.status_code == 201 and r.json()["joinUrl"].startswith("wss://")
    assert c.get(f"/api/calls/{r.json()['callId']}/messages", headers=h).json() == {"results": []}
