"""
Admin Routes Package

This package contains all admin-related API endpoints, split into logical modules
for better maintainability.

The combined router is exported as `router` for use in the main application.
"""

from fastapi import APIRouter

from .status import router as status_router
from .collection import router as collection_router
from .storage import router as storage_router
from .jobs import router as jobs_router
from .documents import router as documents_router
from .metadata import router as metadata_router

# Combined router that includes all admin sub-routers
router = APIRouter(prefix="/admin", tags=["Admin"])

# Include all sub-routers (they have no prefix since combined router has /admin)
router.include_router(status_router)
router.include_router(collection_router)
router.include_router(storage_router)
router.include_router(jobs_router)
router.include_router(documents_router)
router.include_router(metadata_router)

__all__ = ["router"]
