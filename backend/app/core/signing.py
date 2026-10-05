"""Short-lived signed tokens (HMAC-SHA256) for links that work without a session."""

import base64
import hashlib
import hmac
import json
import time
from typing import Any

from app.core.config import get_settings
from app.core.errors import Forbidden


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def _mac(body: str, purpose: str) -> str:
    key = get_settings().secret_key.encode()
    return _b64(hmac.new(key, f"{purpose}.{body}".encode(), hashlib.sha256).digest())


def sign(payload: dict[str, Any], *, purpose: str, ttl_seconds: int) -> str:
    body = _b64(json.dumps({**payload, "exp": int(time.time()) + ttl_seconds}).encode())
    return f"{body}.{_mac(body, purpose)}"


def verify(token: str, *, purpose: str) -> dict[str, Any]:
    try:
        body, mac = token.split(".", 1)
        if not hmac.compare_digest(mac, _mac(body, purpose)):
            raise ValueError("bad signature")
        payload: dict[str, Any] = json.loads(_unb64(body))
    except (ValueError, json.JSONDecodeError) as exc:
        raise Forbidden("Invalid link", code="invalid_link") from exc
    if payload.get("exp", 0) < time.time():
        raise Forbidden("This link has expired", code="link_expired")
    return payload
