"""Tool endpoints the voice engine calls during a call. Not session based: each call has its own token. A caller's words never reach here as commands, only the agent's tool calls do."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from ringlark.api.deps import db, get_ctx
from ringlark.context import Ctx
from ringlark.models import Call
from ringlark.tools import ToolService
from ringlark.toolauth import check_token, secret_for
from sendora_core.ratelimit import RateLimitExceeded

router = APIRouter(prefix="/api/tools", tags=["tools"])
TOOLS = {"book_meeting", "lookup_crm", "transfer_to_human", "send_sms", "press_digit", "end_call"}


@router.post("/{call_id}/{tool}", summary="Run one agent tool for one call")
async def run_tool(call_id: int, tool: str, request: Request, s: Session = Depends(db), ctx: Ctx = Depends(get_ctx), x_tool_token: str | None = Header(default=None)):
    if not check_token(secret_for(ctx.settings), call_id, x_tool_token):
        raise HTTPException(401, "Bad tool token.")
    if tool not in TOOLS:
        raise HTTPException(404, "Unknown tool.")
    try:
        request.app.state.tool_bucket.check(f"call:{call_id}")  # a model that repeats a tool call in a loop is slowed down
    except RateLimitExceeded as exc:
        raise HTTPException(429, str(exc)) from exc
    call = s.get(Call, call_id)
    if call is None or call.status not in ("placed", "in_progress"):
        raise HTTPException(409, "That call is not in progress.")
    raw = await request.body()  # already limited to 20 000 bytes by PerRouteBodyLimit before it is read
    if len(raw) > 20_000:
        raise HTTPException(413, "Body too large.")
    try:
        args = await request.json() if raw else {}
    except ValueError:
        args = {}
    return ToolService(s, ctx, call).run(tool, args if isinstance(args, dict) else {})
