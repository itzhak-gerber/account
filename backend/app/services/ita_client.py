"""HTTP calls to the Israel Tax Authority's open API (openapi.taxes.gov.il).

Everything specific to the tax authority's wire format lives here: the OAuth endpoints, the
allocation request ("Approval") and how its answer is read. Paths and field names follow the
authority's developer portal; confirm them in the sandbox before switching to production.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import httpx

from app.core.config import get_settings


class ItaUnavailable(Exception):
    """The tax authority could not be reached, or answered with a server error."""


class ItaRefused(Exception):
    """The tax authority answered and refused (bad token, invalid invoice, not eligible)."""

    def __init__(self, message: str, response: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.response = response or {}


@dataclass
class Tokens:
    access_token: str
    refresh_token: str
    access_expires_at: datetime
    refresh_expires_at: datetime | None


def _root() -> str:
    settings = get_settings()
    segment = "production" if settings.ita_environment == "production" else "tsandbox"
    return f"{settings.ita_base_url.rstrip('/')}/{segment}"


def authorize_url(state: str, redirect_uri: str) -> str:
    """Where the business owner signs in at the tax authority and approves this software."""
    settings = get_settings()
    query = urlencode(
        {
            "response_type": "code",
            "client_id": settings.ita_client_id,
            "redirect_uri": redirect_uri,
            "scope": settings.ita_scope,
            "state": state,
        }
    )
    return f"{_root()}/longtimetoken/oauth2/authorize?{query}"


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=get_settings().ita_timeout_seconds)


def _tokens(body: dict[str, Any], previous_refresh: str | None = None) -> Tokens:
    now = datetime.now(UTC)
    refresh_in = body.get("refresh_token_expires_in")
    return Tokens(
        access_token=body["access_token"],
        refresh_token=body.get("refresh_token") or previous_refresh or "",
        access_expires_at=now + timedelta(seconds=int(body.get("expires_in", 3600)) - 60),
        refresh_expires_at=now + timedelta(seconds=int(refresh_in)) if refresh_in else None,
    )


async def _token_request(form: dict[str, str]) -> dict[str, Any]:
    settings = get_settings()
    try:
        async with _client() as client:
            response = await client.post(
                f"{_root()}/longtimetoken/oauth2/token",
                data=form,
                auth=(settings.ita_client_id, settings.ita_client_secret),
            )
    except httpx.HTTPError as exc:
        raise ItaUnavailable(str(exc)[:200]) from exc
    if response.status_code >= 500:
        raise ItaUnavailable(f"HTTP {response.status_code}")
    if response.status_code != 200:
        raise ItaRefused(f"HTTP {response.status_code}: {response.text[:200]}")
    body: dict[str, Any] = response.json()
    return body


async def exchange_code(code: str, redirect_uri: str) -> Tokens:
    body = await _token_request(
        {"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri}
    )
    return _tokens(body)


async def refresh(refresh_token: str) -> Tokens:
    body = await _token_request(
        {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "scope": get_settings().ita_scope,
        }
    )
    return _tokens(body, previous_refresh=refresh_token)


def _find(body: dict[str, Any], *names: str) -> Any:
    """A field of the answer, whatever its letter case."""
    lowered = {k.lower(): v for k, v in body.items()}
    for name in names:
        if name.lower() in lowered:
            return lowered[name.lower()]
    return None


async def approval(access_token: str, invoice: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Ask for an allocation number. Returns it with the full answer."""
    try:
        async with _client() as client:
            response = await client.post(
                f"{_root()}/Invoices/v2/Approval",
                json=invoice,
                headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
            )
    except httpx.HTTPError as exc:
        raise ItaUnavailable(str(exc)[:200]) from exc
    if response.status_code >= 500 or response.status_code == 429:
        raise ItaUnavailable(f"HTTP {response.status_code}")
    try:
        body: dict[str, Any] = response.json()
    except ValueError:
        body = {"text": response.text[:500]}
    number = _find(body, "Confirmation_Number", "ConfirmationNumber", "allocation_number")
    status = _find(body, "Status")
    if response.status_code == 200 and number and str(status or 200) == "200":
        return str(number), body
    message = (
        _find(body, "Message", "message", "error_description") or f"HTTP {response.status_code}"
    )
    raise ItaRefused(str(message)[:300], body)
