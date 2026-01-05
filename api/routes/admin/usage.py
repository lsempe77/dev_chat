"""
Admin Usage Stats Routes

Endpoints for persistent usage statistics and cost tracking from Supabase.
"""

import os
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from src.config.costs import MODEL_PRICING, calculate_cost
from src.utils.logging import get_logger
from src.utils.usage_logger import get_usage_logger

logger = get_logger(__name__)

router = APIRouter()


# =============================================================================
# Response Models
# =============================================================================

class DailyUsageStats(BaseModel):
    """Daily usage summary."""
    date: str
    total_queries: int
    total_input_tokens: int
    total_output_tokens: int
    total_cost_usd: float
    avg_latency_ms: float
    cache_hit_rate: float


class ModelUsageStats(BaseModel):
    """Per-model usage breakdown."""
    model: str
    query_count: int
    input_tokens: int
    output_tokens: int
    cost_usd: float
    avg_latency_ms: float


class UsageSummaryResponse(BaseModel):
    """Overall usage summary."""
    period_start: str
    period_end: str
    total_queries: int
    total_input_tokens: int
    total_output_tokens: int
    total_cost_usd: float
    avg_latency_ms: float
    cache_hit_rate: float
    daily_breakdown: List[DailyUsageStats]
    model_breakdown: List[ModelUsageStats]


class CostProjection(BaseModel):
    """Cost projection for budgeting."""
    current_daily_avg: float
    projected_monthly: float
    projected_annual: float
    days_in_sample: int


# =============================================================================
# Usage Stats Endpoints
# =============================================================================

@router.get("/usage/summary", response_model=UsageSummaryResponse)
async def get_usage_summary(
    days: int = Query(default=30, ge=1, le=365, description="Number of days to summarize"),
):
    """
    Get usage summary for the specified period.
    
    Aggregates data from usage_logs table in Supabase.
    """
    from ..dependencies import get_db_session, is_postgres_available
    
    if not is_postgres_available():
        raise HTTPException(status_code=503, detail="Database not available")
    
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)
    
    try:
        db = await get_db_session()
        if not db:
            raise HTTPException(status_code=503, detail="Could not get database session")
        
        async with db:
            from sqlalchemy import text
            
            # Get overall summary
            summary_sql = text("""
                SELECT 
                    COUNT(*) as total_queries,
                    COALESCE(SUM(input_tokens), 0) as total_input_tokens,
                    COALESCE(SUM(output_tokens), 0) as total_output_tokens,
                    COALESCE(SUM(cost_usd), 0) as total_cost_usd,
                    COALESCE(AVG(latency_ms), 0) as avg_latency_ms,
                    COALESCE(
                        SUM(CASE WHEN model = 'cache' THEN 1 ELSE 0 END)::float / 
                        NULLIF(COUNT(*), 0), 0
                    ) as cache_hit_rate
                FROM usage_logs
                WHERE created_at >= :start_date AND created_at <= :end_date
            """)
            
            result = await db.execute(summary_sql, {
                "start_date": start_date,
                "end_date": end_date,
            })
            summary = result.fetchone()
            
            # Get daily breakdown
            daily_sql = text("""
                SELECT 
                    DATE(created_at) as date,
                    COUNT(*) as total_queries,
                    COALESCE(SUM(input_tokens), 0) as total_input_tokens,
                    COALESCE(SUM(output_tokens), 0) as total_output_tokens,
                    COALESCE(SUM(cost_usd), 0) as total_cost_usd,
                    COALESCE(AVG(latency_ms), 0) as avg_latency_ms,
                    COALESCE(
                        SUM(CASE WHEN model = 'cache' THEN 1 ELSE 0 END)::float / 
                        NULLIF(COUNT(*), 0), 0
                    ) as cache_hit_rate
                FROM usage_logs
                WHERE created_at >= :start_date AND created_at <= :end_date
                GROUP BY DATE(created_at)
                ORDER BY date DESC
            """)
            
            daily_result = await db.execute(daily_sql, {
                "start_date": start_date,
                "end_date": end_date,
            })
            daily_rows = daily_result.fetchall()
            
            # Get model breakdown
            model_sql = text("""
                SELECT 
                    model,
                    COUNT(*) as query_count,
                    COALESCE(SUM(input_tokens), 0) as input_tokens,
                    COALESCE(SUM(output_tokens), 0) as output_tokens,
                    COALESCE(SUM(cost_usd), 0) as cost_usd,
                    COALESCE(AVG(latency_ms), 0) as avg_latency_ms
                FROM usage_logs
                WHERE created_at >= :start_date AND created_at <= :end_date
                  AND model != 'cache'
                GROUP BY model
                ORDER BY query_count DESC
            """)
            
            model_result = await db.execute(model_sql, {
                "start_date": start_date,
                "end_date": end_date,
            })
            model_rows = model_result.fetchall()
            
            # Handle case where no data exists
            if summary is None:
                return UsageSummaryResponse(
                    period_start=start_date.isoformat(),
                    period_end=end_date.isoformat(),
                    total_queries=0,
                    total_input_tokens=0,
                    total_output_tokens=0,
                    total_cost_usd=0.0,
                    avg_latency_ms=0.0,
                    cache_hit_rate=0.0,
                    daily_breakdown=[],
                    model_breakdown=[],
                )
            
            return UsageSummaryResponse(
                period_start=start_date.isoformat(),
                period_end=end_date.isoformat(),
                total_queries=summary.total_queries or 0,
                total_input_tokens=summary.total_input_tokens or 0,
                total_output_tokens=summary.total_output_tokens or 0,
                total_cost_usd=round(summary.total_cost_usd or 0, 4),
                avg_latency_ms=round(summary.avg_latency_ms or 0, 1),
                cache_hit_rate=round(summary.cache_hit_rate or 0, 4),
                daily_breakdown=[
                    DailyUsageStats(
                        date=str(row.date),
                        total_queries=row.total_queries,
                        total_input_tokens=row.total_input_tokens,
                        total_output_tokens=row.total_output_tokens,
                        total_cost_usd=round(row.total_cost_usd, 4),
                        avg_latency_ms=round(row.avg_latency_ms, 1),
                        cache_hit_rate=round(row.cache_hit_rate, 4),
                    )
                    for row in daily_rows
                ],
                model_breakdown=[
                    ModelUsageStats(
                        model=row.model,
                        query_count=row.query_count,
                        input_tokens=row.input_tokens,
                        output_tokens=row.output_tokens,
                        cost_usd=round(row.cost_usd, 4),
                        avg_latency_ms=round(row.avg_latency_ms, 1),
                    )
                    for row in model_rows
                ],
            )
            
    except Exception as e:
        logger.error(f"Error fetching usage summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/usage/costs", response_model=CostProjection)
