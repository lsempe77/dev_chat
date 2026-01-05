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


class AdminOverviewStats(BaseModel):
    """Overview stats for admin dashboard."""
    total_users: int
    total_rag_projects: int
    total_documents: int
    total_chunks: int
    total_queries: int
    total_cost_usd: float


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
    import os
    from supabase import create_client
    
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    
    if not supabase_url or not supabase_key:
        # Return empty response if Supabase not configured
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)
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
    
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)
    
    try:
        supabase = create_client(supabase_url, supabase_key)
        
        # Get all usage logs for the period
        result = supabase.table("usage_logs").select("*").gte(
            "created_at", start_date.isoformat()
        ).lte(
            "created_at", end_date.isoformat()
        ).execute()
        
        logs = result.data or []
        
        if not logs:
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
        
        # Calculate totals
        total_queries = len(logs)
        total_input = sum(log.get("input_tokens", 0) or 0 for log in logs)
        total_output = sum(log.get("output_tokens", 0) or 0 for log in logs)
        total_cost = sum(log.get("cost_usd", 0) or 0 for log in logs)
        latencies = [log.get("latency_ms", 0) or 0 for log in logs if log.get("latency_ms")]
        avg_latency = sum(latencies) / len(latencies) if latencies else 0
        cache_hits = sum(1 for log in logs if log.get("model") == "cache")
        cache_rate = cache_hits / total_queries if total_queries > 0 else 0
        
        # Daily breakdown
        daily_data = {}
        for log in logs:
            date_str = log.get("created_at", "")[:10]  # YYYY-MM-DD
            if date_str not in daily_data:
                daily_data[date_str] = {
                    "queries": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "cost_usd": 0,
                    "latencies": [],
                    "cache_hits": 0,
                }
            daily_data[date_str]["queries"] += 1
            daily_data[date_str]["input_tokens"] += log.get("input_tokens", 0) or 0
            daily_data[date_str]["output_tokens"] += log.get("output_tokens", 0) or 0
            daily_data[date_str]["cost_usd"] += log.get("cost_usd", 0) or 0
            if log.get("latency_ms"):
                daily_data[date_str]["latencies"].append(log["latency_ms"])
            if log.get("model") == "cache":
                daily_data[date_str]["cache_hits"] += 1
        
        daily_breakdown = [
            DailyUsageStats(
                date=date,
                total_queries=data["queries"],
                total_input_tokens=data["input_tokens"],
                total_output_tokens=data["output_tokens"],
                total_cost_usd=round(data["cost_usd"], 4),
                avg_latency_ms=round(sum(data["latencies"]) / len(data["latencies"]), 1) if data["latencies"] else 0,
                cache_hit_rate=round(data["cache_hits"] / data["queries"], 4) if data["queries"] > 0 else 0,
            )
            for date, data in sorted(daily_data.items(), reverse=True)
        ]
        
        # Model breakdown
        model_data = {}
        for log in logs:
            model = log.get("model", "unknown")
            if model == "cache":
                continue  # Skip cache entries
            if model not in model_data:
                model_data[model] = {
                    "count": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "cost_usd": 0,
                    "latencies": [],
                }
            model_data[model]["count"] += 1
            model_data[model]["input_tokens"] += log.get("input_tokens", 0) or 0
            model_data[model]["output_tokens"] += log.get("output_tokens", 0) or 0
            model_data[model]["cost_usd"] += log.get("cost_usd", 0) or 0
            if log.get("latency_ms"):
                model_data[model]["latencies"].append(log["latency_ms"])
        
        model_breakdown = [
            ModelUsageStats(
                model=model,
                query_count=data["count"],
                input_tokens=data["input_tokens"],
                output_tokens=data["output_tokens"],
                cost_usd=round(data["cost_usd"], 4),
                avg_latency_ms=round(sum(data["latencies"]) / len(data["latencies"]), 1) if data["latencies"] else 0,
            )
            for model, data in sorted(model_data.items(), key=lambda x: x[1]["count"], reverse=True)
        ]
        
        return UsageSummaryResponse(
            period_start=start_date.isoformat(),
            period_end=end_date.isoformat(),
            total_queries=total_queries,
            total_input_tokens=total_input,
            total_output_tokens=total_output,
            total_cost_usd=round(total_cost, 4),
            avg_latency_ms=round(avg_latency, 1),
            cache_hit_rate=round(cache_rate, 4),
            daily_breakdown=daily_breakdown,
            model_breakdown=model_breakdown,
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
    import os
    from supabase import create_client
    
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    
    if not supabase_url or not supabase_key:
        return CostProjection(
            current_daily_avg=0.0,
            projected_monthly=0.0,
            projected_annual=0.0,
            days_in_sample=0,
        )
    
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=sample_days)
    
    try:
        supabase = create_client(supabase_url, supabase_key)
        
        # Get usage logs for the period
        result = supabase.table("usage_logs").select("cost_usd, created_at, model").gte(
            "created_at", start_date.isoformat()
        ).lte(
            "created_at", end_date.isoformat()
        ).neq("model", "cache").execute()
        
        logs = result.data or []
        
        if not logs:
            return CostProjection(
                current_daily_avg=0.0,
                projected_monthly=0.0,
                projected_annual=0.0,
                days_in_sample=0,
            )
        
        # Calculate totals
        total_cost = sum(log.get("cost_usd", 0) or 0 for log in logs)
        days_with_data = len(set(log.get("created_at", "")[:10] for log in logs))
        days_with_data = max(days_with_data, 1)
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


@router.get("/overview", response_model=AdminOverviewStats)
async def get_admin_overview():
    """
    Get overview statistics for the admin dashboard.
    
    Returns total counts across all users and projects.
    Uses Supabase REST API directly (not SQLAlchemy).
    """
    try:
        from supabase import create_client
        url = os.environ.get("SUPABASE_URL", "")
        key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
        
        if not url or not key:
            raise HTTPException(status_code=503, detail="Supabase not configured")
        
        supabase = create_client(url, key)
        
        # Get RAG projects and count distinct users
        projects_result = supabase.table("rag_projects").select("id, user_id").execute()
        rag_count = len(projects_result.data) if projects_result.data else 0
        user_ids = set(p.get("user_id") for p in (projects_result.data or []) if p.get("user_id"))
        user_count = len(user_ids)
        
        # Get document count and total chunks
        docs_result = supabase.table("documents").select("id, chunk_count", count="exact").execute()
        doc_count = docs_result.count or 0
        chunk_count = sum(d.get("chunk_count", 0) or 0 for d in (docs_result.data or []))
        
        # Get usage totals (if usage_logs exists)
        try:
            usage_result = supabase.table("usage_logs").select("id, cost_usd", count="exact").execute()
            query_count = usage_result.count or 0
            total_cost = sum(float(u.get("cost_usd", 0) or 0) for u in (usage_result.data or []))
        except Exception:
            query_count = 0
            total_cost = 0.0
        
        return AdminOverviewStats(
            total_users=user_count,
            total_rag_projects=rag_count,
            total_documents=doc_count,
            total_chunks=chunk_count,
            total_queries=query_count,
            total_cost_usd=total_cost,
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching admin overview: {e}")
        raise HTTPException(status_code=500, detail=str(e))
