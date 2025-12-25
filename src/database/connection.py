"""
DevChat v2.0 SOTA - Database Connection

Async PostgreSQL connection using SQLAlchemy 2.0.
"""

import os
from typing import AsyncGenerator, Optional
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    AsyncEngine,
    create_async_engine,
    async_sessionmaker,
)
from sqlalchemy.pool import NullPool

from src.utils.logging import get_logger

logger = get_logger(__name__)

# Global engine and session - initialized at runtime by init_database()
engine: Optional[AsyncEngine] = None
async_session: Optional[async_sessionmaker[AsyncSession]] = None


def _get_database_url() -> str:
    """
    Get and normalize the DATABASE_URL from environment.
    Called at runtime, not import time, to ensure env vars are available.
    """
    url = os.getenv("DATABASE_URL", "")
    
    if not url:
        return ""
    
    # Handle Railway's postgres:// vs postgresql:// format
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql://") and "+asyncpg" not in url:
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    
    return url


def init_database(database_url: str = None) -> tuple[AsyncEngine, async_sessionmaker]:
    """
    Initialize database connection.
    
    Call this at app startup to set up the connection pool.
    """
    global engine, async_session
    
    # Get URL at runtime (not import time) to ensure env vars are available
    url = database_url or _get_database_url()
    
    if not url:
        logger.warning("DATABASE_URL not set - PostgreSQL features disabled")
        return None, None
    
    logger.info(f"Initializing database connection to: {url.split('@')[-1] if '@' in url else 'local'}")
    
    engine = create_async_engine(
        url,
        poolclass=NullPool,  # Best for serverless
        echo=os.getenv("DB_ECHO", "false").lower() == "true",
    )
    
    async_session = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    
    logger.info("✅ Database engine and session factory created")
    
    return engine, async_session


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency for FastAPI routes.
    
    Usage:
        @router.get("/documents")
        async def get_documents(db: AsyncSession = Depends(get_db)):
            ...
    """
    if async_session is None:
        raise RuntimeError("Database not initialized. Call init_database() first.")
    
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@asynccontextmanager
async def get_db_context() -> AsyncGenerator[AsyncSession, None]:
    """
    Context manager for non-FastAPI usage.
    
    Usage:
        async with get_db_context() as db:
            docs = await DocumentRepository.list_all(db)
    """
    if async_session is None:
        raise RuntimeError("Database not initialized. Call init_database() first.")
    
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def create_tables():
    """Create all tables. Call once at startup or in migrations."""
    from .models import Base
    
    if engine is None:
        logger.warning("Cannot create tables - database not initialized")
        return
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    logger.info("Database tables created successfully")


async def close_database():
    """Close database connections. Call at app shutdown."""
    global engine
    
    if engine is not None:
        await engine.dispose()
        logger.info("Database connections closed")
