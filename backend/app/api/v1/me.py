from typing import Annotated

from fastapi import APIRouter, Depends

from app.auth.principal import CurrentPrincipal, DbSession, get_session_store
from app.auth.sessions import SessionStore
from app.core.db import commit
from app.core.errors import NotFound
from app.models import User
from app.schemas.billing import PlanSummary
from app.schemas.identity import (
    BusinessOut,
    DisplayPreferencesIn,
    MembershipOut,
    MeOut,
    UserOut,
)
from app.services import billing, businesses, plans

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
    out = []
    for b, role in memberships:
        access = billing.access_of(await billing.current_subscription(session, b.id))
        out.append(
            MembershipOut(
                business=BusinessOut.from_business(b),
                role=role,
                plan=PlanSummary(
                    read_only=access.read_only,
                    modules=sorted(access.modules),
                    ends_on=access.ends_on,
                ),
            )
        )
    return MeOut(
        user=UserOut.model_validate(user),
        memberships=out,
        mfa=principal.mfa,
        is_operator=plans.is_operator(principal),
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
