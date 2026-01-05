"""
Admin Quality Endpoints

Provides endpoints for:
- Running evaluation suite
- Viewing evaluation history
- Getting recent query quality logs
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field

from src.config.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/quality", tags=["Admin Quality"])

# ============================================================================
# Pydantic Models
# ============================================================================

class EvaluationMetrics(BaseModel):
    """Quality metrics from an evaluation run."""
    faithfulness: float = Field(ge=0, le=1)
    citation_recall: float = Field(ge=0, le=1)
    citation_precision: float = Field(ge=0, le=1)
    overall_score: float = Field(ge=0, le=1)


class EvaluationRun(BaseModel):
    """A single evaluation run result."""
    id: str
    run_type: str
    evaluator: str
    collection_name: Optional[str] = None
    metrics: EvaluationMetrics
    num_queries: int
    num_successful: int
    avg_latency_ms: Optional[float] = None
    started_at: str
    completed_at: Optional[str] = None
    triggered_by: Optional[str] = None


class EvaluationHistory(BaseModel):
    """Response for evaluation history endpoint."""
    runs: List[EvaluationRun]
    summary: dict


class QueryQualityLog(BaseModel):
    """A logged query with quality metrics."""
    id: str
    query: str
    answer_preview: Optional[str] = None
    rag_project_id: Optional[str] = None
    num_sources: int = 0
    num_citations: int = 0
    faithfulness: Optional[float] = None
    citation_recall: Optional[float] = None
    citation_precision: Optional[float] = None
    was_sampled: bool = False
    latency_ms: Optional[float] = None
    created_at: str


class RunEvaluationRequest(BaseModel):
    """Request to run evaluation suite."""
    evaluator: str = Field(default="minicheck", description="Evaluator to use: minicheck, reliable")
    collection_name: Optional[str] = Field(default=None, description="Optional RAG collection to test")
    num_queries: int = Field(default=5, ge=1, le=20, description="Number of test queries to run")


class RunEvaluationResponse(BaseModel):
    """Response from starting an evaluation run."""
    run_id: str
    status: str
    message: str


class LatestMetricsResponse(BaseModel):
    """Response with latest quality metrics."""
    metrics: Optional[EvaluationMetrics] = None
    last_run: Optional[str] = None
    targets: dict
    status: str


# ============================================================================
# Helper Functions
# ============================================================================

def get_supabase():
    """Get Supabase client."""
    try:
        from supabase import create_client
        return create_client(settings.supabase_url, settings.supabase_service_role_key)
    except Exception as e:
        logger.error(f"Failed to connect to Supabase: {e}")
        return None


async def run_evaluation_task(run_id: str, evaluator: str, collection_name: Optional[str], num_queries: int):
    """
    Background task to run evaluation suite.
    
    This runs the MiniCheck or Reliable evaluator on the test cases
    and stores results in the database.
    """
    supabase = get_supabase()
    if not supabase:
        logger.error(f"Cannot run evaluation {run_id}: No database connection")
        return
    
    started_at = datetime.utcnow()
    results = {
        "queries": [],
        "errors": []
    }
    
    try:
        # Load test cases
        import os
        test_cases_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "evaluation", "test_cases.json")
        
        if not os.path.exists(test_cases_path):
            # Try alternative path
            test_cases_path = "evaluation/test_cases.json"
        
        with open(test_cases_path, "r") as f:
            test_data = json.load(f)
            test_cases = test_data.get("test_cases", [])[:num_queries]
        
        if not test_cases:
            raise ValueError("No test cases found")
        
        # Import evaluator and agent
        from src.agents.devchat_agent import DevChatAgent
        from src.retrieval.settings import SearchSettings
        
        # Use default graduation collection if not specified
        project_id = collection_name or "0816e8d3-ab23-417c-bf3f-e45531411c73"
        
        agent = DevChatAgent(project_id=project_id)
        search_settings = SearchSettings(max_studies=5, use_claim_ledger=True)
        
        # Select evaluator
        if evaluator == "minicheck":
            from evaluation.minicheck_evaluator import MiniCheckEvaluator
            eval_instance = MiniCheckEvaluator(backend='api', api_model='openai/gpt-4o-mini')
        else:
            from evaluation.reliable_evaluator import ReliableEvaluator
            eval_instance = ReliableEvaluator()
        
        # Run queries and evaluate
        total_faithfulness = 0
        total_recall = 0
        total_precision = 0
        successful = 0
        
        for tc in test_cases:
            query = tc.get("question", tc.get("query", ""))
            if not query:
                continue
                
            try:
                import time
                query_start = time.time()
                
                # Get response from agent
                response = await agent.chat(query, search_settings)
                
                query_latency = (time.time() - query_start) * 1000
                
                # Evaluate response
                if evaluator == "minicheck":
                    eval_result = await eval_instance.evaluate(
                        query=query,
                        answer=response.answer,
                        contexts=[s.text for s in response.sources],
                        citations=response.citations
                    )
                    
                    results["queries"].append({
                        "query": query[:50],
                        "faithfulness": eval_result.faithfulness,
                        "citation_recall": eval_result.citation_recall,
                        "citation_precision": eval_result.citation_precision,
                        "latency_ms": query_latency
                    })
                    
                    total_faithfulness += eval_result.faithfulness
                    total_recall += eval_result.citation_recall
                    total_precision += eval_result.citation_precision
                else:
                    eval_result = await eval_instance.evaluate(
                        query=query,
                        answer=response.answer,
                        contexts=[s.text for s in response.sources],
                        citations=response.citations
                    )
                    
                    results["queries"].append({
                        "query": query[:50],
                        "faithfulness": eval_result.faithfulness,
                        "citation_accuracy": eval_result.citation_accuracy,
                        "latency_ms": query_latency
                    })
                    
                    total_faithfulness += eval_result.faithfulness
                    total_recall += eval_result.citation_accuracy
                    total_precision += eval_result.citation_accuracy
                
                successful += 1
                
            except Exception as e:
                logger.error(f"Error evaluating query '{query[:30]}...': {e}")
                results["errors"].append({"query": query[:50], "error": str(e)})
        
        # Calculate averages
        n = max(successful, 1)
        avg_faithfulness = total_faithfulness / n
        avg_recall = total_recall / n
        avg_precision = total_precision / n
        overall = (avg_faithfulness + avg_recall + avg_precision) / 3
        
        # Calculate average latency
        latencies = [q.get("latency_ms", 0) for q in results["queries"] if q.get("latency_ms")]
        avg_latency = sum(latencies) / len(latencies) if latencies else None
        
        # Update database with results
        completed_at = datetime.utcnow()
        
        supabase.table("evaluation_runs").update({
            "faithfulness": avg_faithfulness,
            "citation_recall": avg_recall,
            "citation_precision": avg_precision,
            "overall_score": overall,
            "num_successful": successful,
            "avg_latency_ms": avg_latency,
            "details": results,
            "completed_at": completed_at.isoformat()
        }).eq("id", run_id).execute()
        
        logger.info(f"Evaluation {run_id} completed: faithfulness={avg_faithfulness:.3f}, recall={avg_recall:.3f}, precision={avg_precision:.3f}")
        
    except Exception as e:
        logger.error(f"Evaluation {run_id} failed: {e}")
        # Update with error
        supabase.table("evaluation_runs").update({
            "details": {"error": str(e), **results},
            "completed_at": datetime.utcnow().isoformat()
        }).eq("id", run_id).execute()


# ============================================================================
# Endpoints
# ============================================================================

@router.get("/metrics", response_model=LatestMetricsResponse)
async def get_latest_metrics():
    """
    Get latest quality metrics from most recent evaluation run.
    
    Returns current metrics vs targets.
    """
    supabase = get_supabase()
    
    targets = {
        "faithfulness": 0.70,
        "citation_recall": 0.70,
        "citation_precision": 0.70,
        "overall_score": 0.80
    }
    
    if not supabase:
        return LatestMetricsResponse(
            metrics=None,
            last_run=None,
            targets=targets,
            status="no_database"
        )
    
    try:
        # Get most recent completed run
        result = supabase.table("evaluation_runs").select("*").eq(
            "evaluator", "minicheck"
        ).not_.is_("completed_at", "null").order(
            "created_at", desc=True
        ).limit(1).execute()
        
        if not result.data:
            return LatestMetricsResponse(
                metrics=None,
                last_run=None,
                targets=targets,
                status="no_runs"
            )
        
        run = result.data[0]
        
        return LatestMetricsResponse(
            metrics=EvaluationMetrics(
                faithfulness=run.get("faithfulness", 0),
                citation_recall=run.get("citation_recall", 0),
                citation_precision=run.get("citation_precision", 0),
                overall_score=run.get("overall_score", 0)
            ),
            last_run=run.get("completed_at"),
            targets=targets,
            status="ok"
        )
        
    except Exception as e:
        logger.error(f"Error fetching metrics: {e}")
        return LatestMetricsResponse(
            metrics=None,
            last_run=None,
            targets=targets,
            status=f"error: {str(e)}"
        )


@router.post("/run", response_model=RunEvaluationResponse)
async def run_evaluation(
    request: RunEvaluationRequest,
    background_tasks: BackgroundTasks
):
    """
    Start a new evaluation run.
    
    This runs in the background and results can be fetched from /history.
    """
    supabase = get_supabase()
    
    if not supabase:
        raise HTTPException(status_code=503, detail="Database not available")
    
    try:
        # Create run record
        run_data = {
            "run_type": "manual",
            "evaluator": request.evaluator,
            "collection_name": request.collection_name,
            "num_queries": request.num_queries,
            "triggered_by": "admin",
            "started_at": datetime.utcnow().isoformat()
        }
        
        result = supabase.table("evaluation_runs").insert(run_data).execute()
        
        if not result.data:
            raise HTTPException(status_code=500, detail="Failed to create evaluation run")
        
        run_id = result.data[0]["id"]
        
        # Start background task
        background_tasks.add_task(
            run_evaluation_task,
            run_id,
            request.evaluator,
            request.collection_name,
            request.num_queries
        )
        
        return RunEvaluationResponse(
            run_id=run_id,
            status="started",
            message=f"Evaluation started with {request.num_queries} queries using {request.evaluator}"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting evaluation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history", response_model=EvaluationHistory)
async def get_evaluation_history(
    limit: int = 10,
    evaluator: Optional[str] = None
):
    """
    Get evaluation run history.
    
    Returns recent runs with their metrics.
    """
    supabase = get_supabase()
    
    if not supabase:
        return EvaluationHistory(runs=[], summary={})
    
    try:
        query = supabase.table("evaluation_runs").select("*").order("created_at", desc=True).limit(limit)
        
        if evaluator:
            query = query.eq("evaluator", evaluator)
        
        result = query.execute()
        
        runs = []
        for row in result.data or []:
            runs.append(EvaluationRun(
                id=row["id"],
                run_type=row.get("run_type", "manual"),
                evaluator=row.get("evaluator", "unknown"),
                collection_name=row.get("collection_name"),
                metrics=EvaluationMetrics(
                    faithfulness=row.get("faithfulness", 0) or 0,
                    citation_recall=row.get("citation_recall", 0) or 0,
                    citation_precision=row.get("citation_precision", 0) or 0,
                    overall_score=row.get("overall_score", 0) or 0
                ),
                num_queries=row.get("num_queries", 0) or 0,
                num_successful=row.get("num_successful", 0) or 0,
                avg_latency_ms=row.get("avg_latency_ms"),
                started_at=row.get("started_at", ""),
                completed_at=row.get("completed_at"),
                triggered_by=row.get("triggered_by")
            ))
        
        # Calculate summary stats
        completed_runs = [r for r in runs if r.completed_at]
        summary = {}
        if completed_runs:
            summary = {
                "total_runs": len(completed_runs),
                "avg_faithfulness": sum(r.metrics.faithfulness for r in completed_runs) / len(completed_runs),
                "avg_recall": sum(r.metrics.citation_recall for r in completed_runs) / len(completed_runs),
                "avg_precision": sum(r.metrics.citation_precision for r in completed_runs) / len(completed_runs),
                "latest_run": completed_runs[0].completed_at if completed_runs else None
            }
        
        return EvaluationHistory(runs=runs, summary=summary)
        
    except Exception as e:
        logger.error(f"Error fetching history: {e}")
        return EvaluationHistory(runs=[], summary={"error": str(e)})


@router.get("/run/{run_id}")
async def get_evaluation_run(run_id: str):
    """
    Get details of a specific evaluation run.
    """
    supabase = get_supabase()
    
    if not supabase:
        raise HTTPException(status_code=503, detail="Database not available")
    
    try:
        result = supabase.table("evaluation_runs").select("*").eq("id", run_id).execute()
        
        if not result.data:
            raise HTTPException(status_code=404, detail="Evaluation run not found")
        
        return result.data[0]
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching run {run_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/recent-queries")
async def get_recent_queries(
    limit: int = 20,
    sampled_only: bool = False
):
    """
    Get recent queries with quality metrics (if sampled).
    
    This shows recent production queries and their quality scores
    for those that were evaluated.
    """
    supabase = get_supabase()
    
    if not supabase:
        return {"queries": [], "total": 0}
    
    try:
        query = supabase.table("query_quality_logs").select("*").order("created_at", desc=True).limit(limit)
        
        if sampled_only:
            query = query.eq("was_sampled", True)
        
        result = query.execute()
        
        queries = []
        for row in result.data or []:
            queries.append(QueryQualityLog(
                id=row["id"],
                query=row.get("query", ""),
                answer_preview=row.get("answer_preview"),
                rag_project_id=row.get("rag_project_id"),
                num_sources=row.get("num_sources", 0) or 0,
                num_citations=row.get("num_citations", 0) or 0,
                faithfulness=row.get("faithfulness"),
                citation_recall=row.get("citation_recall"),
                citation_precision=row.get("citation_precision"),
                was_sampled=row.get("was_sampled", False),
                latency_ms=row.get("latency_ms"),
                created_at=row.get("created_at", "")
            ))
        
        return {"queries": queries, "total": len(queries)}
        
    except Exception as e:
        logger.error(f"Error fetching recent queries: {e}")
        return {"queries": [], "total": 0, "error": str(e)}
