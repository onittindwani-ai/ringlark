from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from ringlark.api.deps import get_ctx, user
from ringlark.context import Ctx
from sendora_core.auth import clean_email, make_session_token, verify_password_or_dummy
from sendora_core.ratelimit import RateLimitExceeded

router = APIRouter(prefix="/api/auth", tags=["auth"])
DEMO_PASSWORD = "demo-password-1"  # only accepted when settings.demo_shortcuts is true: DEMO_MODE on and no owner password hash set


class Login(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=1024)


def _accounts(ctx: Ctx) -> dict[str, tuple[str | None, str]]:
    s = ctx.settings
    out = {clean_email(s.owner_email): (s.owner_password_hash, "owner")}
    if s.approver_email:
        out[clean_email(s.approver_email)] = (s.approver_password_hash, "approver")
    elif s.demo_shortcuts:
        out["approver@example.test"] = (None, "approver")
    if s.viewer_email:
        out[clean_email(s.viewer_email)] = (s.viewer_password_hash, "viewer")
    elif s.demo_shortcuts:
        out["viewer@example.test"] = (None, "viewer")
    return out


def _throttle(request: Request, email: str) -> None:
    """Three limits on one cleaned spelling of the email: this address trying this account, this address trying anything, and anyone trying this account."""
    host = request.client.host if request.client else "x"
    st = request.app.state
    try:
        st.login_ip_bucket.check(host)
        st.login_account_bucket.check(email)
        st.login_bucket.check(f"{host}:{email}")
    except RateLimitExceeded as exc:
        raise HTTPException(429, str(exc)) from exc


@router.post("/login", summary="Sign in with email and password")
def login(body: Login, request: Request, ctx: Ctx = Depends(get_ctx)):
    email = clean_email(body.email)
    _throttle(request, email)
    acc = _accounts(ctx).get(email)
    if acc is not None and acc[0] is None:
        # No password hash: only the public demo password works, and only while demo shortcuts exist. Same work either way.
        verify_password_or_dummy(body.password, None)
        ok = ctx.settings.demo_shortcuts and body.password == DEMO_PASSWORD
    else:
        ok = verify_password_or_dummy(body.password, acc[0] if acc else None)
    if acc is None or not ok:
        raise HTTPException(401, "Email or password is wrong.")
    return {"token": make_session_token(ctx.settings.session_secret, email, acc[1]), "user": email, "role": acc[1]}


@router.post("/logout", summary="End the session (the web app clears the cookie)")
def logout():
    return {"ok": True}


@router.get("/me", summary="Who is signed in")
def me(u: dict = Depends(user), ctx: Ctx = Depends(get_ctx)):
    return {"user": u["user"], "role": u["role"], "demo_mode": ctx.settings.demo_shortcuts}
