"""
DevChat v2.0 SOTA - Chat Routes

Core chat endpoints for the RAG pipeline.
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from api.qdrant_status import mark_qdrant_healthy
from api.schemas import (
    ChatRequest,
    ChatResponse,
    Citation,
    TimingInfo,
)
from src.utils.logging import get_logger

from .dependencies import get_agent

logger = get_logger(__name__)

router = APIRouter(prefix="/chat", tags=["Chat"])


@router.post("", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Process a user query and return an answer.
    
    The full RAG pipeline:
    1. Query classification and expansion
    2. Hybrid retrieval (dense + sparse)
    3. Cross-encoder reranking
    4. Adaptive synthesis
    """
    try:
        agent = get_agent()
        
        # Call agent with session_id for conversation memory
        response = await agent.chat(
            query=request.query,
            include_citations=request.include_citations,
            session_id=request.session_id,
        )

        await mark_qdrant_healthy()

        # Convert to API response
        return ChatResponse(
            answer=response.answer,
            query_type=response.query_type,
            model_used=response.model_used,
            num_sources=response.num_sources,
            citations=[
                Citation(
                    study_id=c.get("study_id", ""),
                    title=c.get("title", ""),
                    year=c.get("year"),
                    sector=c.get("sector"),
                    country=c.get("country"),
                    url=c.get("url"),
                )
                for c in response.citations
            ],
            timing=TimingInfo(
                query_ms=response.query_time_ms,
                retrieval_ms=response.retrieval_time_ms,
                rerank_ms=response.rerank_time_ms,
                synthesis_ms=response.synthesis_time_ms,
                total_ms=response.total_time_ms,
            ),
            expanded_query=response.expanded_query,
            filters_applied=response.filters_applied,
        )
        
    except Exception as e:
        logger.error(f"Chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stream")
async def chat_stream(request: ChatRequest):
    """
    Stream the response as it's generated.
    
    Returns Server-Sent Events (SSE).
    """
    async def generate():
        try:
            agent = get_agent()
            async for chunk in agent.chat_stream(request.query):
                yield f"data: {chunk}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: Error: {str(e)}\n\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
    )


@router.get("/history")
async def get_chat_history():
    """Get conversation history for the current session."""
    agent = get_agent()
    return {"history": agent.get_history()}


@router.delete("/history")
async def clear_chat_history():
    """Clear conversation history."""
    agent = get_agent()
    agent.clear_history()
    return {"status": "cleared"}
