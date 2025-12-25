"""
DevChat v2.0 SOTA - Database Package

PostgreSQL metadata store for fast document queries.
"""

from .models import Document, Base
from .connection import get_db, engine, async_session
from .repository import DocumentRepository

__all__ = [
    "Document",
    "Base",
    "get_db",
    "engine",
    "async_session",
    "DocumentRepository",
]
