"""
DevChat v2.0 SOTA - Frontend API Routes

Endpoints for the Research Workbench frontend (query, compare, suggest, filters).
"""

import os
from botocore.exceptions import ClientError
from fastapi import APIRouter, HTTPException

from api.qdrant_status import mark_qdrant_healthy
from api.schemas import (
    CompareRequest,
    CompareResponse,
    CitationResponse,
    EvidenceHealth,
    FiltersResponse,
    QueryRequest,
    QueryResponse,
    StudyResponse,
    SuggestRequest,
    SuggestResponse,
)
from src.retrieval.context_builder import clean_text_for_display
from src.utils.cache import get_response_cache
from src.utils.circuit_breaker import get_circuit_breaker, CircuitOpenError
from src.utils.logging import get_logger

from .dependencies import get_agent, get_r2_client

logger = get_logger(__name__)

router = APIRouter(prefix="/api", tags=["Frontend API"])


def _generate_pdf_url(document_id: str) -> str | None:
    """Generate a presigned R2 URL for a PDF document.
    
    Optimized: Skip file existence check - generate URL directly.
    Frontend will handle 404s gracefully.
    """
    try:
        r2_client = get_r2_client()
        bucket_name = os.getenv("R2_BUCKET_NAME", "devchat-pdfs")
        r2_key = f"input-pdfs/{document_id}.pdf"
        
        # Generate presigned URL directly (valid for 1 hour)
        # Skip head_object check for performance
        return r2_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': bucket_name, 'Key': r2_key},
            ExpiresIn=3600,
        )
    except Exception as e:
        logger.warning(f"Failed to generate PDF URL for {document_id}: {e}")
        return None


