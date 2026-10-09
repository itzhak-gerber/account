from fastapi import APIRouter

from app.api.v1 import (
    businesses,
    catalog,
    documents,
    exports,
    files,
    me,
    notifications,
    reports,
    system,
)

router = APIRouter(prefix="/api/v1")
router.include_router(system.router)
router.include_router(me.router)
router.include_router(businesses.router)
router.include_router(catalog.router)
router.include_router(documents.router)
router.include_router(files.router)
router.include_router(reports.router)
router.include_router(notifications.router)
router.include_router(exports.router)
