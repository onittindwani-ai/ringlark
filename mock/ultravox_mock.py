"""A local mock of the Ultravox API, written from the public API reference (UNVERIFIED against the real service).

POST /api/calls with `X-API-Key` makes a call and returns callId and joinUrl. GET /api/calls/{id}/messages returns what was said
(the real path and field names are UNVERIFIED). `signed_webhook` builds a webhook with the documented headers: HMAC SHA256 hex of body plus timestamp.
"""

from __future__ import annotations

import json
import time
import uuid

from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse

from ringlark.adapters.ultravox import sign_ultravox


class UltravoxMock:
    def __init__(self, api_key: str = "mock-ultravox-key", webhook_secret: str = "mock-uv-webhook-secret"):
        self.api_key, self.webhook_secret = api_key, webhook_secret
        self.calls: dict[str, dict] = {}
        self.messages: dict[str, list[dict]] = {}
        self.app = self._build()

    def signed_webhook(self, event: str, call: dict, timestamp: int | None = None, secret: str | None = None) -> tuple[bytes, dict[str, str]]:
        ts = str(timestamp or int(time.time()))
        body = json.dumps({"event": event, "call": call}).encode()
        return body, {"X-Ultravox-Webhook-Timestamp": ts, "X-Ultravox-Webhook-Signature": sign_ultravox(secret or self.webhook_secret, body, ts), "content-type": "application/json"}

    def _build(self) -> FastAPI:
        app = FastAPI(title="Ultravox mock")

        @app.post("/api/calls", status_code=201)
        async def create(request: Request, x_api_key: str | None = Header(default=None)):
            if x_api_key != self.api_key:
                return JSONResponse({"detail": "Invalid API key"}, 403)
            body = await request.json()
            if not body.get("systemPrompt"):
                return JSONResponse({"detail": "systemPrompt is required"}, 400)
            if body.get("voice") and body.get("externalVoice"):
                return JSONResponse({"detail": "voice and externalVoice cannot be combined"}, 400)
            cid = str(uuid.uuid4())
            self.calls[cid] = {"callId": cid, "joinUrl": f"wss://mock.ultravox.example.test/join/{cid}", "request": body}
            return {k: v for k, v in self.calls[cid].items() if k != "request"}

        @app.get("/api/calls/{cid}/messages")
        def messages(cid: str, x_api_key: str | None = Header(default=None)):
            if x_api_key != self.api_key:
                return JSONResponse({"detail": "Invalid API key"}, 403)
            if cid not in self.calls:
                return JSONResponse({"detail": "not found"}, 404)
            return {"results": self.messages.get(cid, [])}

        @app.get("/api/voices")
        def voices(x_api_key: str | None = Header(default=None)):
            if x_api_key != self.api_key:
                return JSONResponse({"detail": "Invalid API key"}, 403)
            return {"results": [{"voiceId": "mock-voice-1", "name": "Mock Voice"}]}

        return app
