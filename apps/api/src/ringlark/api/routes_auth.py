from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from ringlark.api.deps import get_ctx, user
from ringlark.context import Ctx
from sendora_core.auth import hash_password, make_session_token, verify_password
from sendora_core.ratelimit import RateLimitExceeded, TokenBucket

router = APIRouter(prefix="/api/auth", tags=["auth"])
DEMO_PASSWORD = "demo-password-1"  # only accepted when DEMO_MODE is true and no password hash is set


class Login(BaseModel):
    email: str
    password: str


def _accounts(ctx: Ctx) -> dict[str, tuple[str | None, str]]:
    s = ctx.settings
    out = {s.owner_email.lower(): (s.owner_password_hash, "owner")}
    if s.approver_email:
        out[s.approver_email.lower()] = (s.approver_password_hash, "approver")
    elif s.demo_mode:
        out["approver@example.test"] = (None, "approver")
    if s.viewer_email:
        out[s.viewer_email.lower()] = (s.viewer_password_hash, "viewer")
    elif s.demo_mode:
        out["viewer@example.test"] = (None, "viewer")
    return out


@router.post("/login", summary="Sign in with email and password")
def login(body: Login, request: Request, ctx: Ctx = Depends(get_ctx)):
    key = f"{request.client.host if request.client else 'x'}:{body.email.lower()}"
    try:
        request.app.state.login_bucket.check(key)
    except RateLimitExceeded as exc:
        raise HTTPException(429, str(exc)) from exc
    acc = _accounts(ctx).get(body.email.strip().lower())
    ok = False
    if acc:
        h, _ = acc
        ok = verify_password(body.password, h) if h else (ctx.settings.demo_mode and body.password == DEMO_PASSWORD)
    if not acc or not ok:
        raise HTTPException(401, "Email or password is wrong.")
    token = make_session_token(ctx.settings.session_secret, body.email.strip().lower(), acc[1])
    return {"token": token, "user": body.email.strip().lower(), "role": acc[1]}


@router.post("/logout", summary="End the session (the web app clears the cookie)")
def logout():
    return {"ok": True}


@router.get("/me", summary="Who is signed in")
def me(u: dict = Depends(user), ctx: Ctx = Depends(get_ctx)):
    return {"user": u["user"], "role": u["role"], "demo_mode": ctx.settings.demo_mode}
