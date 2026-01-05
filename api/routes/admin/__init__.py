"""
Admin Routes Package

This package contains all admin-related API endpoints, split into logical modules
for better maintainability.

The combined router is exported as `router` for use in the main application.

Authentication:
- Protected routes require X-Admin-API-Key header OR X-Admin-Session token
- Login/logout/auth-status endpoints are public (no auth required)
- Set ADMIN_PASSWORD env var for browser login
- Set ADMIN_API_KEY env var for programmatic access
"""

from fastapi import APIRouter, Depends

from ..dependencies import verify_admin_api_key
from .auth import router as auth_router
from .status import router as status_router
from .collection import router as collection_router
from .storage import router as storage_router
from .jobs import router as jobs_router
from .documents import router as documents_router
from .metadata import router as metadata_router
from .bibliography import router as bibliography_router
from .usage import router as usage_router
from .users import router as users_router
from .quality import router as quality_router

# Auth router (login/logout) - NO authentication required
# This must be separate so users can actually log in
public_router = APIRouter(
    prefix="/admin",
    tags=["Admin Auth"],
)
public_router.include_router(auth_router)

# Protected router - requires authentication
protected_router = APIRouter(
    prefix="/admin",
    tags=["Admin"],
    dependencies=[Depends(verify_admin_api_key)],
)

# Include all protected sub-routers
protected_router.include_router(status_router)
protected_router.include_router(collection_router)
protected_router.include_router(storage_router)
protected_router.include_router(jobs_router)
protected_router.include_router(documents_router)
protected_router.include_router(metadata_router)
protected_router.include_router(bibliography_router)
protected_router.include_router(usage_router)
protected_router.include_router(users_router)
protected_router.include_router(quality_router)

# Combined router that includes both public and protected routes
router = APIRouter()
router.include_router(public_router)
router.include_router(protected_router)

__all__ = ["router"]
