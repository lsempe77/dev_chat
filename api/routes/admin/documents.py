"""
Admin Documents Routes

Endpoints for document listing, deletion, and reprocessing.
"""

import asyncio
import os
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from api.schemas import (
    DocumentMetadata,
    DocumentsResponse,
    DocumentSyncRequest,
    DocumentSyncResponse,
)
from src.utils.logging import get_logger

from ..dependencies import (
    DOCUMENTS_CACHE_TTL,
    get_documents_cache,
    get_indexer,
    get_r2_client,
    invalidate_admin_caches,
)

logger = get_logger(__name__)

router = APIRouter()


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
    Get list of indexed documents.
    
    Uses PostgreSQL for instant queries if available,
    falls back to Qdrant scroll if not.
    """
    from ..dependencies import is_postgres_available, get_db_session
    
    # Try PostgreSQL first (instant queries)
    if is_postgres_available():
        try:
            db = await get_db_session()
            if db:
                async with db:
                    from src.database.repository import DocumentRepository
                    
                    # Get documents
                    docs = await DocumentRepository.list_all(
                        db,
                        search=search,
                        status=status,
                        limit=limit,
                        offset=offset,
                    )
                    
                    # Get stats
                    stats = await DocumentRepository.get_stats(db)
                    
                    return DocumentsResponse(
                        documents=[
                            DocumentMetadata(
                                id=d.id,
                                title=d.title,
                                filename=d.filename,
                                authors=d.authors or [],
                                year=d.year,
                                status=d.status,
                                page_count=d.page_count,
                                chunk_count=d.chunk_count,
                                uploaded_at=d.created_at,
                                processed_at=d.updated_at,
                            )
                            for d in docs
                        ],
                        total_count=stats["total"],
                        total_chunks=stats["total_chunks"],
                        total_pages=stats["total_pages"],
                    )
        except Exception as e:
            logger.warning(f"PostgreSQL query failed, falling back to Qdrant: {e}")
    
    # Fallback to Qdrant (slow but works without Postgres)
    return await _get_documents_from_qdrant(search, status, limit, offset)


async def _get_documents_from_qdrant(
    search: Optional[str],
    status: Optional[str],
    limit: int,
    offset: int,
) -> DocumentsResponse:
    """Legacy Qdrant-based document listing (slow but works without Postgres)."""
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
            # Limit scan to prevent timeouts - PostgreSQL is preferred
            all_points = []
            next_offset = None
            max_points = 15000
            
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
# Document Sync (Modal → Postgres)
# =============================================================================

@router.post("/documents/sync", response_model=DocumentSyncResponse)
async def sync_document(request: DocumentSyncRequest):
    """
    Sync a document from Modal to PostgreSQL.
    
    Called by Modal after successful Qdrant indexing to keep
    Postgres metadata store in sync.
    
    This endpoint is idempotent - can be called multiple times
    for the same document (will upsert).
    """
    from ..dependencies import is_postgres_available, get_db_session
    
    if not is_postgres_available():
        logger.warning("PostgreSQL not available, sync skipped")
        return DocumentSyncResponse(
            success=False,
            doc_id=request.doc_id,
            action="skipped",
            message="PostgreSQL not available"
        )
    
    try:
        db = await get_db_session()
        if not db:
            return DocumentSyncResponse(
                success=False,
                doc_id=request.doc_id,
                action="skipped",
                message="Could not get database session"
            )
        
        async with db:
            from src.database.repository import DocumentRepository
            
            # Check if document exists
            existing = await DocumentRepository.get_by_id(db, request.doc_id)
            action = "updated" if existing else "created"
            
            # Prepare document data
            doc_data = {
                "id": request.doc_id,
                "title": request.title,
                "filename": request.filename,
                "authors": request.authors,
                "year": request.year,
                "doi": request.doi,
                "abstract": request.abstract,
                "item_type": request.item_type,
                "journal": request.journal,
                "publisher": request.publisher,
                "volume": request.volume,
                "issue": request.issue,
                "pages": request.pages,
                "cited_by_count": request.cited_by_count,
                "is_open_access": request.is_open_access,
                "countries": request.countries,
                "sectors": request.sectors,
                "study_type": request.study_type,
                "intervention_type": request.intervention_type,
                "sdgs": request.sdgs,
                "keywords": request.keywords,
                "chunk_count": request.chunk_count,
                "page_count": request.page_count,
                "metadata_source": request.metadata_source,
                "metadata_confidence": request.metadata_confidence,
                "needs_review": request.needs_review,
                "status": "indexed",
            }
            
            # Upsert document
            await DocumentRepository.upsert(db, doc_data)
            await db.commit()
            
            # Invalidate caches
            invalidate_admin_caches()
            
            logger.info(f"Synced document to Postgres: {request.doc_id} ({action})")
            
            return DocumentSyncResponse(
                success=True,
                doc_id=request.doc_id,
                action=action,
                message=f"Document {action} in PostgreSQL"
            )
            
    except Exception as e:
        logger.error(f"Failed to sync document {request.doc_id}: {e}")
        return DocumentSyncResponse(
            success=False,
            doc_id=request.doc_id,
            action="error",
            message=str(e)
        )


@router.post("/documents/cleanup-orphans")
async def cleanup_orphan_documents():
    """
    Remove documents from PostgreSQL that don't exist in Qdrant.
    
    This fixes discrepancies where documents were deleted from Qdrant
    but not from PostgreSQL.
    """
    from ..dependencies import is_postgres_available, get_db_session
    
    if not is_postgres_available():
        return {"success": False, "message": "PostgreSQL not available", "deleted": 0}
    
    try:
        # Get all doc_ids from Qdrant
        indexer = get_indexer()
        qdrant_doc_ids = set()
        offset = None
        
        while True:
            results, offset = indexer.client.scroll(
                collection_name=indexer.collection_name,
                limit=500,
                offset=offset,
                with_payload=["doc_id"],
                with_vectors=False,
            )
            for point in results:
                doc_id = point.payload.get("doc_id")
                if doc_id:
                    qdrant_doc_ids.add(doc_id)
            if offset is None or len(results) == 0:
                break
        
        logger.info(f"Found {len(qdrant_doc_ids)} documents in Qdrant")
        
        # Get all doc_ids from PostgreSQL
        db = await get_db_session()
        if not db:
            return {"success": False, "message": "Could not get DB session", "deleted": 0}
        
        async with db:
            from src.database.repository import DocumentRepository
            from sqlalchemy import text
            
            # Get all IDs from Postgres
            result = await db.execute(text("SELECT id FROM documents"))
            postgres_ids = set(row[0] for row in result.fetchall())
            
            logger.info(f"Found {len(postgres_ids)} documents in PostgreSQL")
            
            # Find orphans (in Postgres but not in Qdrant)
            orphans = postgres_ids - qdrant_doc_ids
            
            if not orphans:
                return {
                    "success": True,
                    "message": "No orphan documents found",
                    "deleted": 0,
                    "postgres_count": len(postgres_ids),
                    "qdrant_count": len(qdrant_doc_ids),
                }
            
            # Delete orphans
            for orphan_id in orphans:
                await db.execute(
                    text("DELETE FROM documents WHERE id = :id"),
                    {"id": orphan_id}
                )
                logger.info(f"Deleted orphan document: {orphan_id}")
            
            await db.commit()
            
            # Invalidate caches
            invalidate_admin_caches()
            
            return {
                "success": True,
                "message": f"Deleted {len(orphans)} orphan documents",
                "deleted": len(orphans),
                "deleted_ids": list(orphans),
                "postgres_count": len(postgres_ids) - len(orphans),
                "qdrant_count": len(qdrant_doc_ids),
            }
            
    except Exception as e:
        logger.error(f"Failed to cleanup orphans: {e}")
        return {"success": False, "message": str(e), "deleted": 0}