@router.post("/query", response_model=QueryResponse)
async def query_evidence(request: QueryRequest):
    """
    Main query endpoint for the Research Workbench frontend.
    
    Production features:
    - Response caching for identical queries
    - Circuit breaker for graceful degradation
    - Proper timeout handling
    
    Returns structured response with:
    - answer: Formatted response with inline citations [1], [2]
    - citations: List of citations with study details
    - studies: List of study cards for the evidence panel
    - suggestions: Follow-up query suggestions
    - evidenceHealth: Coverage metrics
    """
    try:
        # Check cache first (production optimization)
        cache = get_response_cache()
        cache_key_settings = request.settings.model_dump() if request.settings else None
        cache_key_filters = [f.model_dump() for f in request.filters] if request.filters else None
        
        cached_response = await cache.get(
            query=request.query,
            filters=cache_key_filters,
            settings_dict=cache_key_settings,
        )
        if cached_response:
            logger.info(f"Cache hit for query: {request.query[:50]}...")
            return cached_response
        
        # Use circuit breaker for external service calls
        llm_breaker = get_circuit_breaker("llm_service", failure_threshold=3, recovery_timeout=60)
        
        try:
            async with llm_breaker:
                settings_obj = request.settings
                
                # Build filters from request
                year_min = None
                year_max = None
                countries = None
                sectors = None
                study_types = None
                
                if request.filters:
                    for f in request.filters:
                        if f.type == "yearRange":
                            # Parse "2018-2024" format
                            if "-" in f.value:
                                parts = f.value.split("-")
                                year_min = int(parts[0])
                                year_max = int(parts[1])
                        elif f.type == "country":
                            countries = countries or []
                            countries.append(f.value)
                        elif f.type == "sector":
                            sectors = sectors or []
                            sectors.append(f.value)
                        elif f.type == "studyType":
                            study_types = study_types or []
                            study_types.append(f.value)
                
                # Apply settings to year filter
                if settings_obj:
                    if settings_obj.yearCutoff and not year_min:
                        year_min = settings_obj.yearCutoff
                
                # Convert API settings to agent SearchSettings
                from src.agents.devchat_agent import SearchSettings as AgentSearchSettings
                agent_settings = None
                if settings_obj:
                    agent_settings = AgentSearchSettings(
                        relevance_threshold=settings_obj.relevanceThreshold,
                        max_studies=settings_obj.maxStudies,
                        answer_style=settings_obj.answerStyle,
                        use_reranking=settings_obj.useReranking,
                        min_confidence=settings_obj.minConfidence,
                        year_cutoff=settings_obj.yearCutoff,
                    )
                
                # Get agent (with optional custom collection for multi-tenant)
                agent = get_agent(collection_name=request.collection)
                
                # Call the agent with settings
                response = await agent.chat(
                    query=request.query,
                    include_citations=True,
                    search_settings=agent_settings,
                )
                
                # Convert backend response to frontend format
                studies: list[StudyResponse] = []
                citations: list[CitationResponse] = []
                
                # Process citations from agent response
                for i, c in enumerate(response.citations):
                    # Clean the snippet text for display
                    raw_snippet = c.get("snippet", c.get("text", ""))
                    # Handle case where snippet is a list
                    if isinstance(raw_snippet, list):
                        raw_snippet = " ".join(str(s) for s in raw_snippet)
                    raw_snippet = str(raw_snippet) if raw_snippet else ""
                    clean_snippet = clean_text_for_display(raw_snippet, max_length=300)
                    
                    # Handle authors - could be list, string, or missing
                    raw_authors = c.get("authors")
                    if isinstance(raw_authors, list):
                        # Flatten nested lists if necessary
                        flat_authors = []
                        for a in raw_authors:
                            if isinstance(a, list):
                                flat_authors.extend(str(x) for x in a)
                            else:
                                flat_authors.append(str(a))
                        authors_str = ", ".join(flat_authors) if flat_authors else ""
                    elif raw_authors:
                        authors_str = str(raw_authors)
                    else:
                        authors_str = ""
                    
                    # Handle year - could be None, empty, or invalid
                    raw_year = c.get("year")
                    year_val = None
                    if raw_year:
                        try:
                            year_val = int(raw_year)
                        except (ValueError, TypeError):
                            year_val = None
                    
                    # Get study ID and generate PDF URL
                    study_id = c.get("study_id", f"STUDY{i+1:03d}")
                    pdf_url = c.get("url") or _generate_pdf_url(study_id)
                    
                    study = StudyResponse(
                        id=study_id,
                        title=c.get("title", "Unknown Study"),
                        authors=authors_str,
                        year=year_val,
                        country=c.get("country", ""),
                        sector=c.get("sector", ""),
                        studyType=c.get("study_type", ""),
                        confidence="high" if c.get("score", 0.5) > 0.7 else "medium" if c.get("score", 0.5) > 0.4 else "low",
                        snippet=clean_snippet,
                        score=c.get("score", 0.0),
                        pdfUrl=pdf_url,
                    )
                    studies.append(study)
                    
                    # Get page info and highlight text for PDF navigation
                    page_num = c.get("page_start") or c.get("page")
                    # Get first few words for highlight search (use clean_snippet which is already a string)
                    highlight_words = " ".join(clean_snippet.split()[:10]) if clean_snippet else None
                    
                    citation = CitationResponse(
                        id=i + 1,
                        studyId=study.id,
                        text=clean_text_for_display(clean_snippet, max_length=200),
                        study=study,
                        page=page_num,
                        highlightText=highlight_words,
                    )
                    citations.append(citation)
                
                # Deduplicate studies by ID
                seen_ids = set()
                unique_studies = []
                for s in studies:
                    if s.id not in seen_ids:
                        seen_ids.add(s.id)
                        unique_studies.append(s)
                
                # Calculate evidence health with richer metrics
                years = [s.year for s in unique_studies if s.year]
                date_range = f"{min(years)}-{max(years)}" if years else "Unknown"
                
                gaps = []
                
                # Check geographic diversity
                countries_found = set(s.country for s in unique_studies if s.country)
                if len(countries_found) < 3:
                    gaps.append(f"Limited geographic coverage ({len(countries_found)} {'country' if len(countries_found) == 1 else 'countries'})")
                
                # Check methodology diversity
                study_types = set(s.studyType for s in unique_studies if s.studyType)
                if len(study_types) < 2:
                    gaps.append(f"Limited methodology diversity ({len(study_types)} study type{'s' if len(study_types) != 1 else ''})")
                
                # Check recency (if most studies are old)
                current_year = 2026
                recent_studies = [s for s in unique_studies if s.year and s.year >= current_year - 5]
                if len(unique_studies) > 0 and len(recent_studies) / len(unique_studies) < 0.3:
                    gaps.append(f"Most studies are older than 5 years ({len(recent_studies)}/{len(unique_studies)} recent)")
                
                # Check confidence distribution
                high_confidence = [s for s in unique_studies if s.confidence == "high"]
                if len(unique_studies) > 2 and len(high_confidence) / len(unique_studies) < 0.3:
                    gaps.append(f"Low proportion of high-confidence studies ({len(high_confidence)}/{len(unique_studies)})")
                
                evidence_health = EvidenceHealth(
                    studyCount=len(unique_studies),
                    dateRange=date_range,
                    gaps=gaps,
                    coverageWarning=None if len(unique_studies) >= 3 else "Few studies found - consider broadening search",
                )
                
                # Generate LLM-based suggestions
                try:
                    suggestions = await agent.generate_suggestions(
                        query=request.query,
                        answer=response.answer,
                        citations=response.citations,
                    )
                except Exception as e:
                    logger.warning(f"Failed to generate suggestions: {e}")
                    # Fallback to default suggestions
                    suggestions = [
                        "Narrow to a specific region?",
                        "Compare different study designs?",
                        "Focus on more recent studies?",
                    ]

                await mark_qdrant_healthy()

                query_response = QueryResponse(
                    answer=response.answer,
                    citations=citations,
                    studies=unique_studies,
                    suggestions=suggestions,
                    evidenceHealth=evidence_health,
                )
                
                # Store in cache for future requests
                await cache.set(
                    query=request.query,
                    response=query_response,
                    filters=cache_key_filters,
                    settings_dict=cache_key_settings,
                )
                
                return query_response
                
        except CircuitOpenError as e:
            # Circuit breaker is open - return graceful degradation response
            logger.warning(f"Circuit breaker open: {e}")
            return QueryResponse(
                answer="The service is temporarily experiencing high load. Please try again in a few minutes.",
                citations=[],
                studies=[],
                suggestions=["Try again in a minute", "Simplify your query"],
                evidenceHealth=EvidenceHealth(studyCount=0, dateRange="N/A", gaps=["Service temporarily unavailable"]),
            )
        
    except Exception as e:
        import traceback
        full_traceback = traceback.format_exc()
        logger.error(f"Query error: {e}\nFull traceback:\n{full_traceback}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/compare", response_model=CompareResponse)
