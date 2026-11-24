"""Telnyx texting and Call Control. Written from the public docs, tested against a mock only (UNVERIFIED live).

Docs read 2026-11-23: dial `POST /v2/calls` (connection_id, to, from, answering_machine_detection, webhook_url, client_state),
transfer `POST /v2/calls/{id}/actions/transfer` (to), webhook headers `telnyx-timestamp` and `telnyx-signature-ed25519`.
Not shown in the docs read: how timestamp and body are combined for signing (we use `timestamp|body`, as the Telnyx SDKs do, UNVERIFIED),
the paths for answer and hangup (written by symmetry, UNVERIFIED). Paths and fields of streaming_start, speak, send_dtmf and transfer were checked against the vendor pages on 2026-11-23 (mock/contracts/telnyx).
US calling and texting need the client's own registrations first (caller ID, STIR/SHAKEN attestation, A2P 10DLC). This code cannot do that.
"""

from __future__ import annotations

import base64
import json
import time

import httpx
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from ringlark.adapters.base import InboundSms, PlacedCall, safe_base_url
from sendora_core.adapters import AdapterError
from sendora_core.safety import write_action

TOLERANCE_S = 300


def verify_telnyx_webhook(public_key_b64: str, body: bytes, signature_b64: str, timestamp: str, now: float | None = None) -> bool:
    try:
        if abs((now or time.time()) - int(timestamp)) > TOLERANCE_S:
            return False
        key = Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key_b64))
        key.verify(base64.b64decode(signature_b64), timestamp.encode() + b"|" + body)
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False


def encode_state(data: dict) -> str:
    return base64.b64encode(json.dumps(data, separators=(",", ":")).encode()).decode()


def decode_state(value: str | None) -> dict:
    try:
        return json.loads(base64.b64decode(value or ""))
    except (ValueError, TypeError):
        return {}


def parse_inbound_sms(body: dict) -> InboundSms:
    d = body["data"]
    if d.get("event_type") != "message.received":
        raise AdapterError("Not an inbound message event.")
    p = d["payload"]
    return InboundSms(str(p.get("id") or d.get("id")), p["from"]["phone_number"], (p.get("to") or [{}])[0].get("phone_number", ""), p.get("text", ""))


def _client(settings, client):
    if client is not None:
        return client
    if not settings.telnyx_api_key:
        raise AdapterError("TELNYX_API_KEY is empty.")
    return httpx.Client(base_url=safe_base_url(settings.telnyx_base_url), timeout=15, headers={"Authorization": f"Bearer {settings.telnyx_api_key}"})


def _fail(r: httpx.Response, what: str) -> None:
    if r.status_code == 401:
        raise AdapterError("Telnyx rejected the API key.")
    if r.status_code >= 400:
        try:
            err = (r.json().get("errors") or [{}])[0]
        except ValueError:
            err = {}
        raise AdapterError(f"Telnyx refused to {what}: {err.get('detail') or err.get('title') or r.status_code}")


class TelnyxSms:
    def __init__(self, settings, client: httpx.Client | None = None):
        self.settings, self.client = settings, _client(settings, client)

    @write_action("sms.send")
    def send(self, *, to: str, text: str) -> str:
        r = self.client.post("/v2/messages", json={"from": self.settings.telnyx_from_number, "to": to, "text": text})
        _fail(r, "send the text")
        return str(r.json()["data"]["id"])

    def healthcheck(self) -> tuple[bool, str]:
        if not self.settings.telnyx_from_number:
            return False, "TELNYX_FROM_NUMBER is empty."
        try:
            r = self.client.get("/v2/messages/healthcheck-probe")
        except httpx.HTTPError as exc:
            return False, f"Could not reach Telnyx: {type(exc).__name__}."
        return (False, "Telnyx rejected the API key.") if r.status_code == 401 else (True, "Telnyx answered and accepted the key (a 404 for the probe id is expected).")


class TelnyxCalls:
    def __init__(self, settings, client: httpx.Client | None = None):
        self.settings, self.client = settings, _client(settings, client)

    def _action(self, cid: str, name: str, body: dict) -> None:
        _fail(self.client.post(f"/v2/calls/{cid}/actions/{name}", json=body), name)

    @write_action("call.place")
    def place_call(self, *, to: str, from_number: str, client_state: str, amd: bool) -> PlacedCall:
        body = {"connection_id": self.settings.telnyx_connection_id, "to": to, "from": from_number, "client_state": client_state,
                "webhook_url": f"{self.settings.public_base_url.rstrip('/')}/api/webhooks/telnyx", "answering_machine_detection": "detect_words" if amd else "disabled"}
        r = self.client.post("/v2/calls", json=body)
        _fail(r, "place the call")
        d = r.json()["data"]
        return PlacedCall(d["call_control_id"], d.get("call_session_id", ""))

    def answer(self, call_control_id: str) -> None:
        self._action(call_control_id, "answer", {})

    def start_stream(self, call_control_id: str, join_url: str) -> None:
        self._action(call_control_id, "streaming_start", {"stream_url": join_url, "stream_track": "both_tracks", "stream_bidirectional_mode": "rtp"})

    def transfer(self, call_control_id: str, to: str) -> None:
        self._action(call_control_id, "transfer", {"to": to})

    def send_dtmf(self, call_control_id: str, digits: str) -> None:
        self._action(call_control_id, "send_dtmf", {"digits": digits})

    @write_action("call.speak")
    def speak(self, call_control_id: str, text: str) -> None:
        self._action(call_control_id, "speak", {"payload": text, "voice": "Telnyx.KokoroTTS.af", "language": "en-US"})

    def hangup(self, call_control_id: str) -> None:
        self._action(call_control_id, "hangup", {})

    def healthcheck(self) -> tuple[bool, str]:
        if not self.settings.telnyx_connection_id or not self.settings.telnyx_from_number:
            return False, "TELNYX_CONNECTION_ID and TELNYX_FROM_NUMBER must be set."
        try:
            r = self.client.get("/v2/calls/healthcheck-probe")
        except httpx.HTTPError as exc:
            return False, f"Could not reach Telnyx: {type(exc).__name__}."
        return (False, "Telnyx rejected the API key.") if r.status_code == 401 else (True, "Telnyx answered and accepted the key.")
