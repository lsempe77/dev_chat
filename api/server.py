"""
DevChat v2.0 SOTA - FastAPI Server

Main application entry point.
"""

import asyncio
import os
from contextlib import asynccontextmanager, suppress
from datetime import datetime

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.qdrant_status import warm_up_qdrant_connection
from api.routes import admin_router, api_router, chat_router, health_router, router
from api.routes.rags import router as rags_router
from api.routes.zotero import router as zotero_router
from api.routes.extraction import router as extraction_router
from src.config.settings import settings

# Note: Routes are now organized in api/routes/ package:
# - api/routes/health.py    - Health check endpoints
# - api/routes/chat.py      - Chat/streaming endpoints  
# - api/routes/api.py       - Frontend API (query, compare, suggest)
# - api/routes/admin.py     - Admin dashboard endpoints
# - api/routes/dependencies.py - Shared singletons and utilities
from src.utils.logging import get_logger, setup_logging

# Setup logging
setup_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    logger.info("🚀 DevChat v2.0 SOTA starting up...")
    logger.info(f"Environment: {settings.environment.value}")
    logger.info(f"LLM Provider: {settings.llm_provider.value}")
    logger.info(f"Fast Model: {settings.llm_fast_model}")
    logger.info(f"Reasoning Model: {settings.llm_reasoning_model}")
    logger.info(f"Embedding Model: {settings.embedding_model}")
    logger.info(f"Hybrid Search: {'enabled' if settings.hybrid_enabled else 'disabled'}")
    logger.info(f"Reranking: {'enabled' if settings.rerank_enabled else 'disabled'}")

    # Initialize PostgreSQL if DATABASE_URL is set
    db_url = os.getenv("DATABASE_URL")
    if db_url:
        try:
            logger.info(f"Initializing PostgreSQL: {db_url.split('@')[-1] if '@' in db_url else 'configured'}")
            from src.database.connection import init_database, create_tables
            engine, session = init_database()
            if engine and session:
                await create_tables()
                logger.info("✅ PostgreSQL metadata store initialized successfully")
            else:
                logger.warning("⚠️ init_database returned None - check DATABASE_URL format")
        except Exception as e:
            import traceback
            logger.error(f"⚠️ PostgreSQL init failed: {e}")
            logger.error(traceback.format_exc())
    else:
        logger.info("ℹ️ DATABASE_URL not set - using Qdrant for metadata")

    warmup_task = asyncio.create_task(warm_up_qdrant_connection())

    yield

    # Shutdown
    warmup_task.cancel()
    with suppress(asyncio.CancelledError):
        await warmup_task
    
    # Close database connections
    if os.getenv("DATABASE_URL"):
        try:
            from src.database.connection import close_database
            await close_database()
        except Exception:
            pass
    
    logger.info("👋 DevChat v2.0 SOTA shutting down...")


# Create FastAPI app
app = FastAPI(
    title="DevChat v2.0 SOTA",
    description="AI-powered assistant for 3ie Development Evidence Portal",
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request timeout middleware
@app.middleware("http")
async def timeout_middleware(request: Request, call_next):
    """Add timeout to requests to prevent hanging connections."""
    import asyncio
    
    # Skip timeout for health checks and admin endpoints
    skip_paths = ["/health", "/admin", "/docs", "/redoc", "/openapi.json"]
    if any(request.url.path.startswith(p) for p in skip_paths):
        return await call_next(request)
    
    try:
        # Use configurable timeout from settings
        return await asyncio.wait_for(
            call_next(request),
            timeout=settings.request_timeout_seconds
        )
    except asyncio.TimeoutError:
        logger.error(
            f"Request timeout after {settings.request_timeout_seconds}s: "
            f"{request.method} {request.url.path}"
        )
        return JSONResponse(
            status_code=504,
            content={
                "error": "gateway_timeout",
                "message": f"Request timed out after {settings.request_timeout_seconds} seconds",
                "suggestion": "Try a simpler query or reduce the number of studies",
                "timestamp": datetime.now().isoformat(),
            },
        )


# Request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all requests with timing."""
    import time
    
    start_time = time.time()
    
    # Process request
    response = await call_next(request)
    
    # Calculate duration
    duration_ms = (time.time() - start_time) * 1000
    
    # Log (skip health checks for less noise)
    if not request.url.path.startswith("/health"):
        logger.info(
            f"{request.method} {request.url.path} "
            f"→ {response.status_code} ({duration_ms:.0f}ms)"
        )
    
    # Add timing header
    response.headers["X-Response-Time-Ms"] = str(int(duration_ms))
    
    return response


# Exception handlers
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Handle uncaught exceptions."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_server_error",
            "message": "An unexpected error occurred",
            "detail": str(exc) if not settings.is_production else None,
            "timestamp": datetime.now().isoformat(),
        },
    )


# Include routers
app.include_router(router)
app.include_router(health_router)
app.include_router(chat_router)
app.include_router(admin_router)
app.include_router(api_router)  # Frontend API endpoints
app.include_router(rags_router)  # Multi-tenant RAG project management
app.include_router(zotero_router)  # Zotero integration
app.include_router(extraction_router)  # Extracted effect sizes for evidence synthesis


# Simple health endpoint that doesn't collide with the richer /health response
# Used by Railway healthcheck to avoid cold-start dependency checks
@app.get("/health/ping", include_in_schema=False)
async def simple_health():
    """Lightweight health check for platform probes."""
    return {"status": "ok", "service": "devchat-api", "version": "2.0.0"}


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "name": "DevChat v2.0 SOTA",
        "version": "2.0.0",
        "description": "AI-powered assistant for 3ie Development Evidence Portal",
        "docs": "/docs",
        "health": "/health",
        "endpoints": {
            "chat": "POST /chat",
            "stream": "POST /chat/stream",
            "metrics": "GET /admin/metrics",
        },
    }


# Run with: uvicorn api.server:app --reload
if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "api.server:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=not settings.is_production,
        log_level="info",
    )