async def compare_studies(request: CompareRequest):
    """
    Compare selected studies side-by-side.
    """
    # TODO: Implement full comparison logic
    # For now, return placeholder
    comparison = {}
    for study_id in request.study_ids:
        comparison[study_id] = {
            "Country": "Unknown",
            "Design": "Unknown",
            "Population": "Unknown",
            "Intervention": "Unknown",
            "Outcome": "Unknown",
            "Effect": "Unknown",
        }
    
    return CompareResponse(
        comparison=comparison,
        conflicts=[],
    )


@router.post("/suggest", response_model=SuggestResponse)
async def get_suggestions(request: SuggestRequest):
    """
    Get query coaching suggestions.
    """
    # TODO: Use LLM to generate contextual suggestions
    suggestions = [
        "What about long-term effects?",
        "Compare different program types?",
        "Focus on a specific region?",
    ]
    
    return SuggestResponse(suggestions=suggestions)


@router.get("/filters", response_model=FiltersResponse)
async def get_available_filters():
    """
    Get available filter options from the database.
    """
    # TODO: Query Qdrant for distinct values
    return FiltersResponse(
        countries=["Kenya", "India", "Mexico", "Brazil", "Uganda", "Ethiopia", "Bangladesh"],
        sectors=["Education", "Health", "Social Protection", "Agriculture", "Nutrition"],
        studyTypes=["RCT", "Quasi-experimental", "Systematic Review", "Mixed Methods"],
        yearRange={"min": 1990, "max": 2024},
    )


