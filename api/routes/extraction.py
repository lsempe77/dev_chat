"""
Extraction API Routes
=====================

API endpoints for managing and querying extracted effect estimates.
Provides quantitative evidence to the chatbot for synthesis responses.

Endpoints:
    GET  /extraction/studies/{study_id}/effects - Get effects for a study
    GET  /extraction/effects - Query effects with filters
    POST /extraction/effects/bulk - Bulk upload effects
    GET  /extraction/outcomes/summary - Get cross-study outcome summaries
    GET  /extraction/chatbot-context - Get effect context for chatbot prompts
"""

from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from src.auth import AuthenticatedUser, get_current_user, get_supabase_client, get_optional_user
from src.utils.logging import get_logger
from api.schemas.extraction import (
    ExtractedEstimate,
    ExtractedEstimateCreate,
    BulkUploadRequest,
    BulkUploadResponse,
    EstimateQuery,
    EstimateQueryResponse,
    StudyEffectSummary,
    OutcomeMetaAnalysis,
    EvidencePanelData,
    QuantitativeContext,
    ChatbotEffectContext,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/extraction", tags=["Extraction"])

# Table name in Supabase
ESTIMATES_TABLE = "extracted_estimates"


# =============================================================================
# Helper Functions
# =============================================================================

def row_to_estimate(row: Dict[str, Any]) -> ExtractedEstimate:
    """Convert a database row to an ExtractedEstimate model."""
    return ExtractedEstimate(**row)


def build_query_filters(query: EstimateQuery, supabase_query):
    """Apply filters to a Supabase query."""
    if query.study_ids:
        supabase_query = supabase_query.in_("study_id", query.study_ids)
    
    if query.outcome_categories:
        supabase_query = supabase_query.in_("outcome_category", query.outcome_categories)
    
    if query.countries:
        supabase_query = supabase_query.in_("country", query.countries)
    
    if query.study_designs:
        supabase_query = supabase_query.in_("study_design", query.study_designs)
    
    if query.min_year:
        supabase_query = supabase_query.gte("year", query.min_year)
    
    if query.max_year:
        supabase_query = supabase_query.lte("year", query.max_year)
    
    if query.main_effects_only:
        supabase_query = supabase_query.eq("is_main_effect", True)
    
    if query.has_effect_size:
        supabase_query = supabase_query.not_.is_("cohens_d", "null")
    
    return supabase_query


# =============================================================================
# Study-Level Endpoints
# =============================================================================

@router.get("/studies/{study_id}/effects", response_model=List[ExtractedEstimate])
async def get_study_effects(
    study_id: str,
    main_effects_only: bool = Query(False, description="Only return main effects"),
    user: Optional[AuthenticatedUser] = Depends(get_optional_user),
):
    """
    Get all extracted effects for a specific study.
    
    Args:
        study_id: Study identifier
        main_effects_only: Filter to main effects only
        
    Returns:
        List of extracted estimates for the study
    """
    client = get_supabase_client()
    
    try:
        query = client.table(ESTIMATES_TABLE).select("*").eq("study_id", study_id)
        
        if main_effects_only:
            query = query.eq("is_main_effect", True)
        
        result = query.execute()
        
        if not result.data:
            return []
        
        return [row_to_estimate(row) for row in result.data]
    
    except Exception as e:
        logger.error(f"Error fetching effects for study {study_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching study effects: {str(e)}"
        )


@router.get("/studies/{study_id}/summary", response_model=StudyEffectSummary)
async def get_study_summary(
    study_id: str,
    user: Optional[AuthenticatedUser] = Depends(get_optional_user),
):
    """
    Get aggregated summary of effects for a study.
    
    Args:
        study_id: Study identifier
        
    Returns:
        Aggregated statistics for the study
    """
    client = get_supabase_client()
    
    try:
        result = client.table(ESTIMATES_TABLE).select("*").eq("study_id", study_id).execute()
        
        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No effects found for study: {study_id}"
            )
        
        rows = result.data
        first_row = rows[0]
        
        # Calculate aggregates
        cohens_d_values = [r["cohens_d"] for r in rows if r.get("cohens_d") is not None]
        hedges_g_values = [r["hedges_g"] for r in rows if r.get("hedges_g") is not None]
        p_values = [r["p_value"] for r in rows if r.get("p_value") is not None]
        outcome_cats = list(set(r["outcome_category"] for r in rows if r.get("outcome_category")))
        
        return StudyEffectSummary(
            study_id=study_id,
            authors=first_row.get("authors"),
            year=first_row.get("year"),
            country=first_row.get("country"),
            study_design=first_row.get("study_design"),
            total_effects=len(rows),
            main_effects=sum(1 for r in rows if r.get("is_main_effect")),
            outcome_categories=outcome_cats,
            avg_cohens_d=sum(cohens_d_values) / len(cohens_d_values) if cohens_d_values else None,
            avg_hedges_g=sum(hedges_g_values) / len(hedges_g_values) if hedges_g_values else None,
            min_p_value=min(p_values) if p_values else None,
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching summary for study {study_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching study summary: {str(e)}"
        )


# =============================================================================
# Query Endpoints
# =============================================================================

@router.post("/effects/query", response_model=EstimateQueryResponse)
async def query_effects(
    query: EstimateQuery,
    user: Optional[AuthenticatedUser] = Depends(get_optional_user),
):
    """
    Query extracted effects with filters.
    
    Args:
        query: Filter criteria
        
    Returns:
        Matching effects with pagination info
    """
    client = get_supabase_client()
    
    try:
        # Build query with filters
        supabase_query = client.table(ESTIMATES_TABLE).select("*", count="exact")
        supabase_query = build_query_filters(query, supabase_query)
        
        # Apply pagination
        supabase_query = supabase_query.range(query.offset, query.offset + query.limit - 1)
        
        result = supabase_query.execute()
        
        estimates = [row_to_estimate(row) for row in result.data] if result.data else []
        
        return EstimateQueryResponse(
            estimates=estimates,
            total=result.count or 0,
            limit=query.limit,
            offset=query.offset,
        )
    
    except Exception as e:
        logger.error(f"Error querying effects: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error querying effects: {str(e)}"
        )


@router.get("/effects", response_model=EstimateQueryResponse)
async def list_effects(
    study_ids: Optional[str] = Query(None, description="Comma-separated study IDs"),
    outcome_categories: Optional[str] = Query(None, description="Comma-separated outcome categories"),
    countries: Optional[str] = Query(None, description="Comma-separated countries"),
    study_designs: Optional[str] = Query(None, description="Comma-separated study designs"),
    min_year: Optional[int] = Query(None, description="Minimum publication year"),
    max_year: Optional[int] = Query(None, description="Maximum publication year"),
    main_effects_only: bool = Query(False, description="Only main effects"),
    has_effect_size: bool = Query(False, description="Only with Cohen's d"),
    limit: int = Query(100, le=1000, description="Max results"),
    offset: int = Query(0, description="Offset for pagination"),
    user: Optional[AuthenticatedUser] = Depends(get_optional_user),
):
    """
    List effects with GET query parameters.
    
    Convenience endpoint that wraps query_effects for simple filtering.
    """
    query = EstimateQuery(
        study_ids=study_ids.split(",") if study_ids else None,
        outcome_categories=outcome_categories.split(",") if outcome_categories else None,
        countries=countries.split(",") if countries else None,
        study_designs=study_designs.split(",") if study_designs else None,
        min_year=min_year,
        max_year=max_year,
        main_effects_only=main_effects_only,
        has_effect_size=has_effect_size,
        limit=limit,
        offset=offset,
    )
    return await query_effects(query, user)


# =============================================================================
# Bulk Operations
# =============================================================================

@router.post("/effects/bulk", response_model=BulkUploadResponse)
async def bulk_upload_effects(
    request: BulkUploadRequest,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Bulk upload extracted effects.
    
    Requires authentication. Supports upsert mode to update existing records.
    
    Args:
        request: List of estimates to upload
        
    Returns:
        Upload statistics
    """
    client = get_supabase_client()
    
    inserted = 0
    updated = 0
    errors = []
    
    try:
        for estimate in request.estimates:
            try:
                record = estimate.model_dump(exclude_none=True)
                
                if request.upsert:
                    # Check if exists
                    existing = (
                        client.table(ESTIMATES_TABLE)
                        .select("id")
                        .eq("study_id", estimate.study_id)
                        .eq("outcome_name", estimate.outcome_name)
                        .eq("treatment_arm", estimate.treatment_arm)
                        .maybeSingle()
                        .execute()
                    )
                    
                    if existing.data:
                        # Update
                        client.table(ESTIMATES_TABLE).update(record).eq("id", existing.data["id"]).execute()
                        updated += 1
                    else:
                        # Insert
                        client.table(ESTIMATES_TABLE).insert(record).execute()
                        inserted += 1
                else:
                    # Insert only
                    client.table(ESTIMATES_TABLE).insert(record).execute()
                    inserted += 1
                    
            except Exception as e:
                errors.append({
                    "study_id": estimate.study_id,
                    "outcome_name": estimate.outcome_name,
                    "error": str(e),
                })
        
        return BulkUploadResponse(
            success=len(errors) == 0,
            inserted=inserted,
            updated=updated,
            errors=errors,
        )
    
    except Exception as e:
        logger.error(f"Bulk upload error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Bulk upload failed: {str(e)}"
        )


# =============================================================================
# Aggregation Endpoints (for Evidence Panel)
# =============================================================================

@router.get("/outcomes/summary", response_model=List[OutcomeMetaAnalysis])
async def get_outcome_summaries(
    study_ids: Optional[str] = Query(None, description="Limit to specific studies (comma-separated)"),
    user: Optional[AuthenticatedUser] = Depends(get_optional_user),
):
    """
    Get cross-study aggregation by outcome category.
    
    Returns pooled effect sizes for meta-analysis context.
    """
    client = get_supabase_client()
    
    try:
        # Get all estimates with effect sizes
        query = client.table(ESTIMATES_TABLE).select("*").not_.is_("cohens_d", "null")
        
        if study_ids:
            query = query.in_("study_id", study_ids.split(","))
        
        result = query.execute()
        
        if not result.data:
            return []
        
        # Group by outcome category
        from collections import defaultdict
        import statistics
        
        by_category = defaultdict(list)
        for row in result.data:
            cat = row.get("outcome_category") or "Other"
            by_category[cat].append(row)
        
        summaries = []
        for cat, rows in by_category.items():
            cohens_d_values = [r["cohens_d"] for r in rows if r.get("cohens_d") is not None]
            hedges_g_values = [r["hedges_g"] for r in rows if r.get("hedges_g") is not None]
            study_ids_in_cat = list(set(r["study_id"] for r in rows))
            
            summaries.append(OutcomeMetaAnalysis(
                outcome_category=cat,
                n_studies=len(study_ids_in_cat),
                n_estimates=len(rows),
                pooled_cohens_d=sum(cohens_d_values) / len(cohens_d_values) if cohens_d_values else None,
                pooled_hedges_g=sum(hedges_g_values) / len(hedges_g_values) if hedges_g_values else None,
                sd_cohens_d=statistics.stdev(cohens_d_values) if len(cohens_d_values) > 1 else None,
                median_cohens_d=statistics.median(cohens_d_values) if cohens_d_values else None,
            ))
        
        return sorted(summaries, key=lambda x: x.n_studies, reverse=True)
    
    except Exception as e:
        logger.error(f"Error fetching outcome summaries: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching summaries: {str(e)}"
        )


@router.get("/evidence-panel", response_model=EvidencePanelData)
async def get_evidence_panel_data(
    study_ids: Optional[str] = Query(None, description="Limit to specific studies"),
    user: Optional[AuthenticatedUser] = Depends(get_optional_user),
):
    """
    Get all data needed for the Evidence Panel component.
    
    Returns study summaries, outcome summaries, and aggregate statistics.
    """
    client = get_supabase_client()
    
    try:
        query = client.table(ESTIMATES_TABLE).select("*")
        
        if study_ids:
            query = query.in_("study_id", study_ids.split(","))
        
        result = query.execute()
        
        if not result.data:
            return EvidencePanelData(
                study_summaries=[],
                outcome_summaries=[],
                total_studies=0,
                total_estimates=0,
                countries=[],
                study_designs=[],
                year_range=None,
            )
        
        rows = result.data
        
        # Group by study
        from collections import defaultdict
        by_study = defaultdict(list)
        for row in rows:
            by_study[row["study_id"]].append(row)
        
        # Build study summaries
        study_summaries = []
        for study_id, study_rows in by_study.items():
            first = study_rows[0]
            cohens_d_values = [r["cohens_d"] for r in study_rows if r.get("cohens_d")]
            hedges_g_values = [r["hedges_g"] for r in study_rows if r.get("hedges_g")]
            p_values = [r["p_value"] for r in study_rows if r.get("p_value")]
            outcome_cats = list(set(r["outcome_category"] for r in study_rows if r.get("outcome_category")))
            
            study_summaries.append(StudyEffectSummary(
                study_id=study_id,
                authors=first.get("authors"),
                year=first.get("year"),
                country=first.get("country"),
                study_design=first.get("study_design"),
                total_effects=len(study_rows),
                main_effects=sum(1 for r in study_rows if r.get("is_main_effect")),
                outcome_categories=outcome_cats,
                avg_cohens_d=sum(cohens_d_values) / len(cohens_d_values) if cohens_d_values else None,
                avg_hedges_g=sum(hedges_g_values) / len(hedges_g_values) if hedges_g_values else None,
                min_p_value=min(p_values) if p_values else None,
            ))
        
        # Get outcome summaries
        outcome_summaries = await get_outcome_summaries(study_ids, user)
        
        # Aggregate stats
        countries = list(set(r["country"] for r in rows if r.get("country")))
        study_designs = list(set(r["study_design"] for r in rows if r.get("study_design")))
        years = [r["year"] for r in rows if r.get("year")]
        year_range = (min(years), max(years)) if years else None
        
        return EvidencePanelData(
            study_summaries=study_summaries,
            outcome_summaries=outcome_summaries,
            total_studies=len(by_study),
            total_estimates=len(rows),
            countries=countries,
            study_designs=study_designs,
            year_range=year_range,
        )
    
    except Exception as e:
        logger.error(f"Error fetching evidence panel data: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching panel data: {str(e)}"
        )


# =============================================================================
# Chatbot Integration Endpoints
# =============================================================================

@router.get("/chatbot-context", response_model=ChatbotEffectContext)
async def get_chatbot_context(
    outcome_keywords: Optional[str] = Query(None, description="Keywords to filter outcomes"),
    study_ids: Optional[str] = Query(None, description="Limit to specific studies"),
    max_studies: int = Query(20, le=50, description="Max studies to include"),
    user: Optional[AuthenticatedUser] = Depends(get_optional_user),
):
    """
    Get compact effect context for chatbot prompts.
    
    Returns pre-formatted data optimized for RAG synthesis.
    This endpoint is called during chat to inject quantitative evidence.
    
    Args:
        outcome_keywords: Filter by outcome name keywords
        study_ids: Limit to specific study IDs
        max_studies: Maximum number of studies to include
        
    Returns:
        ChatbotEffectContext with prompt-ready data
    """
    client = get_supabase_client()
    
    try:
        query = client.table(ESTIMATES_TABLE).select("*")
        
        if study_ids:
            query = query.in_("study_id", study_ids.split(","))
        
        # Filter by outcome keywords if provided
        if outcome_keywords:
            # Use ilike for case-insensitive search
            keywords = outcome_keywords.split(",")
            for kw in keywords:
                query = query.ilike("outcome_name", f"%{kw.strip()}%")
        
        result = query.execute()
        
        if not result.data:
            return ChatbotEffectContext(
                studies=[],
                pooled_effects={},
                n_studies=0,
                n_estimates=0,
            )
        
        rows = result.data
        
        # Group by study
        from collections import defaultdict
        by_study = defaultdict(list)
        for row in rows:
            by_study[row["study_id"]].append(row)
        
        # Build compact study data (limit to max_studies)
        studies = []
        for study_id, study_rows in list(by_study.items())[:max_studies]:
            first = study_rows[0]
            cohens_d_values = [r["cohens_d"] for r in study_rows if r.get("cohens_d")]
            outcomes = list(set(r["outcome_category"] for r in study_rows if r.get("outcome_category")))
            
            studies.append({
                "study_id": study_id,
                "authors": first.get("authors"),
                "year": first.get("year"),
                "country": first.get("country"),
                "outcomes": outcomes,
                "avg_effect": round(sum(cohens_d_values) / len(cohens_d_values), 3) if cohens_d_values else None,
                "n_estimates": len(study_rows),
            })
        
        # Pool effects by outcome category
        by_outcome = defaultdict(list)
        for row in rows:
            if row.get("cohens_d") and row.get("outcome_category"):
                by_outcome[row["outcome_category"]].append(row["cohens_d"])
        
        pooled_effects = {
            cat: round(sum(values) / len(values), 3)
            for cat, values in by_outcome.items()
        }
        
        return ChatbotEffectContext(
            studies=studies,
            pooled_effects=pooled_effects,
            n_studies=len(by_study),
            n_estimates=len(rows),
        )
    
    except Exception as e:
        logger.error(f"Error fetching chatbot context: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching context: {str(e)}"
        )


@router.post("/chatbot-context/for-query")
async def get_context_for_query(
    query_text: str = Query(..., description="User's chat query"),
    rag_project_id: Optional[str] = Query(None, description="RAG project UUID"),
    max_estimates: int = Query(50, le=200, description="Max estimates to return"),
    user: Optional[AuthenticatedUser] = Depends(get_optional_user),
):
    """
    Get quantitative context relevant to a user's query.
    
    Uses semantic matching to find relevant effects based on the query text.
    This is the primary endpoint for chatbot integration.
    
    Args:
        query_text: The user's natural language query
        rag_project_id: Optional RAG project to filter by
        max_estimates: Maximum estimates to return
        
    Returns:
        QuantitativeContext with relevant effects and narrative summary
    """
    client = get_supabase_client()
    
    try:
        # Simple keyword extraction from query
        # In production, this could use embeddings for semantic search
        keywords = extract_outcome_keywords(query_text)
        
        query = client.table(ESTIMATES_TABLE).select("*")
        
        if rag_project_id:
            query = query.eq("rag_project_id", rag_project_id)
        
        # Apply keyword filters
        if keywords:
            # Build OR condition for keywords
            conditions = []
            for kw in keywords[:5]:  # Limit keywords
                query = query.or_(f"outcome_name.ilike.%{kw}%,outcome_category.ilike.%{kw}%")
        
        query = query.limit(max_estimates)
        result = query.execute()
        
        estimates = [row_to_estimate(row) for row in result.data] if result.data else []
        
        # Get outcome summaries for found estimates
        if estimates:
            study_ids = list(set(e.study_id for e in estimates))
            outcome_summaries = await get_outcome_summaries(",".join(study_ids[:20]), user)
        else:
            outcome_summaries = []
        
        # Generate narrative
        narrative = generate_evidence_narrative(estimates, outcome_summaries)
        
        return QuantitativeContext(
            query_relevant_estimates=estimates,
            outcome_summaries=outcome_summaries,
            evidence_narrative=narrative,
        )
    
    except Exception as e:
        logger.error(f"Error getting context for query: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting context: {str(e)}"
        )


# =============================================================================
# Utility Functions
# =============================================================================

def extract_outcome_keywords(query: str) -> List[str]:
    """
    Extract outcome-related keywords from a user query.
    
    Simple heuristic approach - in production, use NLP or embeddings.
    """
    # Common outcome terms to look for
    outcome_terms = [
        "income", "earnings", "wage", "salary",
        "assets", "wealth", "savings", "livestock",
        "consumption", "expenditure", "spending",
        "food", "nutrition", "hunger", "calories",
        "health", "illness", "disease", "mortality",
        "education", "school", "enrollment", "literacy",
        "employment", "job", "work", "labor",
        "poverty", "wellbeing", "welfare",
        "psychological", "mental", "depression", "stress",
    ]
    
    query_lower = query.lower()
    found = [term for term in outcome_terms if term in query_lower]
    
    return found if found else []


def generate_evidence_narrative(
    estimates: List[ExtractedEstimate],
    summaries: List[OutcomeMetaAnalysis],
) -> str:
    """
    Generate a natural language summary of the quantitative evidence.
    
    This narrative is injected into chatbot prompts.
    """
    if not estimates:
        return "No quantitative effect estimates found in the database for this query."
    
    n_studies = len(set(e.study_id for e in estimates))
    n_estimates = len(estimates)
    
    # Effect sizes available
    with_effect_size = [e for e in estimates if e.cohens_d is not None]
    
    lines = [f"**Quantitative Evidence Summary ({n_studies} studies, {n_estimates} estimates)**"]
    
    if with_effect_size:
        avg_d = sum(e.cohens_d for e in with_effect_size) / len(with_effect_size)
        lines.append(f"- Average effect size (Cohen's d): {avg_d:.3f}")
    
    # Outcome category breakdown
    if summaries:
        lines.append("\n**By Outcome Category:**")
        for s in summaries[:5]:
            if s.pooled_cohens_d:
                lines.append(f"- {s.outcome_category}: d = {s.pooled_cohens_d:.3f} ({s.n_studies} studies)")
    
    # Significance counts
    sig_counts = {"***": 0, "**": 0, "*": 0, "ns": 0}
    for e in estimates:
        level = e.significance_level
        if level and level in sig_counts:
            sig_counts[level] += 1
    
    if any(sig_counts.values()):
        lines.append(f"\n**Statistical Significance:** {sig_counts['***']} p<.001, {sig_counts['**']} p<.01, {sig_counts['*']} p<.05, {sig_counts['ns']} n.s.")
    
    return "\n".join(lines)


# =============================================================================
# Statistics Endpoints
# =============================================================================

@router.get("/stats")
async def get_extraction_stats(
    user: Optional[AuthenticatedUser] = Depends(get_optional_user),
):
    """
    Get overall extraction statistics.
    
    Returns counts, coverage, and summary metrics.
    """
    client = get_supabase_client()
    
    try:
        result = client.table(ESTIMATES_TABLE).select("*", count="exact").execute()
        
        if not result.data:
            return {
                "total_estimates": 0,
                "total_studies": 0,
                "countries": [],
                "outcome_categories": [],
                "year_range": None,
            }
        
        rows = result.data
        
        return {
            "total_estimates": result.count,
            "total_studies": len(set(r["study_id"] for r in rows)),
            "countries": list(set(r["country"] for r in rows if r.get("country"))),
            "outcome_categories": list(set(r["outcome_category"] for r in rows if r.get("outcome_category"))),
            "study_designs": list(set(r["study_design"] for r in rows if r.get("study_design"))),
            "year_range": {
                "min": min(r["year"] for r in rows if r.get("year")),
                "max": max(r["year"] for r in rows if r.get("year")),
            } if any(r.get("year") for r in rows) else None,
            "with_effect_size": sum(1 for r in rows if r.get("cohens_d")),
            "with_p_value": sum(1 for r in rows if r.get("p_value")),
        }
    
    except Exception as e:
        logger.error(f"Error fetching stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching stats: {str(e)}"
        )
