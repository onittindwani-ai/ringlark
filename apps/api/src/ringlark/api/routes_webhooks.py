"""Signed webhooks. Nothing here uses a session: each one checks its own signature first and refuses everything else."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from ringlark import live
from ringlark.adapters.telnyx import verify_telnyx_webhook
from ringlark.adapters.ultravox import verify_ultravox_webhook
from ringlark.api.deps import db, get_ctx
from ringlark.context import Ctx
from sendora_core.events import record_event
from sendora_core.safety import SafetyError

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])
MAX_BODY = 1_000_000


async def body_of(request: Request) -> bytes:
    raw = await request.body()
    if len(raw) > MAX_BODY:
        raise HTTPException(413, "Body too large.")
    return raw


@router.post("/telnyx", summary="Call and text events from Telnyx (Ed25519 signed)")
async def telnyx(request: Request, s: Session = Depends(db), ctx: Ctx = Depends(get_ctx), telnyx_signature_ed25519: str | None = Header(default=None), telnyx_timestamp: str | None = Header(default=None)):
    raw = await body_of(request)
    if not (telnyx_signature_ed25519 and telnyx_timestamp and verify_telnyx_webhook(ctx.settings.telnyx_public_key, raw, telnyx_signature_ed25519, telnyx_timestamp)):
        raise HTTPException(401, "Bad signature.")
    try:
        d = json.loads(raw)["data"]
        et, payload = d["event_type"], dict(d.get("payload", {}))
        payload["_event_id"], payload["_occurred_at"] = str(d.get("id") or ""), d.get("occurred_at")
    except (ValueError, KeyError, TypeError):
        return {"ok": True, "ignored": True}
    try:
        # Answering an inbound call talks to Ultravox and Telnyx (up to 20 and 15 seconds). That runs on a worker thread so the event loop keeps serving.
        result = await run_in_threadpool(live.handle_telnyx_event, s, ctx, ctx.effective(s), et, payload)
    except live.CallNotFoundYet as exc:
        # The call is named in the event but not saved yet: say so, and Telnyx sends the event again instead of it being lost.
        raise HTTPException(503, "That call is not saved yet. Send the event again.") from exc
    except SafetyError as exc:
        record_event(s, "webhook.blocked", None, None, {"event": et, "why": type(exc).__name__})
        result = "blocked_by_safety"
    return {"ok": True, "result": result}


@router.post("/ultravox", summary="Call events from Ultravox (HMAC signed)")
async def ultravox(request: Request, s: Session = Depends(db), ctx: Ctx = Depends(get_ctx), x_ultravox_webhook_signature: str | None = Header(default=None), x_ultravox_webhook_timestamp: str | None = Header(default=None)):
    raw = await body_of(request)
    if not verify_ultravox_webhook(ctx.settings.ultravox_webhook_secret, raw, x_ultravox_webhook_signature or "", x_ultravox_webhook_timestamp or ""):
        raise HTTPException(401, "Bad signature.")
    try:
        ev = json.loads(raw)
        event, call = ev["event"], ev.get("call", {})
    except (ValueError, KeyError, TypeError):
        return {"ok": True, "ignored": True}
    return {"ok": True, "result": await run_in_threadpool(live.handle_ultravox_event, s, event, call)}
