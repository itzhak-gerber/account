"""Connecting a business to the Israel Tax Authority for allocation numbers."""

from typing import Any

from fastapi import APIRouter, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from app.auth.principal import CurrentBusiness, CurrentPrincipal, DbSession, enter_business
from app.core.db import commit
from app.core.errors import AppError
from app.services import allocation

router = APIRouter(tags=["ita"])


class ConnectOut(BaseModel):
    url: str


@router.get("/businesses/{business_id}/ita")
async def ita_status(ctx: CurrentBusiness, session: DbSession) -> dict[str, Any]:
    return await allocation.status(session, ctx)


@router.post("/businesses/{business_id}/ita/connect")
async def connect(ctx: CurrentBusiness) -> ConnectOut:
    """The tax authority page where the owner approves this software; the browser goes there."""
    return ConnectOut(url=allocation.connect_url(ctx))


@router.delete("/businesses/{business_id}/ita", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect(ctx: CurrentBusiness, session: DbSession) -> None:
    await allocation.disconnect(session, ctx)
    await commit(session)


@router.get("/ita/callback", include_in_schema=False)
async def callback(
    principal: CurrentPrincipal,
    session: DbSession,
    state: str,
    code: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    """The tax authority sends the browser back here after the owner approved (or not)."""
    back = "/settings?tab=ita"
    if error or not code:
        return RedirectResponse(f"{back}&ita=cancelled", status_code=303)
    business_id = allocation.business_from_state(state, principal)
    ctx = await enter_business(session, principal, business_id)
    try:
        await allocation.finish_connect(session, ctx, code)
    except AppError:
        return RedirectResponse(f"{back}&ita=failed", status_code=303)
    await commit(session)
    return RedirectResponse(f"{back}&ita=connected", status_code=303)