# =============================================================================
# Chat History Endpoints
# =============================================================================

@router.get("/chat-history/{rag_id}")
async def get_chat_history(rag_id: str, session_id: str = None, limit: int = 50):
    """
    Get chat history for a RAG project.
    
    Args:
        rag_id: The RAG project ID
        session_id: Optional session ID for anonymous users
        limit: Maximum number of history items to return
    """
    from src.auth import get_supabase_client
    
    try:
        supabase = get_supabase_client()
        
        # Query chat history for this project
        query = supabase.table("chat_history")\
            .select("id, query, study_count, created_at")\
            .eq("rag_project_id", rag_id)\
            .order("created_at", desc=True)\
            .limit(limit)
        
        # Filter by session if provided (for anonymous users)
        if session_id:
            query = query.eq("session_id", session_id)
        
        result = query.execute()
        
        return {
            "history": [
                {
                    "id": item["id"],
                    "query": item["query"],
                    "studyCount": item["study_count"],
                    "timestamp": item["created_at"],
                }
                for item in result.data
            ]
        }
    except Exception as e:
        logger.error(f"Failed to get chat history: {e}")
        # Return empty history on error (graceful degradation)
        return {"history": []}


@router.post("/chat-history/{rag_id}")
async def add_chat_history(rag_id: str, body: dict):
    """
    Add a query to chat history.
    
    Args:
        rag_id: The RAG project ID
        body: {query: str, studyCount: int, sessionId?: str}
    """
    from src.auth import get_supabase_client
    
    try:
        supabase = get_supabase_client()
        
        # Insert new history item
        result = supabase.table("chat_history").insert({
            "rag_project_id": rag_id,
            "query": body.get("query", ""),
            "study_count": body.get("studyCount", 0),
            "session_id": body.get("sessionId"),
        }).execute()
        
        if result.data:
            item = result.data[0]
            return {
                "id": item["id"],
                "query": item["query"],
                "studyCount": item["study_count"],
                "timestamp": item["created_at"],
            }
        
        return {"error": "Failed to add history"}
    except Exception as e:
        logger.error(f"Failed to add chat history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/chat-history/{rag_id}/{history_id}")
async def delete_chat_history_item(rag_id: str, history_id: str):
    """
    Delete a specific chat history item.
    """
    from src.auth import get_supabase_client
    
    try:
        supabase = get_supabase_client()
        
        # Delete the history item
        result = supabase.table("chat_history")\
            .delete()\
            .eq("id", history_id)\
            .eq("rag_project_id", rag_id)\
            .execute()
        
        return {"deleted": True}
    except Exception as e:
        logger.error(f"Failed to delete chat history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/chat-history/{rag_id}")
async def clear_chat_history(rag_id: str, session_id: str = None):
    """
    Clear all chat history for a RAG project (or just for a session).
    """
    from src.auth import get_supabase_client
    
    try:
        supabase = get_supabase_client()
        
        query = supabase.table("chat_history")\
            .delete()\
            .eq("rag_project_id", rag_id)
        
        if session_id:
            query = query.eq("session_id", session_id)
        
        result = query.execute()
        
        return {"cleared": True}
    except Exception as e:
        logger.error(f"Failed to clear chat history: {e}")
        raise HTTPException(status_code=500, detail=str(e))
