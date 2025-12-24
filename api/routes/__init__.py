"""
DevChat v2.0 SOTA - API Routes Package

Auto-discovers and aggregates all routers from this package.
"""

from fastapi import APIRouter

from .health import router as health_router
from .chat import router as chat_router
from .api import router as api_router
from .admin import router as admin_router

# Legacy router for backwards compatibility (root-level endpoints)
router = APIRouter()

__all__ = [
    "router",
    "health_router", 
    "chat_router",
    "api_router",
    "admin_router",
]
