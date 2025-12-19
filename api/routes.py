"""
DevChat v2.0 SOTA - API Routes

Defines all API endpoints.
"""

import os
from datetime import datetime
from typing import Optional
from uuid import uuid4

import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException, Query, UploadFile, File
from fastapi.responses import StreamingResponse

# Load environment variables from .env file
load_dotenv()

from api.schemas import (
    ChatRequest,
    ChatResponse,
    Citation,
    CitationResponse,
    CollectionInfo,
    CompareRequest,
    CompareResponse,
    ErrorResponse,
    EvidenceHealth,
    FiltersResponse,
    HealthResponse,
    IngestRequest,
    IngestResponse,
    MetricsResponse,
    QueryRequest,
    QueryResponse,
    StudyResponse,
    SuggestRequest,
    SuggestResponse,
    TimingInfo,
    # Admin schemas
    UploadResponse,
    ProcessingJob,
    ProcessingJobsResponse,
    DocumentMetadata,
    DocumentsResponse,
    AdminStatusResponse,
    ServiceConnection,
    StorageStatus,
    TriggerProcessingRequest,
    TriggerProcessingResponse,
)
from src.agents.devchat_agent import DevChatAgent
from src.config.settings import settings
from src.ingestion.indexer import QdrantIndexer
from src.retrieval.context_builder import clean_text_for_display
from src.utils.logging import get_logger
from src.utils.metrics import get_metrics_tracker

logger = get_logger(__name__)

# Create routers
router = APIRouter()
health_router = APIRouter(prefix="/health", tags=["Health"])
chat_router = APIRouter(prefix="/chat", tags=["Chat"])
admin_router = APIRouter(prefix="/admin", tags=["Admin"])
api_router = APIRouter(prefix="/api", tags=["Frontend API"])

# Global agent instance
_agent: Optional[DevChatAgent] = None


def get_agent() -> DevChatAgent:
    """Get or create the global agent instance."""
    global _agent
    if _agent is None:
        _agent = DevChatAgent()
    return _agent


# =============================================================================
# Frontend API Endpoints (Research Workbench)
# =============================================================================

@api_router.post("/query", response_model=QueryResponse)
async def query_evidence(request: QueryRequest):
    """
    Main query endpoint for the Research Workbench frontend.
    
    Returns structured response with:
    - answer: Formatted response with inline citations [1], [2]
    - citations: List of citations with study details
    - studies: List of study cards for the evidence panel
    - suggestions: Follow-up query suggestions
    - evidenceHealth: Coverage metrics
    """
    try:
        agent = get_agent()
        settings = request.settings
        
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
        if settings:
            if settings.yearCutoff and not year_min:
                year_min = settings.yearCutoff
        
        # Convert API settings to agent SearchSettings
        from src.agents.devchat_agent import SearchSettings as AgentSearchSettings
        agent_settings = None
        if settings:
            agent_settings = AgentSearchSettings(
                relevance_threshold=settings.relevanceThreshold,
                max_studies=settings.maxStudies,
                answer_style=settings.answerStyle,
                use_reranking=settings.useReranking,
                min_confidence=settings.minConfidence,
                year_cutoff=settings.yearCutoff,
            )
        
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
            clean_snippet = clean_text_for_display(raw_snippet, max_length=300)
            
            # Handle authors - could be list, string, or missing
            raw_authors = c.get("authors")
            if isinstance(raw_authors, list):
                authors_str = ", ".join(str(a) for a in raw_authors) if raw_authors else ""
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
            
            study = StudyResponse(
                id=c.get("study_id", f"STUDY{i+1:03d}"),
                title=c.get("title", "Unknown Study"),
                authors=authors_str,
                year=year_val,
                country=c.get("country", ""),
                sector=c.get("sector", ""),
                studyType=c.get("study_type", ""),
                confidence="high" if c.get("score", 0.5) > 0.7 else "medium" if c.get("score", 0.5) > 0.4 else "low",
                snippet=clean_snippet,
                score=c.get("score", 0.0),
                pdfUrl=c.get("url"),
            )
            studies.append(study)
            
            citation = CitationResponse(
                id=i + 1,
                studyId=study.id,
                text=clean_text_for_display(raw_snippet, max_length=200),
                study=study,
            )
            citations.append(citation)
        
        # Deduplicate studies by ID
        seen_ids = set()
        unique_studies = []
        for s in studies:
            if s.id not in seen_ids:
                seen_ids.add(s.id)
                unique_studies.append(s)
        
        # Calculate evidence health
        years = [s.year for s in unique_studies if s.year]
        date_range = f"{min(years)}-{max(years)}" if years else "Unknown"
        
        gaps = []
        countries_found = set(s.country for s in unique_studies)
        if len(countries_found) < 3:
            gaps.append(f"Limited geographic coverage ({len(countries_found)} countries)")
        
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
        
        return QueryResponse(
            answer=response.answer,
            citations=citations,
            studies=unique_studies,
            suggestions=suggestions,
            evidenceHealth=evidence_health,
        )
        
    except Exception as e:
        logger.error(f"Query error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/compare", response_model=CompareResponse)
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


