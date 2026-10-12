from fastapi import APIRouter

from app.api.v1 import (
    admin,
    businesses,
    catalog,
    documents,
    exports,
    files,
    inventory,
    ita,
    me,
    notifications,
    plan,
    purchasing,
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
router.include_router(inventory.router)
router.include_router(purchasing.router)
router.include_router(ita.router)
router.include_router(plan.router)
router.include_router(admin.router)
