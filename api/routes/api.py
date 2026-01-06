"""
DevChat v2.0 SOTA - Frontend API Routes

Endpoints for the Research Workbench frontend (query, compare, suggest, filters).
"""

import os
import re
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

# UUID pattern for detecting if a string is a UUID
UUID_PATTERN = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.IGNORECASE)

logger = get_logger(__name__)

router = APIRouter(prefix="/api", tags=["Frontend API"])


async def _resolve_project_id(rag_id: str) -> str:
    """
    Resolve a rag_id (which could be a UUID or slug) to the actual project UUID.
    
    Returns the UUID string, or raises HTTPException if not found.
    """
    from src.auth import get_supabase_client
    
    # If it's already a UUID, return as-is
    if UUID_PATTERN.match(rag_id):
        return rag_id
    
    # Otherwise, look up by slug
    try:
        client = get_supabase_client()
        result = client.table("rag_projects").select("id").eq("slug", rag_id).execute()
        
        if result.data and len(result.data) > 0:
            return result.data[0]["id"]
        
        # Not found by slug, return original (will fail in chat_history query)
        logger.warning(f"Could not resolve slug '{rag_id}' to project ID")
        return rag_id
    except Exception as e:
        logger.warning(f"Error resolving project ID: {e}")
        return rag_id


def _generate_pdf_url(document_id: str, source_path: str = None) -> str | None:
    """Generate a presigned R2 URL for a PDF document.
    
    Args:
        document_id: The document/study ID (filename stem)
        source_path: Optional R2 key path (e.g., "rags/{project_id}/input-pdfs/{file}.pdf")
                     If provided, uses this path directly instead of old format.
    
    Optimized: Skip file existence check - generate URL directly.
    Frontend will handle 404s gracefully.
    """
    try:
        r2_client = get_r2_client()
        bucket_name = os.getenv("R2_BUCKET_NAME", "devchat-pdfs")
        
        # If source path is provided, use it directly (for per-RAG projects)
        if source_path:
            r2_key = source_path
        else:
            # Fallback to old format for legacy collections
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


def _get_project_model_config(project_id: str) -> dict | None:
    """Fetch model configuration for a project from Supabase."""
    try:
        from src.auth import get_supabase_client
        client = get_supabase_client()
        result = client.table("rag_projects").select("model_config").eq("id", project_id).single().execute()
        if result.data and result.data.get("model_config"):
            return result.data["model_config"]
    except Exception as e:
        logger.warning(f"Failed to fetch model config for project {project_id}: {e}")
    return None


