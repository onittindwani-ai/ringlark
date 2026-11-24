"""Signed webhooks. Nothing here uses a session: each one checks its own signature first and refuses everything else."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Header, HTTPException, Request
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
        et, payload = d["event_type"], d.get("payload", {})
    except (ValueError, KeyError, TypeError):
        return {"ok": True, "ignored": True}
    try:
        result = live.handle_telnyx_event(s, ctx, ctx.effective(s), et, payload)
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
    return {"ok": True, "result": live.handle_ultravox_event(s, event, call)}
