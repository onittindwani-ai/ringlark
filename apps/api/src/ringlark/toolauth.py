"""A token per call for the tool endpoints. The voice engine sends it as a header, so only the call it belongs to can use the tools."""

from __future__ import annotations

import hashlib
import hmac


def tool_token(secret: str, call_id: int) -> str:
    return hmac.new(secret.encode(), f"tool:{call_id}".encode(), hashlib.sha256).hexdigest()[:40]


def check_token(secret: str, call_id: int, token: str | None) -> bool:
    return bool(token) and hmac.compare_digest(tool_token(secret, call_id), token)
