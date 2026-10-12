"""The business's own plan: what it includes, this month's usage, and asking to upgrade."""

from fastapi import APIRouter

from app.auth.principal import CurrentBusiness, DbSession
from app.core.db import commit
from app.schemas.billing import PlanStatusOut, UpgradeRequestIn
from app.services import plans

router = APIRouter(prefix="/businesses/{business_id}/plan", tags=["plan"])


@router.get("")
async def get_plan(ctx: CurrentBusiness, session: DbSession) -> PlanStatusOut:
    return await plans.status(session, ctx)


@router.post("/upgrade-request", status_code=202)
async def request_upgrade(
    ctx: CurrentBusiness, session: DbSession, data: UpgradeRequestIn
) -> dict[str, str]:
    await plans.request_upgrade(session, ctx, data)
    await commit(session)
    return {"status": "sent"}