def _get_project_prompt_config(project_id: str) -> dict | None:
    """Fetch prompt configuration for a project from Supabase."""
    try:
        from src.auth import get_supabase_client
        client = get_supabase_client()
        result = client.table("rag_projects").select(
            "context_prompt, custom_prompts"
        ).eq("id", project_id).single().execute()
        logger.info(f"Prompt config query for {project_id}: {result.data}")
        if result.data:
            prompt_config = {}
            if result.data.get("context_prompt"):
                prompt_config["context_prompt"] = result.data["context_prompt"]
            if result.data.get("custom_prompts"):
                prompt_config["custom_prompts"] = result.data["custom_prompts"]
            if prompt_config:
                logger.info(f"Returning prompt config: {prompt_config}")
                return prompt_config
            else:
                logger.info("No context_prompt or custom_prompts found in result")
    except Exception as e:
        logger.warning(f"Failed to fetch prompt config for project {project_id}: {e}")
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
                
                # Fetch project-specific model configuration if project_id provided
                model_config = None
                prompt_config = None
                if request.project_id:
                    model_config = _get_project_model_config(request.project_id)
                    if model_config:
                        logger.info(f"Using project model config: {model_config.get('provider')}/{model_config.get('model')}")
                    prompt_config = _get_project_prompt_config(request.project_id)
                    if prompt_config:
                        has_context = bool(prompt_config.get("context_prompt"))
                        has_custom = bool(prompt_config.get("custom_prompts"))
                        logger.info(f"Using project prompt config: context={has_context}, custom={has_custom}")
                
                # Call the agent with settings and model config
                response = await agent.chat(
                    query=request.query,
                    include_citations=True,
                    search_settings=agent_settings,
                    model_config=model_config,
                    prompt_config=prompt_config,
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
                    # Use source path (R2 key) if available for per-RAG projects
                    source_path = c.get("source")
                    pdf_url = c.get("url") or _generate_pdf_url(study_id, source_path)
                    
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
                    # Use full_text from Qdrant chunk (not truncated snippet) for better highlighting
                    full_chunk_text = c.get("full_text", "")
                    if isinstance(full_chunk_text, list):
                        full_chunk_text = " ".join(str(t) for t in full_chunk_text)
                    full_chunk_text = str(full_chunk_text) if full_chunk_text else ""
                    # Clean but don't truncate - let the PDF endpoint handle it
                    highlight_text = full_chunk_text[:1500] if full_chunk_text else (clean_snippet[:500] if clean_snippet else None)
                    
                    citation = CitationResponse(
                        id=i + 1,
                        studyId=study.id,
                        text=clean_text_for_display(clean_snippet, max_length=200),
                        study=study,
                        page=page_num,
                        highlightText=highlight_text,
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
        rag_id: The RAG project ID or slug
        session_id: Optional session ID for anonymous users
        limit: Maximum number of history items to return
    """
    from src.auth import get_supabase_client
    
    try:
        supabase = get_supabase_client()
        
        # Resolve slug to project ID if needed
        project_id = await _resolve_project_id(rag_id)
        
        # Query chat history for this project (include answer for cache)
        query = supabase.table("chat_history")\
            .select("id, query, study_count, created_at, answer, citations_used, response_data")\
            .eq("rag_project_id", project_id)\
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
                    "answer": item.get("answer"),
                    "citationsUsed": item.get("citations_used"),
                    "responseData": item.get("response_data"),
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
        rag_id: The RAG project ID or slug
        body: {query: str, studyCount: int, sessionId?: str, answer?: str, citationsUsed?: int}
    """
    from src.auth import get_supabase_client
    
    try:
        supabase = get_supabase_client()
        
        # Resolve slug to project ID if needed
        project_id = await _resolve_project_id(rag_id)
        
        # Build insert data - only include answer/citations if columns exist
        insert_data = {
            "rag_project_id": project_id,
            "query": body.get("query", ""),
            "study_count": body.get("studyCount", 0),
            "session_id": body.get("sessionId"),
        }
        
        # Add answer if provided (requires migration to add column)
        if body.get("answer"):
            insert_data["answer"] = body.get("answer")
        if body.get("citationsUsed") is not None:
            insert_data["citations_used"] = body.get("citationsUsed")
        # Add full response data for caching (citations, studies, suggestions, etc.)
        if body.get("responseData"):
            insert_data["response_data"] = body.get("responseData")
        
        # Insert new history item
        result = supabase.table("chat_history").insert(insert_data).execute()
        
        if result.data:
            item = result.data[0]
            return {
                "id": item["id"],
                "query": item["query"],
                "studyCount": item["study_count"],
                "timestamp": item["created_at"],
                "answer": item.get("answer"),
                "citationsUsed": item.get("citations_used"),
                "responseData": item.get("response_data"),
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
        
        # Resolve slug to project ID if needed
        project_id = await _resolve_project_id(rag_id)
        
        # Delete the history item
        result = supabase.table("chat_history")\
            .delete()\
            .eq("id", history_id)\
            .eq("rag_project_id", project_id)\
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
        
        # Resolve slug to project ID if needed
        project_id = await _resolve_project_id(rag_id)
        
        query = supabase.table("chat_history")\
            .delete()\
            .eq("rag_project_id", project_id)
        
        if session_id:
            query = query.eq("session_id", session_id)
        
        result = query.execute()
        
        return {"cleared": True}
    except Exception as e:
        logger.error(f"Failed to clear chat history: {e}")
        raise HTTPException(status_code=500, detail=str(e))