async def get_cost_projection(
    sample_days: int = Query(default=7, ge=1, le=30, description="Days to sample for projection"),
):
    """
    Get cost projection based on recent usage.
    
    Uses last N days to project monthly and annual costs.
    """
    from ..dependencies import get_db_session, is_postgres_available
    
    if not is_postgres_available():
        raise HTTPException(status_code=503, detail="Database not available")
    
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=sample_days)
    
    try:
        db = await get_db_session()
        if not db:
            raise HTTPException(status_code=503, detail="Could not get database session")
        
        async with db:
            from sqlalchemy import text
            
            sql = text("""
                SELECT 
                    COALESCE(SUM(cost_usd), 0) as total_cost,
                    COUNT(DISTINCT DATE(created_at)) as days_with_data
                FROM usage_logs
                WHERE created_at >= :start_date AND created_at <= :end_date
                  AND model != 'cache'
            """)
            
            result = await db.execute(sql, {
                "start_date": start_date,
                "end_date": end_date,
            })
            row = result.fetchone()
            
            # Handle no data case
            if row is None:
                return CostProjection(
                    current_daily_avg=0.0,
                    projected_monthly=0.0,
                    projected_annual=0.0,
                    days_in_sample=0,
                )
            
            days_with_data = max(row.days_with_data or 1, 1)
            total_cost = row.total_cost or 0
            daily_avg = total_cost / days_with_data
            
            return CostProjection(
                current_daily_avg=round(daily_avg, 4),
                projected_monthly=round(daily_avg * 30, 2),
                projected_annual=round(daily_avg * 365, 2),
                days_in_sample=days_with_data,
            )
            
    except Exception as e:
        logger.error(f"Error fetching cost projection: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/usage/pricing")
async def get_model_pricing():
    """
    Get current model pricing configuration.
    
    Returns the cost per 1M tokens for each model.
    """
    return {
        model: {
            "input_per_1m": float(pricing.input_per_1m),
            "output_per_1m": float(pricing.output_per_1m),
            "provider": pricing.provider,
        }
        for model, pricing in MODEL_PRICING.items()
    }


@router.post("/usage/flush")
async def flush_usage_buffer():
    """
    Force flush any buffered usage events to database.
    
    Useful for testing or before shutdown.
    """
    try:
        usage_logger = get_usage_logger()
        await usage_logger.flush()
        return {"status": "ok", "message": "Buffer flushed successfully"}
    except Exception as e:
        logger.error(f"Error flushing usage buffer: {e}")
        raise HTTPException(status_code=500, detail=str(e))
