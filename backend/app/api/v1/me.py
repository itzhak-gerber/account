from typing import Annotated

from fastapi import APIRouter, Depends

from app.auth.principal import CurrentPrincipal, DbSession, get_session_store
from app.auth.sessions import SessionStore
from app.core.db import commit
from app.core.errors import NotFound
from app.models import User
from app.schemas.identity import (
    BusinessOut,
    DisplayPreferencesIn,
    MembershipOut,
    MeOut,
    UserOut,
)
from app.services import businesses

router = APIRouter(tags=["me"])


@router.get("/me")
async def me(
    principal: CurrentPrincipal,
    session: DbSession,
    store: Annotated[SessionStore, Depends(get_session_store)],
) -> MeOut:
    user = await session.get(User, principal.user_id)
    if user is None:
        raise NotFound()
    memberships = await businesses.list_for_user(session, principal)
    csrf_token = None
    if principal.session_id:
        data = await store.get(principal.session_id)
        csrf_token = data.csrf_token if data else None
    return MeOut(
        user=UserOut.model_validate(user),
        memberships=[
            MembershipOut(business=BusinessOut.from_business(b), role=role)
            for b, role in memberships
        ],
        mfa=principal.mfa,
        csrf_token=csrf_token,
    )


@router.patch("/me/display-preferences")
async def set_display_preferences(
    body: DisplayPreferencesIn, principal: CurrentPrincipal, session: DbSession
) -> UserOut:
    """Light / dark / device theme and text size, kept per user across devices."""
    user = await session.get(User, principal.user_id)
    if user is None:
        raise NotFound()
    if body.theme is not None:
        user.theme = body.theme
    if body.text_size is not None:
        user.text_size = body.text_size
    result = UserOut.model_validate(user)
    await commit(session)
    return result
