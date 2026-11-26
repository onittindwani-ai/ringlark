"""A size limit per kind of route, checked before the body is read. The base app already refuses anything over MAX_BODY_BYTES (25 MB); these routes
are open to anyone (sign in, webhooks, tool calls), so they get the limit they really need."""

from __future__ import annotations

from sendora_core.app import BodyTooLarge, LimitBodySize

LIMITS = (("/api/auth/login", 8_192), ("/api/webhooks/", 1_000_000), ("/api/tools/", 20_000))


class PerRouteBodyLimit:
    def __init__(self, app, limits=LIMITS):
        self.app, self.limits = app, limits

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            path = scope.get("path", "")
            for prefix, limit in self.limits:
                if path.startswith(prefix):
                    return await LimitBodySize(self.app, limit)(scope, receive, send)
        return await self.app(scope, receive, send)


__all__ = ["PerRouteBodyLimit", "BodyTooLarge", "LIMITS"]