@api_router.post("/suggest", response_model=SuggestResponse)
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


@api_router.get("/filters", response_model=FiltersResponse)
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
# Health Endpoints
# =============================================================================

@health_router.get("", response_model=HealthResponse)
async def health_check():
    """
    Check service health.
    
    Returns status of all components.
    """
    components = {
        "api": True,
        "qdrant": False,
        "llm": False,
    }
    
    # Check Qdrant
    try:
        indexer = QdrantIndexer()
        info = indexer.get_collection_info()
        components["qdrant"] = "error" not in info
    except Exception as e:
        logger.warning(f"Qdrant health check failed: {e}")
    
    # Check LLM (basic check)
    try:
        components["llm"] = bool(settings.anthropic_api_key or settings.openai_api_key)
    except Exception:
        pass
    
    overall_status = "healthy" if all(components.values()) else "degraded"
    
    return HealthResponse(
        status=overall_status,
        version="2.0.0",
        timestamp=datetime.now(),
        components=components,
    )


@health_router.get("/ready")
async def readiness_check():
    """Kubernetes-style readiness probe."""
    return {"status": "ready"}


@health_router.get("/live")
async def liveness_check():
    """Kubernetes-style liveness probe."""
    return {"status": "live"}


# =============================================================================
# Chat Endpoints
# =============================================================================

@chat_router.post("", response_model=ChatResponse)
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
        
        # Call agent
        response = await agent.chat(
            query=request.query,
            include_citations=request.include_citations,
        )
        
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


@chat_router.post("/stream")
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


@chat_router.get("/history")
async def get_chat_history():
    """Get conversation history for the current session."""
    agent = get_agent()
    return {"history": agent.get_history()}


@chat_router.delete("/history")
async def clear_chat_history():
    """Clear conversation history."""
    agent = get_agent()
    agent.clear_history()
    return {"status": "cleared"}


# =============================================================================
# Admin Endpoints
# =============================================================================

@admin_router.get("/metrics", response_model=MetricsResponse)
async def get_metrics(
    last_n: Optional[int] = Query(default=None, description="Only last N queries"),
):
    """Get metrics summary."""
    tracker = get_metrics_tracker()
    summary = tracker.get_summary(last_n)
    
    if "message" in summary:
        return MetricsResponse(
            total_queries=0,
            latency={},
            query_types={},
            error_rate_percent=0.0,
            tokens={},
        )
    
    return MetricsResponse(
        total_queries=summary["total_queries"],
        latency=summary["latency"],
        query_types=summary["query_types"],
        error_rate_percent=summary["error_rate_percent"],
        tokens=summary["tokens"],
    )


