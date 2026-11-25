from __future__ import annotations

from collections.abc import Iterator

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from ringlark.context import Ctx
from sendora_core.auth import WRITE_ROLES


def get_ctx(request: Request) -> Ctx:
    return request.app.state.ctx


def db(request: Request) -> Iterator[Session]:
    s = request.app.state.ctx.factory()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


def user(request: Request) -> dict:
    u = getattr(request.state, "user", None)
    if not u:
        raise HTTPException(401, "Sign in to continue.")
    return u


def writer(request: Request) -> dict:
    u = user(request)
    if u["role"] not in WRITE_ROLES:
        raise HTTPException(403, "This needs the owner or an approver.")
    return u


def owner(request: Request) -> dict:
    u = user(request)
    if u["role"] != "owner":
        raise HTTPException(403, "Only the owner can do this.")
    return u


def demo_only(request: Request) -> None:
    if not request.app.state.ctx.settings.demo_shortcuts:  # an owner password hash switches every demo route off
        raise HTTPException(404, "Not found.")
