"""
DevChat v2.0 SOTA - Health Check Routes

Endpoints for service health monitoring and Kubernetes probes.
"""

import os
from datetime import datetime

from fastapi import APIRouter

from api.qdrant_status import get_qdrant_status_snapshot
from api.schemas import HealthResponse
from src.config.settings import settings
from src.utils.cache import get_response_cache
from src.utils.circuit_breaker import get_all_breaker_status

router = APIRouter(prefix="/health", tags=["Health"])


@router.get("", response_model=HealthResponse)
async def health_check():
    """
    Check service health.
    
    Returns status of all components.
    """
    components = {
        "api": True,
        "qdrant": False,
        "llm": False,
        "r2": False,
        "cohere": False,
    }

    qdrant_status = await get_qdrant_status_snapshot()
    components["qdrant"] = qdrant_status.healthy

    # Check LLM (basic check - verify API key exists)
    try:
        components["llm"] = bool(settings.anthropic_api_key or settings.openai_api_key or settings.openrouter_api_key)
    except Exception:
        pass

    # Check Cohere (verify API key exists)
    try:
        components["cohere"] = bool(settings.cohere_api_key)
    except Exception:
        pass

    # Check R2 (verify credentials exist)
    try:
        r2_access = os.getenv("R2_ACCESS_KEY_ID")
        r2_secret = os.getenv("R2_SECRET_ACCESS_KEY")
        components["r2"] = bool(r2_access and r2_secret)
    except Exception:
        pass

    overall_status = "healthy" if all(components.values()) else "degraded"
    
    return HealthResponse(
        status=overall_status,
        version="2.0.0",
        timestamp=datetime.now(),
        components=components,
    )


@router.get("/production")
async def production_health():
    """
    Production health check with detailed metrics.
    
    Returns:
    - Circuit breaker status
    - Cache statistics
    - Configuration settings
    """
    from src.config.settings import settings as app_settings
    
    # Get cache stats
    cache = get_response_cache()
    cache_stats = cache.get_stats()
    
    # Get circuit breaker status
    breaker_status = get_all_breaker_status()
    
    return {
        "status": "ok",
        "version": "2.0.0",
        "timestamp": datetime.now().isoformat(),
        "production_settings": {
            "max_sources_for_extraction": app_settings.max_sources_for_extraction,
            "llm_concurrency_limit": app_settings.llm_concurrency_limit,
            "request_timeout_seconds": app_settings.request_timeout_seconds,
            "enable_response_cache": app_settings.enable_response_cache,
            "response_cache_ttl_seconds": app_settings.response_cache_ttl_seconds,
        },
        "cache": cache_stats,
        "circuit_breakers": breaker_status,
    }


@router.get("/ready")
async def readiness_check():
    """Kubernetes-style readiness probe."""
    return {"status": "ready"}


@router.get("/live")
async def liveness_check():
    """Kubernetes-style liveness probe."""
    return {"status": "live"}
