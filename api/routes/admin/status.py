"""
Admin Status Routes

Endpoints for database status, metrics, and overall admin dashboard status.
"""

import asyncio
import os
from typing import Optional

import boto3
from fastapi import APIRouter, Query

from api.schemas import (
    AdminStatusResponse,
    MetricsResponse,
    ServiceConnection,
    StorageStatus,
)
from src.config.settings import settings
from src.utils.logging import get_logger
from src.utils.metrics import get_metrics_tracker

from ..dependencies import (
    get_collection_info_cache,
    get_indexer,
)

logger = get_logger(__name__)

router = APIRouter()


# =============================================================================
# Database Status (Debug)
# =============================================================================

@router.get("/db-status")
async def get_db_status():
    """Check PostgreSQL connection status (debug endpoint)."""
    from ..dependencies import is_postgres_available, get_db_session
    
    db_url = os.getenv("DATABASE_URL", "")
    # Mask password for security
    if "@" in db_url and ":" in db_url:
        parts = db_url.split("@")
        prefix = parts[0].rsplit(":", 1)[0] + ":***"
        db_url_masked = prefix + "@" + "@".join(parts[1:])
    else:
        db_url_masked = db_url if db_url else "(not set)"
    
    result = {
        "postgres_available": is_postgres_available(),
        "database_url": db_url_masked,
    }
    
    if is_postgres_available():
        try:
            db = await get_db_session()
            if db:
                async with db:
                    from sqlalchemy import text
                    res = await db.execute(text("SELECT COUNT(*) FROM documents"))
                    count = res.scalar()
                    result["document_count"] = count
                    result["connection"] = "success"
            else:
                result["connection"] = "session_unavailable"
        except Exception as e:
            result["connection"] = "error"
            result["error"] = str(e)
    
    return result


# =============================================================================
# Metrics Endpoints
# =============================================================================

@router.get("/metrics", response_model=MetricsResponse)
async def get_metrics(
    last_n: Optional[int] = Query(default=None, description="Only last N queries"),
):
    """Get metrics summary."""
    tracker = get_metrics_tracker()
    summary = tracker.get_summary(last_n)
    
    if "message" in summary:
        return MetricsResponse(
            total_queries=0,
            latency={},
            query_types={},
            error_rate_percent=0.0,
            tokens={},
        )
    
    return MetricsResponse(
        total_queries=summary["total_queries"],
        latency=summary["latency"],
        query_types=summary["query_types"],
        error_rate_percent=summary["error_rate_percent"],
        tokens=summary["tokens"],
    )


# =============================================================================
# Admin Status
# =============================================================================

@router.get("/status", response_model=AdminStatusResponse)
async def get_admin_status():
    """
    Get admin dashboard status including storage and service connections.
    
    Performs real checks on all services with timeouts to prevent blocking.
    """
    connections = []
    storage_info = StorageStatus(
        bucket=os.getenv("R2_BUCKET_NAME", "devchat-pdfs"),
        input_path="/input-pdfs/",
        output_path="/outputs/",
        storage_used_bytes=0,
        file_count=0,
    )
    
    collection_cache = get_collection_info_cache()
    
    # Check R2 (with timeout)
    async def check_r2():
        try:
            loop = asyncio.get_event_loop()
            
            def _check():
                account_id = os.getenv("R2_ACCOUNT_ID", "667549da0201b12a53872d803b9880b6")
                access_key = os.getenv("R2_ACCESS_KEY_ID")
                secret_key = os.getenv("R2_SECRET_ACCESS_KEY")
                
                if not access_key or not secret_key:
                    return "disconnected", "No credentials", 0, 0
                
                client = boto3.client(
                    "s3",
                    endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
                    aws_access_key_id=access_key,
                    aws_secret_access_key=secret_key,
                    region_name="auto",
                )
                
                bucket = os.getenv("R2_BUCKET_NAME", "devchat-pdfs")
                # List objects to get count and size (limit to first 100 for speed)
                response = client.list_objects_v2(Bucket=bucket, Prefix="input-pdfs/", MaxKeys=100)
                
                file_count = response.get("KeyCount", 0)
                total_size = sum(obj.get("Size", 0) for obj in response.get("Contents", []))
                
                return "connected", bucket, file_count, total_size
            
            status, details, count, size = await asyncio.wait_for(
                loop.run_in_executor(None, _check),
                timeout=5.0
            )
            return status, details, count, size
        except asyncio.TimeoutError:
            return "timeout", "Connection timeout", 0, 0
        except Exception as e:
            logger.warning(f"R2 check failed: {e}")
            return "disconnected", str(e)[:50], 0, 0
    
    # Check Qdrant (use cached collection info)
    async def check_qdrant():
        try:
            # Use the cached collection info endpoint logic
            if collection_cache["data"] and collection_cache["data"].get("points_count"):
                info = collection_cache["data"]
                return "connected", f"{info['points_count']:,} vectors"
            
            # Try fresh check
            loop = asyncio.get_event_loop()
            
            def _check():
                indexer = get_indexer()
                info = indexer.get_collection_info()
                return info
            
            info = await asyncio.wait_for(
                loop.run_in_executor(None, _check),
                timeout=3.0
            )
            
            if "error" in info:
                return "disconnected", info["error"][:50]
            return "connected", f"{info.get('points_count', 0):,} vectors"
        except asyncio.TimeoutError:
            return "timeout", "Connection timeout"
        except Exception as e:
            logger.warning(f"Qdrant check failed: {e}")
            return "disconnected", str(e)[:50]
    
    # Check LLM (just verify API key exists)
    def check_llm():
        if settings.openrouter_api_key:
            return "connected", "OpenRouter (GPT-4o)"
        elif settings.openai_api_key:
            return "connected", "OpenAI"
        elif settings.anthropic_api_key:
            return "connected", "Anthropic"
        return "disconnected", "No API key"
    
    # Check Cohere
    def check_cohere():
        if settings.cohere_api_key:
            return "connected", "embed-v4.0"
        return "disconnected", "No API key"
    
    # Run checks in parallel
    r2_result, qdrant_result = await asyncio.gather(
        check_r2(),
        check_qdrant(),
    )
    
    r2_status, r2_details, file_count, total_size = r2_result
    qdrant_status, qdrant_details = qdrant_result
    llm_status, llm_details = check_llm()
    cohere_status, cohere_details = check_cohere()
    
    # Update storage info
    storage_info = StorageStatus(
        bucket=os.getenv("R2_BUCKET_NAME", "devchat-pdfs"),
        input_path="/input-pdfs/",
        output_path="/outputs/",
        storage_used_bytes=total_size,
        file_count=file_count,
    )
    
    connections = [
        ServiceConnection(name="Cloudflare R2", status=r2_status, details=r2_details),
        ServiceConnection(name="Qdrant Cloud", status=qdrant_status, details=qdrant_details),
        ServiceConnection(name="LLM Provider", status=llm_status, details=llm_details),
        ServiceConnection(name="Cohere API", status=cohere_status, details=cohere_details),
    ]
    
    return AdminStatusResponse(
        storage=storage_info,
        connections=connections,
        pending_jobs=0,  # TODO: Track actual job queue
        active_workers=1 if all(c.status == "connected" for c in connections) else 0,
    )
