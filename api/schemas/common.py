"""
DevChat v2.0 SOTA - Common Schema Models

Base models, health checks, and error responses.
"""

from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


# =============================================================================
# Health & System Models
# =============================================================================

class HealthResponse(BaseModel):
    """Health check response."""
    
    status: str = Field(description="Service status")
    version: str = Field(description="API version")
    timestamp: datetime = Field(description="Current timestamp")
    
    # Component health
    components: Dict[str, bool] = Field(
        description="Health status of components"
    )


class MetricsResponse(BaseModel):
    """Metrics summary response."""
    
    total_queries: int
    latency: Dict[str, float]
    query_types: Dict[str, int]
    error_rate_percent: float
    tokens: Dict[str, int]


class ErrorResponse(BaseModel):
    """Error response."""
    
    error: str = Field(description="Error type")
    message: str = Field(description="Error message")
    detail: Optional[str] = Field(default=None, description="Additional details")
    timestamp: datetime = Field(default_factory=datetime.now)


class TimingInfo(BaseModel):
    """Timing breakdown for a request."""
    
    query_ms: float = Field(description="Query processing time")
    retrieval_ms: float = Field(description="Retrieval time")
    rerank_ms: float = Field(description="Reranking time")
    synthesis_ms: float = Field(description="LLM synthesis time")
    total_ms: float = Field(description="Total request time")


class CollectionInfo(BaseModel):
    """Information about a vector collection."""
    
    name: str
    points_count: int
    vectors_count: int
    status: str


class ServiceConnection(BaseModel):
    """Status of an external service connection."""
    name: str
    status: str  # "connected", "disconnected", "error"
    details: Optional[str] = None
    latency_ms: Optional[float] = None
