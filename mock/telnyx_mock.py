"""Fake Telnyx messaging API, written from the public docs (UNVERIFIED against the real service).

POST /v2/messages with Bearer auth and {from, to, text}. Inbound texts are simulated with `signed_inbound`,
which builds a webhook body and Ed25519 headers exactly as the docs describe: signature over `timestamp|body`.
"""

from __future__ import annotations

import base64
import json
import re
import time
import uuid

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

E164 = re.compile(r"^\+[1-9]\d{6,14}$")


class TelnyxMock:
    def __init__(self, api_key: str = "mock-telnyx-key"):
        self.api_key = api_key
        self.messages: dict[str, dict] = {}
        self.calls: dict[str, dict] = {}
        self.actions: list[tuple[str, str, dict]] = []
        self._key = Ed25519PrivateKey.generate()
        self.public_key_b64 = base64.b64encode(self._key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)).decode()
        self.app = self._build()

    def signed_inbound(self, from_number: str, to_number: str, text: str, timestamp: int | None = None) -> tuple[bytes, dict[str, str]]:
        ts = str(timestamp or int(time.time()))
        body = json.dumps({
            "data": {"event_type": "message.received", "id": str(uuid.uuid4()), "record_type": "event",
                     "payload": {"direction": "inbound", "type": "SMS", "text": text, "from": {"phone_number": from_number}, "to": [{"phone_number": to_number}]}},
            "meta": {"attempt": 1},
        }).encode()
        sig = base64.b64encode(self._key.sign(ts.encode() + b"|" + body)).decode()
        return body, {"telnyx-signature-ed25519": sig, "telnyx-timestamp": ts, "content-type": "application/json"}

    def signed_event(self, event_type: str, payload: dict, timestamp: int | None = None) -> tuple[bytes, dict[str, str]]:
        """A call event (call.answered, call.hangup, call.machine.detection.ended, call.initiated) signed like the real ones."""
        ts = str(timestamp or int(time.time()))
        body = json.dumps({"data": {"event_type": event_type, "id": str(uuid.uuid4()), "record_type": "event", "payload": payload}, "meta": {"attempt": 1}}).encode()
        sig = base64.b64encode(self._key.sign(ts.encode() + b"|" + body)).decode()
        return body, {"telnyx-signature-ed25519": sig, "telnyx-timestamp": ts, "content-type": "application/json"}

    def _build(self) -> FastAPI:
        app = FastAPI(title="Telnyx mock")

        @app.post("/v2/messages")
        async def send(request: Request, authorization: str | None = Header(default=None)):
            if authorization != f"Bearer {self.api_key}":
                return JSONResponse({"errors": [{"code": "10009", "title": "Authentication failed"}]}, 401)
            body = await request.json()
            if not E164.match(str(body.get("to", ""))):
                return JSONResponse({"errors": [{"code": "40310", "title": "Invalid 'to' address", "detail": "Use E.164, for example +14155550100"}]}, 422)
            if not body.get("text"):
                return JSONResponse({"errors": [{"code": "40002", "title": "text is required"}]}, 422)
            mid = str(uuid.uuid4())
            msg = {"id": mid, "direction": "outbound", "type": "SMS", "from": {"phone_number": body.get("from")}, "text": body["text"],
                   "to": [{"phone_number": body["to"], "status": "queued"}]}
            self.messages[mid] = msg
            return {"data": msg}

        @app.post("/v2/calls")
        async def dial(request: Request, authorization: str | None = Header(default=None)):
            if authorization != f"Bearer {self.api_key}":
                return JSONResponse({"errors": [{"code": "10009", "title": "Authentication failed"}]}, 401)
            body = await request.json()
            for f in ("connection_id", "to", "from"):
                if not body.get(f):
                    return JSONResponse({"errors": [{"code": "90015", "title": f"{f} is required"}]}, 422)
            if not E164.match(str(body["to"])):
                return JSONResponse({"errors": [{"code": "40310", "title": "Invalid 'to' address", "detail": "Use E.164, for example +14155550100"}]}, 422)
            cid = "v3:" + uuid.uuid4().hex
            self.calls[cid] = {"call_control_id": cid, "call_session_id": str(uuid.uuid4()), "call_leg_id": str(uuid.uuid4()), "is_alive": False, "record_type": "call", "request": body}
            return {"data": {k: v for k, v in self.calls[cid].items() if k != "request"}}

        @app.post("/v2/calls/{cid}/actions/{action}")
        async def act(cid: str, action: str, request: Request, authorization: str | None = Header(default=None)):
            if authorization != f"Bearer {self.api_key}":
                return JSONResponse({"errors": [{"code": "10009", "title": "Authentication failed"}]}, 401)
            body = await request.json()
            if cid not in self.calls:
                return JSONResponse({"errors": [{"code": "90018", "title": "Call has already ended or does not exist"}]}, 404)
            if action == "transfer" and not body.get("to"):
                return JSONResponse({"errors": [{"code": "90015", "title": "to is required"}]}, 422)
            self.actions.append((cid, action, body))
            return {"data": {"result": "ok"}}

        @app.get("/v2/calls/{cid}")
        def get_call(cid: str, authorization: str | None = Header(default=None)):
            if authorization != f"Bearer {self.api_key}":
                raise HTTPException(401, "Authentication failed")
            if cid not in self.calls:
                raise HTTPException(404, "not found")
            return {"data": self.calls[cid]}

        @app.get("/v2/messages/{mid}")
        def get(mid: str, authorization: str | None = Header(default=None)):
            if authorization != f"Bearer {self.api_key}":
                raise HTTPException(401, "Authentication failed")
            if mid not in self.messages:
                raise HTTPException(404, "not found")
            return {"data": self.messages[mid]}

        return app
