"""The Ringlark API. Every route under /api needs a signed in session, except sign in and signed webhooks."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ringlark.api import routes_auth, routes_data, routes_demo, routes_ops, routes_tools, routes_webhooks
from ringlark.config import Settings
from ringlark.context import Ctx
from sendora_core.app import SESSION_COOKIE, create_base_app
from sendora_core.auth import read_session_token
from sendora_core.ratelimit import TokenBucket
from sendora_core.db import Base, make_engine, make_session_factory

PUBLIC = {"/api/auth/login", "/api/auth/logout"}
PUBLIC_PREFIX = ("/api/webhooks/", "/api/tools/")


def create_app(settings: Settings | None = None, ctx: Ctx | None = None) -> FastAPI:
    settings = settings or Settings()
    if ctx is None:
        engine = make_engine(settings.database_url)
        from sendora_core import models as _c  # noqa: F401
        import ringlark.models  # noqa: F401

        if settings.database_url.startswith("sqlite"):
            Base.metadata.create_all(engine)  # SQLite zero setup path. Postgres uses `alembic upgrade head`.
        ctx = Ctx(settings, make_session_factory(engine))
        if not settings.seed_dir and (Path(__file__).resolve().parents[5] / "data").exists():
            ctx.settings.seed_dir = str(Path(__file__).resolve().parents[5] / "data")
    app = create_base_app(ctx.settings, ctx.factory)
    app.title, app.version = "Ringlark API", "1.0.0"
    app.state.ctx = ctx
    # A dashboard page makes several calls at once. This bucket is per client address (set uvicorn --proxy-headers so that is the real visitor, not the web server).
    app.state.limiter = TokenBucket(capacity=600, refill_per_sec=20.0)
    # Sign in attempts per address and email: a burst of LOGIN_BURST (default 5), then one more every 12 seconds.
    app.state.login_bucket = TokenBucket(capacity=settings.login_burst, refill_per_sec=1 / 12)

    @app.middleware("http")
    async def require_session(request: Request, call_next):
        p = request.url.path
        if p.startswith("/api/") and p not in PUBLIC and not p.startswith(PUBLIC_PREFIX):
            token = request.cookies.get(SESSION_COOKIE) or request.headers.get("x-session")
            data = read_session_token(ctx.settings.session_secret, token) if token else None
            if data is None:
                return JSONResponse({"error": {"code": "http_401", "message": "Sign in to continue."}}, 401)
            request.state.user = data
        return await call_next(request)

    for r in (routes_auth, routes_data, routes_ops, routes_tools, routes_webhooks, routes_demo):
        app.include_router(r.router)
    return app


def seed_empty_demo(app: FastAPI) -> bool:
    """A first run in demo mode starts with the fictional practice already loaded, so no screen is empty and Run now has someone to call.
    Only when demo mode is on and the database has no agent yet. A database that already has data is never touched."""
    ctx: Ctx = app.state.ctx
    if not ctx.settings.demo_mode:
        return False
    from sqlalchemy import func, select

    from ringlark import demo
    from ringlark.models import Agent

    with ctx.factory() as s:
        if s.scalar(select(func.count(Agent.id))):
            return False
        demo.reset(s, ctx)
    return True


def app_from_env() -> FastAPI:  # uvicorn ringlark.api.app:app_from_env --factory
    app = create_app(Settings(_env_file=os.environ.get("ENV_FILE", ".env")))
    seed_empty_demo(app)
    return app
