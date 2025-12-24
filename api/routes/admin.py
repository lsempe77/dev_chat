"""
DevChat v2.0 SOTA - Admin Routes

Admin dashboard endpoints for document management, processing, and metadata.
"""

import asyncio
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import uuid4

import boto3
from botocore.exceptions import ClientError
from fastapi import APIRouter, BackgroundTasks, File, HTTPException, Query, UploadFile
from qdrant_client import models

from api.schemas import (
    AdminStatusResponse,
    CollectionInfo,
    DocumentMetadata,
    DocumentMetadataDetail,
    DocumentsResponse,
    IngestRequest,
    IngestResponse,
    MetadataReviewResponse,
    MetadataUpdateRequest,
    MetadataUpdateResponse,
    MetricsResponse,
    ProcessingJob,
    ProcessingJobsResponse,
    ServiceConnection,
    StorageStatus,
    TriggerProcessingRequest,
    TriggerProcessingResponse,
    UploadResponse,
)
from src.config.settings import settings
from src.utils.logging import get_logger
from src.utils.metrics import get_metrics_tracker

from .dependencies import (
    COLLECTION_CACHE_TTL,
    DOCUMENTS_CACHE_TTL,
    METADATA_CACHE_TTL,
    get_collection_info_cache,
    get_documents_cache,
    get_indexer,
    get_metadata_cache,
    get_r2_client,
    invalidate_admin_caches,
    trigger_modal_processing,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/admin", tags=["Admin"])


# =============================================================================
# Metrics Endpoints
# =============================================================================

@router.get("/metrics", response_model=MetricsResponse)
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


# =============================================================================
# Collection Management
# =============================================================================

@router.get("/collection")
async def get_collection_info():
    """Get vector collection information. Cached for 30 seconds."""
    cache = get_collection_info_cache()
    
    # Check cache first
    now = time.time()
    if cache["data"] and (now - cache["timestamp"]) < COLLECTION_CACHE_TTL:
        return cache["data"]
    
    try:
        # Wrap sync call with timeout to prevent hanging
        def _get_info():
            indexer = get_indexer()
            return indexer.get_collection_info()
        
        loop = asyncio.get_event_loop()
        info = await asyncio.wait_for(
            loop.run_in_executor(None, _get_info),
            timeout=8.0  # 8 second timeout
        )
        
        # Cache the result
        cache["data"] = info
        cache["timestamp"] = now
        
        return info
    except asyncio.TimeoutError:
        # Return cached data if available, even if stale
        if cache["data"]:
            return cache["data"]
        return {
            "error": "Qdrant connection timeout",
            "name": settings.qdrant_collection_name,
            "points_count": 0,
            "status": "timeout"
        }
    except Exception as e:
        logger.error(f"Collection info error: {e}")
        return {
            "error": str(e),
            "name": settings.qdrant_collection_name,
            "points_count": 0,
            "status": "error"
        }


@router.post("/indexes")
async def ensure_indexes():
    """
    Create or ensure all required payload indexes exist on the Qdrant collection.
    This enables efficient filtering by document_id, source, etc.
    Safe to call multiple times - will skip already existing indexes.
    """
    try:
        indexer = get_indexer()
        results = indexer.ensure_indexes()
        return {
            "success": True,
            "message": "Payload indexes ensured",
            "indexes": results,
        }
    except Exception as e:
        logger.error(f"Failed to ensure indexes: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sample-points")
async def sample_points(limit: int = 5):
    """
    Sample a few points from Qdrant to inspect payloads.
    Useful for debugging what fields are available for filtering/deletion.
    """
    try:
        indexer = get_indexer()
        points = indexer.sample_points(limit=limit)
        return {
            "count": len(points),
            "points": points,
        }
    except Exception as e:
        logger.error(f"Failed to sample points: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ingest", response_model=IngestResponse)
async def ingest_documents(request: IngestRequest):
    """
    Ingest documents into the vector database.
    
    This is an admin endpoint for re-indexing documents.
    """
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
# Admin Status
# =============================================================================

@router.get("/status", response_model=AdminStatusResponse)
async def get_admin_status():
    """
    Get admin dashboard status including storage and service connections.
    
    Performs real checks on all services with timeouts to prevent blocking.
    """
    connections = []
    storage_info = StorageStatus(
        bucket=os.getenv("R2_BUCKET_NAME", "devchat-pdfs"),
        input_path="/input-pdfs/",
        output_path="/outputs/",
        storage_used_bytes=0,
        file_count=0,
    )
    
    collection_cache = get_collection_info_cache()
    
    # Check R2 (with timeout)
    async def check_r2():
        try:
            loop = asyncio.get_event_loop()
            
            def _check():
                account_id = os.getenv("R2_ACCOUNT_ID", "667549da0201b12a53872d803b9880b6")
                access_key = os.getenv("R2_ACCESS_KEY_ID")
                secret_key = os.getenv("R2_SECRET_ACCESS_KEY")
                
                if not access_key or not secret_key:
                    return "disconnected", "No credentials", 0, 0
                
                client = boto3.client(
                    "s3",
                    endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
                    aws_access_key_id=access_key,
                    aws_secret_access_key=secret_key,
                    region_name="auto",
                )
                
                bucket = os.getenv("R2_BUCKET_NAME", "devchat-pdfs")
                # List objects to get count and size (limit to first 100 for speed)
                response = client.list_objects_v2(Bucket=bucket, Prefix="input-pdfs/", MaxKeys=100)
                
                file_count = response.get("KeyCount", 0)
                total_size = sum(obj.get("Size", 0) for obj in response.get("Contents", []))
                
                return "connected", bucket, file_count, total_size
            
            status, details, count, size = await asyncio.wait_for(
                loop.run_in_executor(None, _check),
                timeout=5.0
            )
            return status, details, count, size
        except asyncio.TimeoutError:
            return "timeout", "Connection timeout", 0, 0
        except Exception as e:
            logger.warning(f"R2 check failed: {e}")
            return "disconnected", str(e)[:50], 0, 0
    
    # Check Qdrant (use cached collection info)
    async def check_qdrant():
        try:
            # Use the cached collection info endpoint logic
            if collection_cache["data"] and collection_cache["data"].get("points_count"):
                info = collection_cache["data"]
                return "connected", f"{info['points_count']:,} vectors"
            
            # Try fresh check
            loop = asyncio.get_event_loop()
            
            def _check():
                indexer = get_indexer()
                info = indexer.get_collection_info()
                return info
            
            info = await asyncio.wait_for(
                loop.run_in_executor(None, _check),
                timeout=3.0
            )
            
            if "error" in info:
                return "disconnected", info["error"][:50]
            return "connected", f"{info.get('points_count', 0):,} vectors"
        except asyncio.TimeoutError:
            return "timeout", "Connection timeout"
        except Exception as e:
            logger.warning(f"Qdrant check failed: {e}")
            return "disconnected", str(e)[:50]
    
    # Check LLM (just verify API key exists)
    def check_llm():
        if settings.openrouter_api_key:
            return "connected", "OpenRouter (GPT-4o)"
        elif settings.openai_api_key:
            return "connected", "OpenAI"
        elif settings.anthropic_api_key:
            return "connected", "Anthropic"
        return "disconnected", "No API key"
    
    # Check Cohere
    def check_cohere():
        if settings.cohere_api_key:
            return "connected", "embed-v4.0"
        return "disconnected", "No API key"
    
    # Run checks in parallel
    r2_result, qdrant_result = await asyncio.gather(
        check_r2(),
        check_qdrant(),
    )
    
    r2_status, r2_details, file_count, total_size = r2_result
    qdrant_status, qdrant_details = qdrant_result
    llm_status, llm_details = check_llm()
    cohere_status, cohere_details = check_cohere()
    
    # Update storage info
    storage_info = StorageStatus(
        bucket=os.getenv("R2_BUCKET_NAME", "devchat-pdfs"),
        input_path="/input-pdfs/",
        output_path="/outputs/",
        storage_used_bytes=total_size,
        file_count=file_count,
    )
    
    connections = [
        ServiceConnection(name="Cloudflare R2", status=r2_status, details=r2_details),
        ServiceConnection(name="Qdrant Cloud", status=qdrant_status, details=qdrant_details),
        ServiceConnection(name="LLM Provider", status=llm_status, details=llm_details),
        ServiceConnection(name="Cohere API", status=cohere_status, details=cohere_details),
    ]
    
    return AdminStatusResponse(
        storage=storage_info,
        connections=connections,
        pending_jobs=0,  # TODO: Track actual job queue
        active_workers=1 if all(c.status == "connected" for c in connections) else 0,
    )


# =============================================================================
# File Upload and R2 Management
# =============================================================================

@router.post("/upload", response_model=UploadResponse)
async def upload_document(
    background_tasks: BackgroundTasks,
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
        invalidate_admin_caches()
        
        # Automatically trigger processing in background
        background_tasks.add_task(trigger_modal_processing, force_reprocess=False, max_documents=1)
        
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


@router.get("/r2/list")
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


@router.get("/pdf/{document_id:path}")
async def get_pdf_url(document_id: str):
    """
    Get a presigned URL to view a PDF document.
    
    Returns a temporary URL (valid for 1 hour) that can be used to view the PDF.
    """
    try:
        r2_client = get_r2_client()
        bucket_name = os.getenv("R2_BUCKET_NAME", "devchat-pdfs")
        
        # Try input-pdfs first (original uploaded PDF)
        r2_key = f"input-pdfs/{document_id}.pdf"
        
        # Check if file exists
        try:
            r2_client.head_object(Bucket=bucket_name, Key=r2_key)
        except ClientError:
            # Try without .pdf extension (in case document_id already has it)
            if document_id.endswith('.pdf'):
                r2_key = f"input-pdfs/{document_id}"
                try:
                    r2_client.head_object(Bucket=bucket_name, Key=r2_key)
                except ClientError:
                    raise HTTPException(status_code=404, detail=f"PDF not found: {document_id}")
            else:
                raise HTTPException(status_code=404, detail=f"PDF not found: {document_id}")
        
        # Generate presigned URL (valid for 1 hour)
        presigned_url = r2_client.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': bucket_name,
                'Key': r2_key,
            },
            ExpiresIn=3600,  # 1 hour
        )
        
        return {
            "document_id": document_id,
            "url": presigned_url,
            "expires_in": 3600,
            "r2_key": r2_key,
        }
        
    except HTTPException:
        raise
    except ClientError as e:
        logger.error(f"Failed to generate presigned URL: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get PDF URL: {str(e)}")