@admin_router.get("/collection")
async def get_collection_info():
    """Get vector collection information."""
    try:
        indexer = QdrantIndexer()
        info = indexer.get_collection_info()
        return info
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@admin_router.post("/indexes")
async def ensure_indexes():
    """
    Create or ensure all required payload indexes exist on the Qdrant collection.
    This enables efficient filtering by document_id, source, etc.
    Safe to call multiple times - will skip already existing indexes.
    """
    try:
        indexer = QdrantIndexer()
        results = indexer.ensure_indexes()
        return {
            "success": True,
            "message": "Payload indexes ensured",
            "indexes": results,
        }
    except Exception as e:
        logger.error(f"Failed to ensure indexes: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@admin_router.get("/sample-points")
async def sample_points(limit: int = 5):
    """
    Sample a few points from Qdrant to inspect payloads.
    Useful for debugging what fields are available for filtering/deletion.
    """
    try:
        indexer = QdrantIndexer()
        points = indexer.sample_points(limit=limit)
        return {
            "count": len(points),
            "points": points,
        }
    except Exception as e:
        logger.error(f"Failed to sample points: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@admin_router.post("/ingest", response_model=IngestResponse)
async def ingest_documents(request: IngestRequest):
    """
    Ingest documents into the vector database.
    
    This is an admin endpoint for re-indexing documents.
    """
    import time
    from pathlib import Path
    
    from src.ingestion.chunking import get_chunker
    from src.ingestion.document_loader import DocumentLoader
    from src.ingestion.indexer import QdrantIndexer
    
    start_time = time.time()
    
    try:
        # Load documents
        loader = DocumentLoader(markdown_dir=Path(request.source_path))
        documents = loader.load_all()
        
        if not documents:
            raise HTTPException(status_code=400, detail="No documents found")
        
        # Chunk documents
        chunker = get_chunker("hybrid")
        nodes = chunker.chunk(documents)
        
        # Index
        collection_name = request.collection_name or settings.qdrant_collection_name
        indexer = QdrantIndexer(collection_name=collection_name)
        indexer.create_collection(recreate=request.recreate)
        indexer.index_nodes(nodes)
        
        # Get final info
        info = indexer.get_collection_info()
        
        elapsed = time.time() - start_time
        
        return IngestResponse(
            status="success",
            documents_processed=len(documents),
            chunks_created=len(nodes),
            collection=CollectionInfo(
                name=info["name"],
                points_count=info["points_count"],
                vectors_count=info["vectors_count"],
                status=info["status"],
            ),
            elapsed_seconds=elapsed,
        )
        
    except Exception as e:
        logger.error(f"Ingestion error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Admin API Endpoints (Document Management)
# =============================================================================

@admin_router.get("/status", response_model=AdminStatusResponse)
async def get_admin_status():
    """
    Get admin dashboard status including storage and service connections.
    """
    # TODO: Replace with actual R2/Modal/Qdrant checks
    return AdminStatusResponse(
        storage=StorageStatus(
            bucket="devchat-pdfs",
            input_path="/input-pdfs/",
            output_path="/outputs/",
            storage_used_bytes=2_500_000_000,  # 2.5 GB placeholder
            file_count=42,
        ),
        connections=[
            ServiceConnection(name="Cloudflare R2", status="connected", details="devchat-pdfs"),
            ServiceConnection(name="Qdrant Cloud", status="connected", details="1,234 vectors"),
            ServiceConnection(name="Modal", status="connected", details="2 workers"),
            ServiceConnection(name="Cohere API", status="connected", details="embed-v4.0"),
        ],
        pending_jobs=3,
        active_workers=1,
    )


def get_r2_client():
    """Create S3 client configured for Cloudflare R2."""
    account_id = os.getenv("R2_ACCOUNT_ID", "667549da0201b12a53872d803b9880b6")
    access_key = os.getenv("R2_ACCESS_KEY_ID")
    secret_key = os.getenv("R2_SECRET_ACCESS_KEY")
    
    if not access_key or not secret_key:
        raise HTTPException(
            status_code=500,
            detail="R2 credentials not configured. Set R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY."
        )
    
    return boto3.client(
        "s3",
        endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name="auto",
    )


@admin_router.post("/upload", response_model=UploadResponse)
async def upload_document(
    file: UploadFile = File(...),
):
    """
    Upload a document to R2 for processing.
    
    The file will be stored in the input-pdfs/ prefix and queued for
    processing by the Modal MinerU pipeline.
    """
    # Validate file type
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")
    
    allowed_extensions = {".pdf", ".docx", ".doc", ".txt", ".md"}
    file_ext = os.path.splitext(file.filename)[1].lower()
    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"File type {file_ext} not allowed. Allowed: {allowed_extensions}"
        )
    
    # Generate universal document ID (used across R2, Qdrant, Modal, etc.)
    unique_id = str(uuid4())[:8]
    safe_filename = file.filename.replace(" ", "_").replace("/", "_")
    base_name = os.path.splitext(safe_filename)[0]
    
    # doc_id format: {8-char-uuid}_{sanitized_basename}
    # This ID is used consistently across all systems
    doc_id = f"{unique_id}_{base_name}"
    
    r2_key = f"input-pdfs/{doc_id}{file_ext}"
    
    try:
        # Read file content
        content = await file.read()
        size_bytes = len(content)
        
        # Upload to R2
        r2_client = get_r2_client()
        bucket_name = os.getenv("R2_BUCKET_NAME", "devchat-pdfs")
        
        r2_client.put_object(
            Bucket=bucket_name,
            Key=r2_key,
            Body=content,
            ContentType=file.content_type or "application/pdf",
            Metadata={
                "doc_id": doc_id,  # Universal document ID
                "original_filename": file.filename,
                "upload_timestamp": datetime.utcnow().isoformat(),
            }
        )
        
        logger.info(f"Uploaded {file.filename} to R2 as {r2_key} (doc_id={doc_id}, {size_bytes} bytes)")
        
        return UploadResponse(
            success=True,
            filename=file.filename,
            r2_key=r2_key,
            size_bytes=size_bytes,
            queued_for_processing=True,
            doc_id=doc_id,  # Return the doc_id for reference
        )
        
    except ClientError as e:
        logger.error(f"R2 upload failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to upload to R2: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Upload failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Upload failed: {str(e)}"
        )


@admin_router.get("/r2/list")
async def list_r2_files(prefix: str = Query("input-pdfs/", description="Prefix to list")):
    """
    List files in R2 bucket.
    """
    try:
        r2_client = get_r2_client()
        bucket_name = os.getenv("R2_BUCKET_NAME", "devchat-pdfs")
        
        response = r2_client.list_objects_v2(
            Bucket=bucket_name,
            Prefix=prefix,
            MaxKeys=100,
        )
        
        files = []
        for obj in response.get("Contents", []):
            files.append({
                "key": obj["Key"],
                "size_bytes": obj["Size"],
                "last_modified": obj["LastModified"].isoformat(),
            })
        
        return {
            "prefix": prefix,
            "file_count": len(files),
            "files": files,
        }
        
    except ClientError as e:
        logger.error(f"R2 list failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list R2: {str(e)}")


@admin_router.get("/jobs", response_model=ProcessingJobsResponse)
async def get_processing_jobs():
    """
    Get list of processing jobs with their status.
    
    TODO: Implement actual job tracking from Modal/database
    """
    # Mock data - replace with actual job tracking
    jobs = [
        ProcessingJob(
            id="job-001",
            filename="systematic_review_education.pdf",
            status="processing",
            progress=65,
            started_at=datetime.now(),
            pages=45,
        ),
        ProcessingJob(
            id="job-002",
            filename="rct_cash_transfers.pdf",
            status="queued",
            progress=0,
        ),
        ProcessingJob(
            id="job-003",
            filename="impact_eval_health.pdf",
            status="completed",
            progress=100,
            started_at=datetime.now(),
            completed_at=datetime.now(),
            pages=32,
            chunks=156,
        ),
    ]
    
    return ProcessingJobsResponse(
        jobs=jobs,
        queued_count=sum(1 for j in jobs if j.status == "queued"),
        processing_count=sum(1 for j in jobs if j.status == "processing"),
        completed_count=sum(1 for j in jobs if j.status == "completed"),
        failed_count=sum(1 for j in jobs if j.status == "failed"),
    )


@admin_router.post("/jobs/trigger", response_model=TriggerProcessingResponse)
async def trigger_processing(request: TriggerProcessingRequest):
    """
    Trigger batch processing of pending PDFs.
    
    Calls the Modal orchestrator function to process new PDFs.
    """
    import subprocess
    
    try:
        # Run Modal orchestrator command with UTF-8 encoding
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        
        result = subprocess.run(
            ["modal", "run", "infrastructure/modal_mineru.py::orchestrate"],
            capture_output=True,
            timeout=60,  # Longer timeout for initial run
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            env=env,
            encoding="utf-8",
            errors="replace",  # Replace undecodable chars
        )
        
        if result.returncode == 0:
            # Parse output if available
            logger.info(f"Modal orchestrate triggered: {result.stdout}")
            return TriggerProcessingResponse(
                queued=request.max_documents or 10,
                skipped=0,
                message=f"Processing triggered. Output: {result.stdout[:200] if result.stdout else 'Started'}",
            )
        else:
            logger.error(f"Modal trigger failed: {result.stderr}")
            return TriggerProcessingResponse(
                queued=0,
                skipped=0,
                message=f"Trigger failed: {result.stderr[:200] if result.stderr else 'Unknown error'}",
            )
            
    except subprocess.TimeoutExpired:
        # This is expected - job continues in background
        return TriggerProcessingResponse(
            queued=request.max_documents or 10,
            skipped=0,
            message="Processing triggered in background (Modal running)",
        )
    except Exception as e:
        logger.error(f"Failed to trigger Modal: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to trigger processing: {str(e)}"
        )


@admin_router.get("/documents", response_model=DocumentsResponse)
async def get_documents(
    search: Optional[str] = Query(None, description="Search query"),
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """
    Get list of indexed documents from Qdrant.
    
    Aggregates unique documents from vector payloads.
    """
    try:
        indexer = QdrantIndexer()
        
        # Scroll through all points to get unique documents
        # This is a simple approach - for production, use a metadata DB
        all_points = []
        next_offset = None
        
        while True:
            results, next_offset = indexer.client.scroll(
                collection_name=indexer.collection_name,
                limit=100,
                offset=next_offset,
                with_payload=True,
                with_vectors=False,
            )
            all_points.extend(results)
            if next_offset is None or len(results) == 0:
                break
        
        # Aggregate by doc_id (universal document identifier)
        doc_map = {}
        for point in all_points:
            payload = point.payload or {}
            
            # Get doc_id - primary identifier (new format)
            # Fallback to pdf_name or source for backward compatibility
            doc_id = payload.get("doc_id") or payload.get("pdf_name") or payload.get("source", "unknown")
            
            # Extract doc_id from source path if needed (e.g., "input-pdfs/abc123_file.pdf" -> "abc123_file")
            if "/" in doc_id:
                doc_id = doc_id.split("/")[-1]
            if doc_id.endswith(".pdf"):
                doc_id = doc_id[:-4]
            
            if doc_id not in doc_map:
                doc_map[doc_id] = {
                    "doc_id": doc_id,  # Universal document ID
                    "id": doc_id,  # For API compatibility
                    "title": payload.get("title", doc_id),
                    "filename": f"{doc_id}.pdf",
                    "source": payload.get("source", ""),
                    "authors": [],
                    "year": payload.get("year"),
                    "status": "indexed",
                    "page_count": 0,
                    "chunk_count": 0,
                    "uploaded_at": datetime.now(),
                    "processed_at": datetime.now(),
                }
            
            doc_map[doc_id]["chunk_count"] += 1
            
            # Try to get page info
            if payload.get("page"):
                doc_map[doc_id]["page_count"] = max(
                    doc_map[doc_id]["page_count"], 
                    int(payload.get("page", 0))
                )
            
            # Get authors if available
            if payload.get("authors") and not doc_map[doc_id]["authors"]:
                authors = payload.get("authors")
                if isinstance(authors, list):
                    doc_map[doc_id]["authors"] = authors
                elif isinstance(authors, str):
                    doc_map[doc_id]["authors"] = [authors]
        
        # Convert to list and apply filters
        documents = []
        for doc_data in doc_map.values():
            # Apply search filter
            if search:
                search_lower = search.lower()
                if (search_lower not in doc_data["title"].lower() and 
                    search_lower not in doc_data["filename"].lower() and
                    search_lower not in doc_data["doc_id"].lower()):
                    continue
            
            documents.append(DocumentMetadata(
                id=doc_data["doc_id"],  # Use doc_id as the primary identifier
                title=doc_data["title"],
                filename=doc_data["filename"],
                authors=doc_data["authors"],
                year=doc_data["year"],
                status=doc_data["status"],
                page_count=doc_data["page_count"],
                chunk_count=doc_data["chunk_count"],
                uploaded_at=doc_data["uploaded_at"],
                processed_at=doc_data["processed_at"],
            ))
        
        # Apply pagination
        total_count = len(documents)
        documents = documents[offset:offset + limit]
        
        total_chunks = sum(d.chunk_count for d in documents)
        total_pages = sum(d.page_count for d in documents)
        
        return DocumentsResponse(
            documents=documents,
            total_count=total_count,
            total_chunks=total_chunks,
            total_pages=total_pages,
        )
        
    except Exception as e:
        logger.error(f"Failed to get documents: {e}")
        # Return empty list on error
        return DocumentsResponse(
            documents=[],
            total_count=0,
            total_chunks=0,
            total_pages=0,
        )


@admin_router.delete("/documents/{document_id:path}")
async def delete_document(document_id: str):
    """
    Delete a document and its vectors from the knowledge base.
    
    Args:
        document_id: The universal doc_id (e.g., "a1b2c3d4_filename") or full path
    
    Deletes:
    - Vectors from Qdrant (by doc_id)
    - Original PDF from R2 (input-pdfs/{doc_id}.pdf)
    - Processed outputs from R2 (outputs/json/{doc_id}.json, outputs/md/{doc_id}.md)
    """
    deleted_vectors = 0
    deleted_r2_files = []
    errors = []
    
    # Extract doc_id from various input formats
    # Could be: "input-pdfs/a1b2c3d4_file.pdf" or "a1b2c3d4_file" or "a1b2c3d4_file.pdf"
    doc_id_parts = document_id.split("/")
    base_name = doc_id_parts[-1] if doc_id_parts else document_id
    doc_id = base_name.rsplit(".", 1)[0] if "." in base_name else base_name
    
    logger.info(f"Deleting document with doc_id: {doc_id} (from input: {document_id})")
    
    try:
        # 1. Delete from Qdrant
        try:
            indexer = QdrantIndexer()
            deleted_vectors = indexer.delete_by_document_id(doc_id)
            logger.info(f"Deleted {deleted_vectors} vectors for doc_id: {doc_id}")
        except Exception as e:
            errors.append(f"Qdrant delete failed: {str(e)}")
            logger.error(f"Failed to delete from Qdrant: {e}")
        
        # 2. Delete from R2 using consistent doc_id
        try:
            r2_client = get_r2_client()
            bucket_name = os.getenv("R2_BUCKET_NAME", "devchat-pdfs")
            
            # Use doc_id consistently for all R2 paths
            prefixes_to_check = [
                f"input-pdfs/{doc_id}.pdf",  # Original PDF
                f"input-pdfs/{doc_id}",  # In case extension varies
                f"outputs/json/{doc_id}.json",  # JSON output
                f"outputs/md/{doc_id}.md",  # Markdown output
            ]
            
            logger.info(f"Looking for R2 files with prefixes: {prefixes_to_check}")
            
            for prefix in prefixes_to_check:
                try:
                    # Use paginator to handle folders with many files
                    paginator = r2_client.get_paginator('list_objects_v2')
                    pages = paginator.paginate(
                        Bucket=bucket_name,
                        Prefix=prefix,
                    )
                    
                    for page in pages:
                        for obj in page.get("Contents", []):
                            try:
                                r2_client.delete_object(Bucket=bucket_name, Key=obj["Key"])
                                deleted_r2_files.append(obj["Key"])
                                logger.info(f"Deleted R2 file: {obj['Key']}")
                            except Exception as e:
                                errors.append(f"R2 delete failed for {obj['Key']}: {str(e)}")
                except Exception as e:
                    logger.warning(f"Could not list R2 prefix {prefix}: {e}")
                    
        except Exception as e:
            errors.append(f"R2 connection failed: {str(e)}")
            logger.error(f"Failed to connect to R2: {e}")
        
        success = deleted_vectors > 0 or len(deleted_r2_files) > 0
        
        return {
            "success": success,
            "doc_id": doc_id,
            "deleted": doc_id,
            "vectors_deleted": deleted_vectors,
            "r2_files_deleted": deleted_r2_files,
            "errors": errors if errors else None,
        }
        
    except Exception as e:
        logger.error(f"Delete document failed: {e}")
        raise HTTPException(status_code=500, detail=f"Delete failed: {str(e)}")


@admin_router.post("/documents/{document_id:path}/reprocess")
async def reprocess_document(document_id: str):
    """
    Reprocess a document (re-run MinerU and re-index).
    """
    # Extract doc_id from input
    doc_id_parts = document_id.split("/")
    base_name = doc_id_parts[-1] if doc_id_parts else document_id
    doc_id = base_name.rsplit(".", 1)[0] if "." in base_name else base_name
    
    logger.info(f"Reprocessing document with doc_id: {doc_id}")
    
    # TODO: Queue job in Modal with force_reindex=True
    return {
        "success": True, 
        "doc_id": doc_id,
        "job_id": f"job-reprocess-{doc_id}",
        "message": "Document queued for reprocessing"
    }


