"""Ultravox voice engine. Written from the public API reference read 2026-11-23, tested against a mock only (UNVERIFIED live).

Read from the docs: `POST /api/calls` with header `X-API-Key`; body fields systemPrompt, voice, model, firstSpeakerSettings,
selectedTools (each a toolId, toolName or temporaryTool with modelToolName, description, dynamicParameters, http.baseUrlPattern and httpMethod),
medium (telnyx, serverWebSocket and others), recordingEnabled, maxDuration ("3600s"), languageHint, externalVoice; reply has callId and joinUrl.
Webhooks: headers `X-Ultravox-Webhook-Timestamp` and `X-Ultravox-Webhook-Signature` (comma separated), HMAC SHA256 hex of the raw body with the timestamp appended, about one minute tolerance.
Not shown in the pages read (UNVERIFIED): `staticParameters` and `automaticParameters` shapes, `GET /api/calls/{id}/messages`, the telnyx medium details.
"""

from __future__ import annotations

import hashlib
import hmac
import time

import httpx

from ringlark.adapters.base import VoiceCall, safe_base_url
from sendora_core.adapters import AdapterError

TOLERANCE_S = 60


def sign_ultravox(secret: str, body: bytes, timestamp: str) -> str:
    return hmac.new(secret.encode(), body + timestamp.encode(), hashlib.sha256).hexdigest()


def verify_ultravox_webhook(secret: str, body: bytes, signature_header: str, timestamp: str, now: float | None = None) -> bool:
    """True when any listed signature matches and the timestamp is fresh. An empty secret never verifies."""
    if not secret or not signature_header or not timestamp:
        return False
    try:
        if abs((now or time.time()) - float(timestamp)) > TOLERANCE_S:
            return False
    except ValueError:
        return False
    want = sign_ultravox(secret, body, timestamp)
    return any(hmac.compare_digest(want, s.strip().lower()) for s in signature_header.split(","))


def tool_definitions(public_base_url: str, call_id: int, token: str) -> list[dict]:
    """The tools the agent may call during a call. Every one points at this app and carries a per call token (shape UNVERIFIED)."""
    base = f"{public_base_url.rstrip('/')}/api/tools/{call_id}"
    hdr = [{"name": "X-Tool-Token", "location": "PARAMETER_LOCATION_HEADER", "value": token}]

    def tool(name: str, desc: str, params: list[tuple[str, str, bool]]) -> dict:
        return {"temporaryTool": {"modelToolName": name, "description": desc, "http": {"baseUrlPattern": f"{base}/{name}", "httpMethod": "POST"}, "staticParameters": hdr,
                "dynamicParameters": [{"name": n, "location": "PARAMETER_LOCATION_BODY", "schema": {"type": "string", "description": d}, "required": req} for n, d, req in params]}}

    return [
        tool("book_meeting", "Book a meeting once the person has agreed to a time.", [("slot", "ISO time chosen from the offered times", True), ("name", "Person's name", True), ("email", "Person's email if given", False)]),
        tool("lookup_crm", "Look up what we already know about the person on the line.", []),
        tool("transfer_to_human", "Hand the call to a human when asked, or when you cannot help.", [("reason", "Why", False)]),
        tool("send_sms", "Text the person a standard message, only if they agreed to a text.", [("kind", "booking_link, confirmation or callback", True)]),
        tool("press_digit", "Press one key on a phone menu. Only the configured key works, and only once.", [("digit", "The key", True)]),
        tool("end_call", "End the call and record how it went.", [("disposition", "One of the allowed outcome codes", True), ("note", "One short sentence", False)]),
    ]


class UltravoxVoice:
    def __init__(self, settings, client: httpx.Client | None = None):
        self.settings = settings
        if client is not None:
            self.client = client
        else:
            if not settings.ultravox_api_key:
                raise AdapterError("ULTRAVOX_API_KEY is empty.")
            self.client = httpx.Client(base_url=safe_base_url(settings.ultravox_base_url), timeout=20, headers={"X-API-Key": settings.ultravox_api_key})

    def create_call(self, *, system_prompt: str, voice: str, first_message: str, tools: list[dict], max_seconds: int, external_voice: dict | None = None) -> VoiceCall:
        body: dict = {"systemPrompt": system_prompt, "firstSpeakerSettings": {"agent": {"text": first_message, "uninterruptible": True}}, "selectedTools": tools,
                      "medium": {"telnyx": {}}, "recordingEnabled": False, "maxDuration": f"{max_seconds}s"}
        if external_voice:
            body["externalVoice"] = external_voice
        else:
            body["voice"] = voice
        r = self.client.post("/api/calls", json=body)
        if r.status_code in (401, 403):
            raise AdapterError("Ultravox rejected the API key.")
        if r.status_code >= 400:
            raise AdapterError(f"Ultravox refused to create the call: {r.status_code}")
        d = r.json()
        return VoiceCall(d["callId"], d.get("joinUrl") or "")

    def transcript(self, call_id: str) -> list[dict]:
        r = self.client.get(f"/api/calls/{call_id}/messages")
        if r.status_code >= 400:
            raise AdapterError(f"Ultravox could not return the transcript: {r.status_code}")
        return [{"speaker": "agent" if m.get("role") == "MESSAGE_ROLE_AGENT" else "caller", "text": m.get("text", ""), "start_ms": int(m.get("startMs", 0)), "end_ms": int(m.get("endMs", 0))}
                for m in r.json().get("results", []) if m.get("text")]

    def healthcheck(self) -> tuple[bool, str]:
        try:
            r = self.client.get("/api/voices", params={"pageSize": 1})
        except httpx.HTTPError as exc:
            return False, f"Could not reach Ultravox: {type(exc).__name__}."
        return (False, "Ultravox rejected the API key.") if r.status_code in (401, 403) else (True, "Ultravox answered and accepted the key.")
