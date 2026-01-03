"""
DevChat v2.0 SOTA - Qdrant to Postgres Sync

Utility to sync document metadata from Qdrant to PostgreSQL.
Run this once after setting up the database, or when needed.
"""

import asyncio
import os
from typing import Dict, Any, List

from dotenv import load_dotenv

load_dotenv()


async def sync_qdrant_to_postgres(batch_size: int = 100) -> Dict[str, Any]:
    """
    Sync all documents from Qdrant to PostgreSQL.
    
    Scans Qdrant for unique doc_ids and creates/updates
    corresponding records in PostgreSQL.
    
    Returns:
        Dict with sync statistics
    """
    from src.database.connection import init_database, create_tables, get_db_context
    from src.database.repository import DocumentRepository
    from src.ingestion.indexer import QdrantIndexer
    from src.utils.logging import get_logger
    
    logger = get_logger(__name__)
    
    # Initialize database
    init_database()
    await create_tables()
    
    # Get Qdrant indexer
    indexer = QdrantIndexer()
    
    logger.info("Starting Qdrant → PostgreSQL sync...")
    
    # Scan all Qdrant points
    doc_map: Dict[str, Dict[str, Any]] = {}
    next_offset = None
    points_scanned = 0
    
    payload_fields = [
        "doc_id", "pdf_name", "source", "title", "authors", "year", "doi", 
        "journal", "publisher", "cited_by_count", "is_open_access", 
        "countries", "sectors", "study_type", "intervention_type", 
        "sdgs", "keywords", "metadata_source", "metadata_confidence", 
        "needs_review", "page"
    ]
    
    while True:
        results, next_offset = indexer.client.scroll(
            collection_name=indexer.collection_name,
            limit=1000,
            offset=next_offset,
            with_payload=payload_fields,
            with_vectors=False,
        )
        
        if not results:
            break
        
        points_scanned += len(results)
        
        for point in results:
            payload = point.payload or {}
            
            # Get doc_id
            doc_id = payload.get("doc_id") or payload.get("pdf_name") or payload.get("source", "unknown")
            if "/" in doc_id:
                doc_id = doc_id.split("/")[-1]
            if doc_id.endswith(".pdf"):
                doc_id = doc_id[:-4]
            
            if doc_id not in doc_map:
                # Handle authors
                authors = payload.get("authors")
                if isinstance(authors, str):
                    authors = [a.strip() for a in authors.split(",")]
                
                # Handle intervention_type
                intervention_type = payload.get("intervention_type")
                if isinstance(intervention_type, list):
                    intervention_type = ", ".join(intervention_type)
                
                # Handle study_type
                study_type = payload.get("study_type")
                if isinstance(study_type, list):
                    study_type = ", ".join(study_type)
                
                doc_map[doc_id] = {
                    "id": doc_id,
                    "title": payload.get("title", doc_id),
                    "filename": f"{doc_id}.pdf",
                    "authors": authors or [],
                    "year": payload.get("year"),
                    "doi": payload.get("doi"),
                    "journal": payload.get("journal"),
                    "publisher": payload.get("publisher"),
                    "cited_by_count": payload.get("cited_by_count"),
                    "is_open_access": payload.get("is_open_access"),
                    "countries": payload.get("countries") or [],
                    "sectors": payload.get("sectors") or [],
                    "study_type": study_type,
                    "intervention_type": intervention_type,
                    "sdgs": payload.get("sdgs") or [],
                    "keywords": payload.get("keywords") or [],
                    "chunk_count": 0,
                    "page_count": 0,
                    "metadata_source": payload.get("metadata_source"),
                    "metadata_confidence": payload.get("metadata_confidence", 0.0),
                    "needs_review": payload.get("needs_review", True),
                    "status": "indexed",
                }
            
            # Increment chunk count
            doc_map[doc_id]["chunk_count"] += 1
            
            # Track max page
            page = payload.get("page")
            if page:
                try:
                    doc_map[doc_id]["page_count"] = max(
                        doc_map[doc_id]["page_count"],
                        int(page)
                    )
                except (ValueError, TypeError):
                    pass
        
        if next_offset is None:
            break
        
        logger.info(f"Scanned {points_scanned} points, found {len(doc_map)} unique documents...")
    
    logger.info(f"Scan complete: {points_scanned} points, {len(doc_map)} documents")
    
    # Upsert to PostgreSQL
    async with get_db_context() as db:
        synced = await DocumentRepository.bulk_upsert(db, list(doc_map.values()))
    
    stats = {
        "points_scanned": points_scanned,
        "documents_found": len(doc_map),
        "documents_synced": synced,
    }
    
    logger.info(f"Sync complete: {stats}")
    return stats


async def main():
    """CLI entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Sync Qdrant to PostgreSQL")
    parser.add_argument("--batch-size", type=int, default=100, help="Batch size for upserts")
    args = parser.parse_args()
    
    stats = await sync_qdrant_to_postgres(batch_size=args.batch_size)
    print(f"\n✅ Sync complete!")
    print(f"   Points scanned: {stats['points_scanned']:,}")
    print(f"   Documents found: {stats['documents_found']:,}")
    print(f"   Documents synced: {stats['documents_synced']:,}")


if __name__ == "__main__":
    asyncio.run(main())