# =============================================================================
# Processing Jobs
# =============================================================================

@router.get("/jobs", response_model=ProcessingJobsResponse)
async def get_processing_jobs():
    """
    Get list of processing jobs with their status.
    
    Shows:
    - Pending: Files in R2 input-pdfs/ that are not yet indexed in Qdrant
    - Completed: Files that have been indexed in Qdrant
    """
    jobs = []
    documents_cache = get_documents_cache()
    
    try:
        # Get files from R2
        r2_client = get_r2_client()
        bucket_name = os.getenv("R2_BUCKET_NAME", "devchat-pdfs")
        
        r2_files = {}
        paginator = r2_client.get_paginator('list_objects_v2')
        for page in paginator.paginate(Bucket=bucket_name, Prefix="input-pdfs/"):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if key.endswith(".pdf"):
                    doc_id = key.split("/")[-1].rsplit(".", 1)[0]
                    r2_files[doc_id] = {
                        "key": key,
                        "size": obj.get("Size", 0),
                        "uploaded_at": obj.get("LastModified"),
                    }
        
        # Get indexed doc_ids from Qdrant
        indexed_doc_ids = set()
        
        # Optimization: Use cache if available
        if documents_cache["data"] is not None:
            # Extract IDs from cached response
            for doc in documents_cache["data"].documents:
                indexed_doc_ids.add(doc.id)
        else:
            # Fallback: Scroll through to get unique doc_ids
            try:
                indexer = get_indexer()
                next_offset = None
                # Limit scroll to avoid timeout - we might miss some if > 5000
                MAX_SCROLL = 5000
                count = 0
                
                while count < MAX_SCROLL:
                    results, next_offset = indexer.client.scroll(
                        collection_name=indexer.collection_name,
                        limit=100,
                        offset=next_offset,
                        with_payload=["doc_id", "pdf_name"],
                        with_vectors=False,
                    )
                    for point in results:
                        payload = point.payload or {}
                        doc_id = payload.get("doc_id") or payload.get("pdf_name")
                        if doc_id:
                            indexed_doc_ids.add(doc_id)
                    
                    count += len(results)
                    if next_offset is None or len(results) == 0:
                        break
            except Exception as e:
                logger.warning(f"Could not get indexed doc_ids: {e}")
        
        # Create job entries
        for doc_id, file_info in r2_files.items():
            is_indexed = doc_id in indexed_doc_ids
            jobs.append(ProcessingJob(
                id=f"job-{doc_id[:8]}",
                filename=file_info["key"].split("/")[-1],
                status="completed" if is_indexed else "queued",
                progress=100 if is_indexed else 0,
                started_at=file_info.get("uploaded_at"),
                completed_at=file_info.get("uploaded_at") if is_indexed else None,
                doc_id=doc_id,
            ))
        
        # Sort: queued first, then by filename
        jobs.sort(key=lambda j: (j.status != "queued", j.filename))
        
    except Exception as e:
        logger.error(f"Failed to get processing jobs: {e}")
        # Return empty list on error
        pass
    
    return ProcessingJobsResponse(
        jobs=jobs,
        queued_count=sum(1 for j in jobs if j.status == "queued"),
        processing_count=sum(1 for j in jobs if j.status == "processing"),
        completed_count=sum(1 for j in jobs if j.status == "completed"),
        failed_count=sum(1 for j in jobs if j.status == "failed"),
    )


