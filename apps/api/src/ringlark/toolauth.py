"""A token per call for the tool endpoints. The voice engine sends it as a header, so only the call it belongs to can use the tools, and only for a short time.

The signing key is made from its own secret (TOOL_TOKEN_SECRET, or a key derived from SESSION_SECRET with a fixed label), so a session secret that leaks
does not by itself let a stranger use the tool endpoints of another call, and a token is never valid as a session."""

from __future__ import annotations

import hashlib
import hmac
import time

from sendora_core.adapters import AdapterError

TOKEN_TTL_S = 20 * 60  # a call lasts at most 10 minutes (max_seconds); the rest is margin for a slow start
_LABEL = b"ringlark-tool-token-v1"


def _key(secret: str) -> bytes:
    return hmac.new(secret.encode(), _LABEL, hashlib.sha256).digest()


def _sign(secret: str, call_id: int, expires: int) -> str:
    return hmac.new(_key(secret), f"tool:{call_id}:{expires}".encode(), hashlib.sha256).hexdigest()[:40]


def tool_token(secret: str, call_id: int, now: float | None = None, ttl_s: int = TOKEN_TTL_S) -> str:
    expires = int((now if now is not None else time.time()) + ttl_s)
    return f"{expires}.{_sign(secret, call_id, expires)}"


def check_token(secret: str, call_id: int, token: str | None, now: float | None = None) -> bool:
    """True only for a token made for this call that has not expired. Compared as bytes, so a header with odd characters is a plain no, never an error."""
    try:
        expires_text, sig = (token or "").split(".", 1)
        expires = int(expires_text)
        if expires < (now if now is not None else time.time()):
            return False
        return hmac.compare_digest(_sign(secret, call_id, expires).encode(), sig.encode())
    except (ValueError, TypeError, UnicodeError):
        return False


def tool_base_url(settings) -> str:
    """Where the voice engine reaches the tool endpoints. Outside demo mode an empty PUBLIC_BASE_URL is an error, never a guessed address."""
    if settings.public_base_url:
        return settings.public_base_url
    if settings.demo_mode:
        return "https://example.test"  # the offline demo never calls it
    raise AdapterError("PUBLIC_BASE_URL is empty, so the voice engine could not reach the tool endpoints. Set it to the public https address of the API.")


def secret_for(settings) -> str:
    return settings.tool_token_secret or settings.session_secret
