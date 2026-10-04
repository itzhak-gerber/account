from fastapi import APIRouter

from app.api.v1 import businesses, me, system

router = APIRouter(prefix="/api/v1")
router.include_router(system.router)
router.include_router(me.router)
router.include_router(businesses.router)
