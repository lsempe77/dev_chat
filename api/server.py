"""
DevChat v2.0 SOTA - FastAPI Server

Main application entry point.
"""

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.routes import admin_router, api_router, chat_router, health_router, router
from src.config.settings import settings
from src.utils.logging import get_logger, setup_logging

# Setup logging
setup_logging()
logger = get_logger(__name__)


async def initialize_qdrant_connection():
    """
    Initialize Qdrant connection in background.
    
    This warms up the connection so health checks don't block.
    """
    from api.routes import get_indexer, update_qdrant_status
    
    try:
        logger.info("🔌 Initializing Qdrant connection in background...")
        loop = asyncio.get_event_loop()
        
        def _connect():
            indexer = get_indexer()
            # Verify connection by getting collections
            collections = indexer.client.get_collections()
            return True
        
        # Run with timeout
        result = await asyncio.wait_for(
            loop.run_in_executor(None, _connect),
            timeout=30.0  # Allow up to 30 seconds on cold start
        )
        
        # Update cache
        update_qdrant_status(True, "Connected on startup")
        logger.info("✅ Qdrant connection initialized successfully")
        
    except asyncio.TimeoutError:
        logger.warning("⚠️ Qdrant connection timed out during startup")
        update_qdrant_status(False, "Connection timeout during startup")
    except Exception as e:
        logger.error(f"❌ Qdrant connection failed during startup: {e}")
        update_qdrant_status(False, str(e)[:100])


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
    
    # Initialize Qdrant connection in background (don't block startup)
    asyncio.create_task(initialize_qdrant_connection())
    
    yield
    
    # Shutdown
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


# Simple health endpoint that doesn't require any external connections
# This is used by Railway healthcheck
@app.get("/health")
async def simple_health():
    """Simple health check for Railway."""
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