@router.post("/jobs/trigger", response_model=TriggerProcessingResponse)
async def trigger_processing_endpoint(request: TriggerProcessingRequest):
    """
    Trigger batch processing of pending PDFs.
    
    Calls the Modal web endpoint to process new PDFs.
    This works from Railway (unlike subprocess which needs modal CLI).
    """
    # Use the helper function
    await trigger_modal_processing(
        force_reprocess=request.force_reprocess if hasattr(request, 'force_reprocess') else False,
        max_documents=request.max_documents or 10
    )
    
    return TriggerProcessingResponse(
        queued=1,  # We don't know exact count from async call, but we know it triggered
        skipped=0,
        message="Processing triggered successfully",
    )


# =============================================================================
# Document Management
# =============================================================================

@router.get("/documents", response_model=DocumentsResponse)
async def get_documents(
    search: Optional[str] = Query(None, description="Search query"),
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(1000, ge=1, description="Max documents to return"),
    offset: int = Query(0, ge=0),
):
    """
    Get list of indexed documents from Qdrant.
    
    Aggregates unique documents from vector payloads.
    Optimized: Limits scroll to avoid timeout with large collections.
    """
    documents_cache = get_documents_cache()
    
    try:
        # Serve from cache when requesting the common default view
        now_ts = asyncio.get_event_loop().time()
        if (
            search is None
            and status is None
            and offset == 0
            and limit <= 100
            and documents_cache["data"] is not None
            and (now_ts - documents_cache["timestamp"]) < DOCUMENTS_CACHE_TTL
        ):
            return documents_cache["data"]

        indexer = get_indexer()
        
        # Use executor with timeout to prevent blocking
        def _get_documents():
            # Scroll to get unique documents (not all chunks)
            # We only need one chunk per doc to get metadata
            # Limit scan to 10K points - should find all unique docs
            all_points = []
            next_offset = None
            max_points = 10000
            
            while len(all_points) < max_points:
                results, next_offset = indexer.client.scroll(
                    collection_name=indexer.collection_name,
                    limit=1000,  # Larger batches = fewer round trips
                    offset=next_offset,
                    with_payload=["doc_id", "pdf_name", "source", "title", "authors", "year", "page"],
                    with_vectors=False,
                )
                all_points.extend(results)
                if next_offset is None or len(results) == 0:
                    break
            
            # Aggregate by doc_id (universal document identifier)
            doc_map = {}
            for point in all_points:
                payload = point.payload or {}
                
                # Get doc_id - primary identifier
                doc_id = payload.get("doc_id") or payload.get("pdf_name") or payload.get("source", "unknown")
                
                # Extract doc_id from source path if needed
                if "/" in doc_id:
                    doc_id = doc_id.split("/")[-1]
                if doc_id.endswith(".pdf"):
                    doc_id = doc_id[:-4]
                
                if doc_id not in doc_map:
                    doc_map[doc_id] = {
                        "doc_id": doc_id,
                        "id": doc_id,
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
                    try:
                        doc_map[doc_id]["page_count"] = max(
                            doc_map[doc_id]["page_count"], 
                            int(payload.get("page", 0))
                        )
                    except (ValueError, TypeError):
                        pass
                
                # Get authors if available
                if payload.get("authors") and not doc_map[doc_id]["authors"]:
                    authors = payload.get("authors")
                    if isinstance(authors, list):
                        doc_map[doc_id]["authors"] = authors
                    elif isinstance(authors, str):
                        doc_map[doc_id]["authors"] = [authors]
            
            return doc_map
        
        # Run with timeout
        loop = asyncio.get_event_loop()
        doc_map = await asyncio.wait_for(
            loop.run_in_executor(None, _get_documents),
            timeout=30.0  # 30 second timeout
        )
        
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
                id=doc_data["doc_id"],
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
        
        # Sort by title
        documents.sort(key=lambda d: d.title.lower())
        
        # Apply pagination
        total_count = len(documents)
        documents = documents[offset:offset + limit]
        
        # Get total chunks from Qdrant count() - instant, no scanning
        try:
            count_result = indexer.client.count(collection_name=indexer.collection_name)
            total_chunks = count_result.count
        except Exception:
            total_chunks = sum(d.chunk_count for d in documents)
        
        total_pages = sum(d.page_count for d in documents)

        response_payload = DocumentsResponse(
            documents=documents,
            total_count=total_count,
            total_chunks=total_chunks,
            total_pages=total_pages,
        )

        # Cache only the default view (no filters/search, first page) to keep fresh
        if search is None and status is None and offset == 0 and limit <= 100:
            documents_cache["data"] = response_payload
            documents_cache["timestamp"] = asyncio.get_event_loop().time()
            documents_cache["search"] = search
            documents_cache["status"] = status
        
        return response_payload
        
    except asyncio.TimeoutError:
        logger.warning("Documents endpoint timed out")
        return DocumentsResponse(
            documents=[],
            total_count=0,
            total_chunks=0,
            total_pages=0,
        )
    except Exception as e:
        logger.error(f"Failed to get documents: {e}")
        return DocumentsResponse(
            documents=[],
            total_count=0,
            total_chunks=0,
            total_pages=0,
        )


@router.delete("/documents/{document_id:path}")
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
            indexer = get_indexer()
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
        invalidate_admin_caches()
        
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


@router.post("/documents/{document_id:path}/reprocess")
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


# =============================================================================
# Metadata Review
# =============================================================================

@router.get("/metadata/review", response_model=MetadataReviewResponse)
async def get_metadata_for_review(
    filter_type: Optional[str] = Query(None, description="Filter: 'needs_review' or 'low_confidence'"),
    limit: int = Query(1000, ge=1, description="Max documents to return"),
    offset: int = Query(0, ge=0),
):
    """
    Get documents with metadata that needs review.
    
    Returns documents with needs_review=True or low confidence scores.
    OPTIMIZED: Limits scrolling to prevent timeout with large collections.
    """
    metadata_cache = get_metadata_cache()
    
    try:
        # Serve cached snapshot for the default view to avoid repeat scrolls
        now_ts = asyncio.get_event_loop().time()
        if (
            offset == 0
            and limit <= 100
            and (filter_type in {None, "needs_review", "low_confidence"})
            and metadata_cache["data"] is not None
            and metadata_cache["filter"] == filter_type
            and (now_ts - metadata_cache["timestamp"]) < METADATA_CACHE_TTL
        ):
            return metadata_cache["data"]

        indexer = get_indexer()
        
        # PRODUCTION OPTIMIZATION: Limit how many points we scroll through
        MAX_SCROLL_POINTS = 5000  # Don't scroll through 48k+ vectors
        MAX_DOCS = 200  # We only need a sample for review
        
        # NOTE: Qdrant requires payload indexes for filtering.
        # Since needs_review may not be indexed, we scroll without filter
        # and do client-side filtering to avoid "Index required" errors.
        scroll_filter = None
        
        # Client-side filter functions
        def needs_review_check(payload):
            return payload.get("needs_review") is True or payload.get("needs_review") is None
        
        def low_confidence_check(payload):
            conf = payload.get("metadata_confidence")
            return conf is not None and conf < 0.5
        
        if filter_type == "needs_review":
            filter_fn = needs_review_check
        elif filter_type == "low_confidence":
            filter_fn = low_confidence_check
        else:
            # Default: Show anything that needs review OR has low confidence
            filter_fn = lambda p: needs_review_check(p) or low_confidence_check(p)

        # Scroll through points with limits
        doc_map = {}
        next_offset = None
        points_processed = 0
        
        # Only fetch necessary payload fields to reduce bandwidth
        payload_fields = [
            "doc_id", "pdf_name", "source", "title", "authors", "year", "doi", 
            "journal", "publisher", "cited_by_count", "is_open_access", 
            "countries", "sectors", "study_type", "intervention_type", 
            "sdgs", "keywords", "metadata_source", "metadata_confidence", 
            "needs_review"
        ]
        
        while points_processed < MAX_SCROLL_POINTS and len(doc_map) < MAX_DOCS:
            results, next_offset = indexer.client.scroll(
                collection_name=indexer.collection_name,
                scroll_filter=scroll_filter,
                limit=100,
                offset=next_offset,
                with_payload=payload_fields,
                with_vectors=False,
            )
            
            if not results:
                break
                
            points_processed += len(results)
            
            # Process points immediately (with client-side filtering)
            for point in results:
                payload = point.payload or {}
                
                # Apply client-side filter
                if not filter_fn(payload):
                    continue
                
                doc_id = payload.get("doc_id") or payload.get("pdf_name") or payload.get("source", "unknown")
                if "/" in doc_id:
                    doc_id = doc_id.split("/")[-1]
                if doc_id.endswith(".pdf"):
                    doc_id = doc_id[:-4]
                
                if doc_id not in doc_map:
                    # Handle intervention_type - could be string or list
                    intervention_type_raw = payload.get("intervention_type")
                    if isinstance(intervention_type_raw, list):
                        intervention_type = ", ".join(intervention_type_raw) if intervention_type_raw else None
                    else:
                        intervention_type = intervention_type_raw
                    
                    # Handle study_type - could be string or list
                    study_type_raw = payload.get("study_type")
                    if isinstance(study_type_raw, list):
                        study_type = ", ".join(study_type_raw) if study_type_raw else None
                    else:
                        study_type = study_type_raw
                    
                    doc_map[doc_id] = {
                        "id": doc_id,
                        "title": payload.get("title", doc_id),
                        "filename": f"{doc_id}.pdf",
                        "authors": [],
                        "year": payload.get("year"),
                        "doi": payload.get("doi"),
                        "journal": payload.get("journal"),
                        "publisher": payload.get("publisher"),
                        "cited_by_count": payload.get("cited_by_count"),
                        "is_open_access": payload.get("is_open_access", False),
                        "countries": payload.get("countries", []),
                        "sectors": payload.get("sectors", []),
                        "study_type": study_type,
                        "intervention_type": intervention_type,
                        "sdgs": payload.get("sdgs", []),
                        "keywords": payload.get("keywords", []),
                        "metadata_source": payload.get("metadata_source", "extraction"),
                        "metadata_confidence": payload.get("metadata_confidence", 0.0),
                        "needs_review": payload.get("needs_review", True),
                        "chunk_count": 0,
                    }
                
                doc_map[doc_id]["chunk_count"] += 1
                
                # Get authors if available
                if payload.get("authors") and not doc_map[doc_id]["authors"]:
                    authors = payload.get("authors")
                    if isinstance(authors, list):
                        doc_map[doc_id]["authors"] = authors
                    elif isinstance(authors, str):
                        doc_map[doc_id]["authors"] = [a.strip() for a in authors.split(",")]
            
            # Check exit conditions
            if next_offset is None:
                break
        
        # Filter documents
        documents = []
        needs_review_count = 0
        low_confidence_count = 0
        
        for doc_data in doc_map.values():
            # Count stats
            if doc_data["needs_review"]:
                needs_review_count += 1
            if doc_data["metadata_confidence"] < 0.5:
                low_confidence_count += 1
            
            # Apply filter
            if filter_type == "needs_review" and not doc_data["needs_review"]:
                continue
            elif filter_type == "low_confidence" and doc_data["metadata_confidence"] >= 0.5:
                continue
            
            documents.append(DocumentMetadataDetail(**doc_data))
        
        # Sort by confidence (lowest first)
        documents.sort(key=lambda d: d.metadata_confidence)
        
        # Apply pagination
        total_count = len(documents)
        documents = documents[offset:offset + limit]
        
        response_payload = MetadataReviewResponse(
            documents=documents,
            total_count=total_count,
            needs_review_count=needs_review_count,
            low_confidence_count=low_confidence_count,
        )

        # Cache default views briefly to smooth tab switching
        if offset == 0 and limit <= 100 and filter_type in {None, "needs_review", "low_confidence"}:
            metadata_cache["data"] = response_payload
            metadata_cache["timestamp"] = asyncio.get_event_loop().time()
            metadata_cache["filter"] = filter_type
        
        return response_payload
        
    except Exception as e:
        logger.error(f"Failed to get metadata for review: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/metadata/{document_id:path}", response_model=DocumentMetadataDetail)
async def get_document_metadata(document_id: str):
    """Get detailed metadata for a specific document."""
    try:
        indexer = get_indexer()
        
        # Clean up doc_id
        doc_id = document_id
        if "/" in doc_id:
            doc_id = doc_id.split("/")[-1]
        if doc_id.endswith(".pdf"):
            doc_id = doc_id[:-4]
        
        from qdrant_client.models import Filter, FieldCondition, MatchValue
        
        results = indexer.client.scroll(
            collection_name=indexer.collection_name,
            scroll_filter=Filter(
                must=[
                    FieldCondition(key="doc_id", match=MatchValue(value=doc_id))
                ]
            ),
            limit=1,
            with_payload=True,
            with_vectors=False,
        )[0]
        
        if not results:
            raise HTTPException(status_code=404, detail=f"Document not found: {doc_id}")
        
        payload = results[0].payload or {}
        
        # Count total chunks
        count_result = indexer.client.count(
            collection_name=indexer.collection_name,
            count_filter=Filter(
                must=[
                    FieldCondition(key="doc_id", match=MatchValue(value=doc_id))
                ]
            ),
        )
        
        authors = payload.get("authors", [])
        if isinstance(authors, str):
            authors = [a.strip() for a in authors.split(",")]
        
        return DocumentMetadataDetail(
            id=doc_id,
            title=payload.get("title", doc_id),
            filename=f"{doc_id}.pdf",
            authors=authors,
            year=payload.get("year"),
            doi=payload.get("doi"),
            journal=payload.get("journal"),
            publisher=payload.get("publisher"),
            cited_by_count=payload.get("cited_by_count"),
            is_open_access=payload.get("is_open_access", False),
            countries=payload.get("countries", []),
            sectors=payload.get("sectors", []),
            study_type=payload.get("study_type"),
            intervention_type=payload.get("intervention_type"),
            sdgs=payload.get("sdgs", []),
            keywords=payload.get("keywords", []),
            metadata_source=payload.get("metadata_source", "extraction"),
            metadata_confidence=payload.get("metadata_confidence", 0.0),
            needs_review=payload.get("needs_review", True),
            chunk_count=count_result.count,
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get document metadata: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/metadata/{document_id:path}", response_model=MetadataUpdateResponse)
async def update_document_metadata(document_id: str, update: MetadataUpdateRequest):
    """
    Update metadata for a document.
    
    Updates all chunks belonging to this document in Qdrant.
    """
    try:
        indexer = get_indexer()
        
        # Clean up doc_id
        doc_id = document_id
        if "/" in doc_id:
            doc_id = doc_id.split("/")[-1]
        if doc_id.endswith(".pdf"):
            doc_id = doc_id[:-4]
        
        from qdrant_client.models import Filter, FieldCondition, MatchValue
        
        # Get all points for this document
        all_points = []
        next_offset = None
        
        while True:
            results, next_offset = indexer.client.scroll(
                collection_name=indexer.collection_name,
                scroll_filter=Filter(
                    must=[
                        FieldCondition(key="doc_id", match=MatchValue(value=doc_id))
                    ]
                ),
                limit=100,
                offset=next_offset,
                with_payload=True,
                with_vectors=False,
            )
            all_points.extend(results)
            if next_offset is None or len(results) == 0:
                break
        
        if not all_points:
            raise HTTPException(status_code=404, detail=f"Document not found: {doc_id}")
        
        # Prepare payload update
        payload_update = {}
        if update.title is not None:
            payload_update["title"] = update.title
        if update.authors is not None:
            payload_update["authors"] = update.authors
        if update.year is not None:
            payload_update["year"] = update.year
        if update.doi is not None:
            payload_update["doi"] = update.doi
        if update.journal is not None:
            payload_update["journal"] = update.journal
        if update.countries is not None:
            payload_update["countries"] = update.countries
        if update.sectors is not None:
            payload_update["sectors"] = update.sectors
        if update.study_type is not None:
            payload_update["study_type"] = update.study_type
        if update.intervention_type is not None:
            payload_update["intervention_type"] = update.intervention_type
        if update.needs_review is not None:
            payload_update["needs_review"] = update.needs_review
        
        # Mark as user-verified
        payload_update["metadata_source"] = "user"
        payload_update["metadata_confidence"] = 1.0  # User-verified is highest confidence
        
        # Update all points
        point_ids = [str(p.id) for p in all_points]
        
        indexer.client.set_payload(
            collection_name=indexer.collection_name,
            payload=payload_update,
            points=point_ids,
        )
        
        logger.info(f"Updated metadata for {doc_id}: {len(point_ids)} chunks")
        invalidate_admin_caches()
        
        return MetadataUpdateResponse(
            success=True,
            document_id=doc_id,
            updated_chunks=len(point_ids),
            message=f"Updated metadata for {len(point_ids)} chunks",
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update document metadata: {e}")
        raise HTTPException(status_code=500, detail=str(e))
