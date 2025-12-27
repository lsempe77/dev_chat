"""
DevChat v2.0 SOTA - Document Repository

CRUD operations for document metadata in PostgreSQL.
Provides fast queries that replace Qdrant scroll operations.
"""

from datetime import datetime
from typing import List, Optional, Dict, Any

from sqlalchemy import select, func, update, delete, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Document
from src.utils.logging import get_logger

logger = get_logger(__name__)


class DocumentRepository:
    """
    Repository for document metadata operations.
    
    All methods are static and require an AsyncSession parameter.
    This makes them easy to use with FastAPI's Depends().
    """

    # =========================================================================
    # READ Operations
    # =========================================================================

    @staticmethod
    async def get_by_id(db: AsyncSession, doc_id: str) -> Optional[Document]:
        """Get a single document by ID."""
        result = await db.execute(
            select(Document).where(Document.id == doc_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_all(
        db: AsyncSession,
        *,
        search: Optional[str] = None,
        status: Optional[str] = None,
        needs_review: Optional[bool] = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> List[Document]:
        """
        List documents with optional filtering.
        
        This replaces the slow Qdrant scroll + aggregation.
        ~5ms for 1000 docs vs ~2s for Qdrant scroll.
        """
        query = select(Document)
        
        # Apply filters
        conditions = []
        
        if search:
            search_lower = f"%{search.lower()}%"
            conditions.append(
                or_(
                    func.lower(Document.title).like(search_lower),
                    func.lower(Document.filename).like(search_lower),
                    func.lower(Document.id).like(search_lower),
                )
            )
        
        if status:
            conditions.append(Document.status == status)
        
        if needs_review is not None:
            conditions.append(Document.needs_review == needs_review)
        
        if conditions:
            query = query.where(and_(*conditions))
        
        # Order and paginate
        query = query.order_by(Document.title).offset(offset).limit(limit)
        
        result = await db.execute(query)
        return list(result.scalars().all())

    @staticmethod
    async def count(
        db: AsyncSession,
        *,
        needs_review: Optional[bool] = None,
        status: Optional[str] = None,
    ) -> int:
        """Count documents with optional filtering."""
        query = select(func.count(Document.id))
        
        if needs_review is not None:
            query = query.where(Document.needs_review == needs_review)
        
        if status:
            query = query.where(Document.status == status)
        
        result = await db.execute(query)
        return result.scalar() or 0

    @staticmethod
    async def get_stats(db: AsyncSession) -> Dict[str, int]:
        """Get document statistics (counts by status, needs_review, etc.)."""
        total = await DocumentRepository.count(db)
        needs_review_count = await DocumentRepository.count(db, needs_review=True)
        
        # Low confidence count
        low_conf_query = select(func.count(Document.id)).where(
            Document.metadata_confidence < 0.5
        )
        low_conf_result = await db.execute(low_conf_query)
        low_confidence_count = low_conf_result.scalar() or 0
        
        # Total chunks
        chunks_query = select(func.sum(Document.chunk_count))
        chunks_result = await db.execute(chunks_query)
        total_chunks = chunks_result.scalar() or 0
        
        # Total pages
        pages_query = select(func.sum(Document.page_count))
        pages_result = await db.execute(pages_query)
        total_pages = pages_result.scalar() or 0
        
        return {
            "total": total,
            "needs_review": needs_review_count,
            "low_confidence": low_confidence_count,
            "total_chunks": total_chunks,
            "total_pages": total_pages,
        }

    @staticmethod
    async def get_for_review(
        db: AsyncSession,
        *,
        filter_type: Optional[str] = None,  # "needs_review", "low_confidence", "all"
        limit: int = 1000,
        offset: int = 0,
    ) -> List[Document]:
        """Get documents needing metadata review."""
        query = select(Document)
        
        if filter_type == "needs_review":
            query = query.where(Document.needs_review == True)
        elif filter_type == "low_confidence":
            query = query.where(Document.metadata_confidence < 0.5)
        elif filter_type != "all":
            # Default: needs_review OR low_confidence
            query = query.where(
                or_(
                    Document.needs_review == True,
                    Document.metadata_confidence < 0.5,
                )
            )
        
        # Order by confidence (lowest first) so worst metadata appears first
        query = query.order_by(Document.metadata_confidence).offset(offset).limit(limit)
        
        result = await db.execute(query)
        return list(result.scalars().all())

    # =========================================================================
    # WRITE Operations
    # =========================================================================

    @staticmethod
    async def create(db: AsyncSession, doc_data: Dict[str, Any]) -> Document:
        """Create a new document."""
        doc = Document(**doc_data)
        db.add(doc)
        await db.flush()
        await db.refresh(doc)
        logger.info(f"Created document: {doc.id}")
        return doc

    @staticmethod
    async def upsert(db: AsyncSession, doc_data: Dict[str, Any]) -> Document:
        """Create or update a document."""
        doc_id = doc_data.get("id")
        if not doc_id:
            raise ValueError("Document ID is required for upsert")
        
        existing = await DocumentRepository.get_by_id(db, doc_id)
        
        if existing:
            # Update existing
            for key, value in doc_data.items():
                if hasattr(existing, key) and key != "id":
                    setattr(existing, key, value)
            existing.updated_at = datetime.utcnow()
            await db.flush()
            await db.refresh(existing)
            logger.info(f"Updated document: {doc_id}")
            return existing
        else:
            # Create new
            return await DocumentRepository.create(db, doc_data)

    @staticmethod
    async def update(
        db: AsyncSession,
        doc_id: str,
        updates: Dict[str, Any],
    ) -> Optional[Document]:
        """Update a document's metadata."""
        doc = await DocumentRepository.get_by_id(db, doc_id)
        
        if not doc:
            return None
        
        for key, value in updates.items():
            if hasattr(doc, key) and key != "id":
                setattr(doc, key, value)
        
        doc.updated_at = datetime.utcnow()
        await db.flush()
        await db.refresh(doc)
        logger.info(f"Updated document: {doc_id}")
        return doc

    @staticmethod
    async def delete(db: AsyncSession, doc_id: str) -> bool:
        """Delete a document."""
        result = await db.execute(
            delete(Document).where(Document.id == doc_id)
        )
        deleted = result.rowcount > 0
        if deleted:
            logger.info(f"Deleted document: {doc_id}")
        return deleted

    @staticmethod
    async def bulk_upsert(
        db: AsyncSession,
        documents: List[Dict[str, Any]],
    ) -> int:
        """Bulk upsert documents. Returns count of upserted docs."""
        count = 0
        for doc_data in documents:
            try:
                await DocumentRepository.upsert(db, doc_data)
                count += 1
            except Exception as e:
                logger.error(f"Failed to upsert document {doc_data.get('id')}: {e}")
        
        logger.info(f"Bulk upserted {count}/{len(documents)} documents")
        return count

    # =========================================================================
    # Sync Operations (Qdrant ↔ Postgres)
    # =========================================================================

    @staticmethod
    async def sync_from_qdrant_payload(
        db: AsyncSession,
        doc_id: str,
        payload: Dict[str, Any],
        chunk_count: int = 1,
    ) -> Document:
        """
        Sync a document from Qdrant payload.
        
        Called when processing PDFs to keep Postgres in sync.
        """
        # Handle authors - could be string or list
        authors = payload.get("authors")
        if isinstance(authors, str):
            authors = [a.strip() for a in authors.split(",")]
        
        # Handle intervention_type - could be string or list
        intervention_type = payload.get("intervention_type")
        if isinstance(intervention_type, list):
            intervention_type = ", ".join(intervention_type)
        
        doc_data = {
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
            "study_type": payload.get("study_type"),
            "intervention_type": intervention_type,
            "sdgs": payload.get("sdgs") or [],
            "keywords": payload.get("keywords") or [],
            "chunk_count": chunk_count,
            "page_count": payload.get("page") or 0,
            "metadata_source": payload.get("metadata_source"),
            "metadata_confidence": payload.get("metadata_confidence", 0.0),
            "needs_review": payload.get("needs_review", True),
            "status": "indexed",
        }
        
        return await DocumentRepository.upsert(db, doc_data)

    # =========================================================================
    # Search Operations
    # =========================================================================

    @staticmethod
    async def find_by_title_fuzzy(
        db: AsyncSession,
        title: str,
        threshold: float = 0.8,
    ) -> Optional[Document]:
        """
        Find a document with a similar title (fuzzy match).
        
        Uses case-insensitive LIKE for now.
        For better fuzzy matching, could use pg_trgm extension.
        """
        if not title:
            return None
        
        # Normalize title for comparison
        normalized = title.lower().strip()
        
        # First try exact match
        result = await db.execute(
            select(Document).where(
                func.lower(Document.title) == normalized
            )
        )
        doc = result.scalar_one_or_none()
        if doc:
            return doc
        
        # Try LIKE with first 50 chars (handles slight variations)
        prefix = normalized[:50]
        result = await db.execute(
            select(Document).where(
                func.lower(Document.title).like(f"{prefix}%")
            ).limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def find_by_doi(db: AsyncSession, doi: str) -> Optional[Document]:
        """Find a document by DOI."""
        if not doi:
            return None
        
        result = await db.execute(
            select(Document).where(
                func.lower(Document.doi) == doi.lower().strip()
            )
        )
        return result.scalar_one_or_none()
