"""
Admin Collection Routes

Endpoints for Qdrant collection management, migrations, and indexing.
"""

import asyncio
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException

from api.schemas import (
    CollectionInfo,
    IngestRequest,
    IngestResponse,
)
from src.config.settings import settings
from src.utils.logging import get_logger

from ..dependencies import (
    COLLECTION_CACHE_TTL,
    get_collection_info_cache,
    get_indexer,
)

logger = get_logger(__name__)

router = APIRouter()


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


@router.post("/migrate/add-zotero-fields")
async def migrate_add_zotero_fields():
    """
    Add all Zotero-compatible columns to PostgreSQL documents table if they don't exist.
    Safe to call multiple times.
    """
    try:
        from ..dependencies import is_postgres_available, get_db_session
        from sqlalchemy import text
        
        if not is_postgres_available():
            return {"status": "skipped", "message": "PostgreSQL not available"}
        
        db = await get_db_session()
        try:
            # List of all Zotero-compatible columns to add
            columns = [
                ("item_type", "VARCHAR(100)"),
                ("volume", "VARCHAR(50)"),
                ("issue", "VARCHAR(50)"),
                ("pages", "VARCHAR(50)"),
                ("edition", "VARCHAR(50)"),
                ("isbn", "VARCHAR(50)"),
                ("issn", "VARCHAR(50)"),
                ("series", "VARCHAR(255)"),
                ("series_number", "VARCHAR(50)"),
                ("place", "VARCHAR(255)"),
                ("url", "TEXT"),
                ("accessed_date", "VARCHAR(50)"),
                ("abstract", "TEXT"),
                ("short_title", "VARCHAR(500)"),
                ("report_number", "VARCHAR(100)"),
                ("institution", "VARCHAR(500)"),
                ("thesis_type", "VARCHAR(100)"),
                ("conference_name", "VARCHAR(500)"),
                ("proceedings_title", "VARCHAR(500)"),
            ]
            
            added = []
            for col_name, col_type in columns:
                try:
                    await db.execute(text(f"ALTER TABLE documents ADD COLUMN IF NOT EXISTS {col_name} {col_type}"))
                    added.append(col_name)
                except Exception as col_error:
                    logger.warning(f"Could not add column {col_name}: {col_error}")
            
            await db.commit()
            logger.info(f"Migration: Zotero columns added successfully: {added}")
            return {"status": "success", "message": f"Zotero columns added: {added}"}
        finally:
            await db.close()
    except Exception as e:
        logger.error(f"Migration error: {e}")
        return {"status": "error", "message": str(e)}


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
