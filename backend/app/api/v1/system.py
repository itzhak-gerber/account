from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.services.system import SystemStatus, get_system_status

router = APIRouter(tags=["system"])


@router.get("/health")
async def health(session: Annotated[AsyncSession, Depends(get_session)]) -> SystemStatus:
    return await get_system_status(session)
