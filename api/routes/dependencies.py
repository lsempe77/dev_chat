"""
DevChat v2.0 SOTA - Shared Route Dependencies

Common dependencies, singletons, and utilities used across route modules.
"""

import asyncio
import os
from typing import Optional

import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv
from fastapi import HTTPException

from src.agents.devchat_agent import DevChatAgent
from src.config.settings import settings
from src.ingestion.indexer import QdrantIndexer
from src.utils.logging import get_logger

# Load environment variables from .env file
load_dotenv()

logger = get_logger(__name__)

# =============================================================================
# Global Singletons
# =============================================================================

_agent: Optional[DevChatAgent] = None
_indexer: Optional[QdrantIndexer] = None


def get_agent() -> DevChatAgent:
    """Get or create the global agent instance."""
    global _agent
    if _agent is None:
        _agent = DevChatAgent()
    return _agent


def get_indexer() -> QdrantIndexer:
    """Get or create the global indexer instance (avoids repeated Qdrant connections)."""
    global _indexer
    if _indexer is None:
        _indexer = QdrantIndexer()
    return _indexer


# =============================================================================
# Database (PostgreSQL)
# =============================================================================

def is_postgres_available() -> bool:
    """Check if PostgreSQL is configured and available."""
    return bool(os.getenv("DATABASE_URL"))


async def get_db_session():
    """Get database session if available. Returns None if not configured."""
    if not is_postgres_available():
        return None
    
    try:
        # Import the module to access the current value of async_session
        # (not a cached import-time value)
        import src.database.connection as db_conn
        if db_conn.async_session is None:
            return None
        return db_conn.async_session()
    except Exception:
        return None


# =============================================================================
# R2 Client
# =============================================================================

def get_r2_client():
    """Create S3 client configured for Cloudflare R2."""
    account_id = os.getenv("R2_ACCOUNT_ID", "667549da0201b12a53872d803b9880b6")
    access_key = os.getenv("R2_ACCESS_KEY_ID")
    secret_key = os.getenv("R2_SECRET_ACCESS_KEY")
    
    if not access_key or not secret_key:
        raise HTTPException(
            status_code=500,
            detail="R2 credentials not configured. Set R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY."
        )
    
    return boto3.client(
        "s3",
        endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name="auto",
    )


# =============================================================================
# Cache Management
# =============================================================================

# Cache for collection info (refreshes every 30 seconds)
_collection_info_cache = {
    "data": None,
    "timestamp": 0
}
COLLECTION_CACHE_TTL = 30  # seconds

# Longer cache TTL because scanning 400K+ vectors is expensive
DOCUMENTS_CACHE_TTL = 300  # 5 minutes
_documents_cache = {
    "data": None,
    "timestamp": 0,
    "search": None,
    "status": None,
}

METADATA_CACHE_TTL = 30  # seconds
_metadata_cache = {
    "data": None,
    "timestamp": 0,
    "filter": None,
}


def get_collection_info_cache():
    """Get the collection info cache."""
    return _collection_info_cache


def get_documents_cache():
    """Get the documents cache."""
    return _documents_cache


def get_metadata_cache():
    """Get the metadata cache."""
    return _metadata_cache


def invalidate_admin_caches() -> None:
    """Clear lightweight admin caches after mutations."""
    _documents_cache["data"] = None
    _documents_cache["timestamp"] = 0
    _metadata_cache["data"] = None
    _metadata_cache["timestamp"] = 0


# =============================================================================
# Modal Processing Trigger
# =============================================================================

async def trigger_modal_processing(force_reprocess: bool = False, max_documents: int = 10):
    """Helper to trigger Modal processing via webhook."""
    import httpx
    
    # Modal web endpoint URL
    modal_trigger_url = os.environ.get(
        "MODAL_TRIGGER_URL",
        "https://lsempe77--devchat-mineru-trigger-processing.modal.run"
    )
    
    try:
        # Longer timeout (90s) to handle Modal cold starts
        # Modal functions can take 30-60s to spin up from cold
        async with httpx.AsyncClient(timeout=90.0) as client:
            response = await client.post(
                modal_trigger_url,
                json={
                    "force_reprocess": force_reprocess,
                    "check_qdrant": True,
                    "max_documents": max_documents,
                },
                headers={"Content-Type": "application/json"},
            )
            logger.info(f"Triggered Modal processing via {modal_trigger_url}: {response.status_code}")
            return response.json() if response.status_code == 200 else None
    except Exception as e:
        logger.error(f"Failed to trigger Modal processing: {e}")
        raise  # Re-raise so caller knows it failed
