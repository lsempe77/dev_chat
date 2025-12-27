"""
Admin Metadata Routes

Endpoints for metadata review and management (Zotero-compatible fields).
"""

import asyncio
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from qdrant_client.models import Filter, FieldCondition, MatchValue

from api.schemas import (
    DocumentMetadataDetail,
    MetadataReviewResponse,
    MetadataUpdateRequest,
    MetadataUpdateResponse,
)
from src.utils.logging import get_logger

from ..dependencies import (
    METADATA_CACHE_TTL,
    get_indexer,
    get_metadata_cache,
    invalidate_admin_caches,
)

logger = get_logger(__name__)

router = APIRouter()


# =============================================================================
# Metadata Review
# =============================================================================

@router.get("/metadata/review", response_model=MetadataReviewResponse)
async def get_metadata_for_review(
    filter_type: Optional[str] = Query(None, description="Filter: 'needs_review', 'low_confidence', or 'all'"),
    limit: int = Query(1000, ge=1, description="Max documents to return"),
    offset: int = Query(0, ge=0),
):
    """
    Get documents with metadata that needs review.
    
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
                    
                    # Get documents for review
                    docs = await DocumentRepository.get_for_review(
                        db,
                        filter_type=filter_type,
                        limit=limit,
                        offset=offset,
                    )
                    
                    # Get stats
                    stats = await DocumentRepository.get_stats(db)
                    
                    return MetadataReviewResponse(
                        documents=[
                            DocumentMetadataDetail(
                                id=d.id,
                                title=d.title,
                                filename=d.filename,
                                authors=d.authors or [],
                                year=d.year,
                                abstract=d.abstract,
                                item_type=d.item_type,
                                # Identifiers
                                doi=d.doi,
                                isbn=d.isbn,
                                issn=d.issn,
                                url=d.url,
                                # Publication
                                publication=d.publication,
                                journal=d.journal,
                                volume=d.volume,
                                issue=d.issue,
                                pages=d.pages,
                                edition=d.edition,
                                # Publisher
                                publisher=d.publisher,
                                place=d.place,
                                # Series
                                series=d.series,
                                series_number=d.series_number,
                                # Book
                                book_title=d.book_title,
                                num_pages=d.num_pages,
                                # Report/Thesis
                                institution=d.institution,
                                report_number=d.report_number,
                                report_type=d.report_type,
                                thesis_type=d.thesis_type,
                                # Conference
                                conference_name=d.conference_name,
                                proceedings_title=d.proceedings_title,
                                # Access
                                accessed_date=d.accessed_date,
                                # Metrics
                                cited_by_count=d.cited_by_count,
                                is_open_access=d.is_open_access,
                                # Classification
                                countries=d.countries or [],
                                sectors=d.sectors or [],
                                study_type=d.study_type,
                                intervention_type=d.intervention_type,
                                sdgs=d.sdgs or [],
                                keywords=d.keywords or [],
                                # Processing
                                metadata_source=d.metadata_source,
                                metadata_confidence=d.metadata_confidence,
                                needs_review=d.needs_review,
                                chunk_count=d.chunk_count or 0,
                                page_count=d.page_count or 0,
                                extra=d.extra,
                            )
                            for d in docs
                        ],
                        total_count=stats["total"],
                        needs_review_count=stats["needs_review"],
                        low_confidence_count=stats["low_confidence"],
                    )
        except Exception as e:
            logger.warning(f"PostgreSQL query failed, falling back to Qdrant: {e}")
    
    # Fallback to Qdrant (slow but works without Postgres)
    return await _get_metadata_for_review_from_qdrant(filter_type, limit, offset)


async def _get_metadata_for_review_from_qdrant(
    filter_type: Optional[str],
    limit: int,
    offset: int,
) -> MetadataReviewResponse:
    """Legacy Qdrant-based metadata review (slow but works without Postgres)."""
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
        
        # PRODUCTION OPTIMIZATION: Limit scan to prevent timeouts
        # With 413K+ vectors, scanning everything is too slow
        MAX_SCROLL_POINTS = 15000  # Scan 15K points (~30 seconds max)
        MAX_DOCS = 200  # Max unique documents to return
        
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
        elif filter_type == "all":
            # Show all documents without filtering
            filter_fn = lambda p: True
        else:
            # Default (None): Show anything that needs review OR has low confidence
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
        total_docs = len(doc_map)  # Total documents BEFORE filtering
        
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
        documents = documents[offset:offset + limit]
        
        response_payload = MetadataReviewResponse(
            documents=documents,
            total_count=total_docs,  # Always the total, not filtered count
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
            abstract=payload.get("abstract"),
            item_type=payload.get("item_type"),
            # Identifiers
            doi=payload.get("doi"),
            isbn=payload.get("isbn"),
            issn=payload.get("issn"),
            url=payload.get("url"),
            # Publication
            publication=payload.get("publication"),
            journal=payload.get("journal"),
            volume=payload.get("volume"),
            issue=payload.get("issue"),
            pages=payload.get("pages"),
            edition=payload.get("edition"),
            # Publisher
            publisher=payload.get("publisher"),
            place=payload.get("place"),
            # Series
            series=payload.get("series"),
            series_number=payload.get("series_number"),
            # Book
            book_title=payload.get("book_title"),
            num_pages=payload.get("num_pages"),
            # Report/Thesis
            institution=payload.get("institution"),
            report_number=payload.get("report_number"),
            report_type=payload.get("report_type"),
            thesis_type=payload.get("thesis_type"),
            # Conference
            conference_name=payload.get("conference_name"),
            proceedings_title=payload.get("proceedings_title"),
            # Access
            accessed_date=payload.get("accessed_date"),
            # Metrics
            cited_by_count=payload.get("cited_by_count"),
            is_open_access=payload.get("is_open_access", False),
            # Classification
            countries=payload.get("countries", []),
            sectors=payload.get("sectors", []),
            study_type=payload.get("study_type"),
            intervention_type=payload.get("intervention_type"),
            sdgs=payload.get("sdgs", []),
            keywords=payload.get("keywords", []),
            # Processing
            metadata_source=payload.get("metadata_source", "extraction"),
            metadata_confidence=payload.get("metadata_confidence", 0.0),
            needs_review=payload.get("needs_review", True),
            chunk_count=count_result.count,
            page_count=payload.get("page_count", 0),
            extra=payload.get("extra"),
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
    
    Updates PostgreSQL (primary) and Qdrant (vector payloads).
    """
    from ..dependencies import is_postgres_available, get_db_session
    
    try:
        # Clean up doc_id
        doc_id = document_id
        if "/" in doc_id:
            doc_id = doc_id.split("/")[-1]
        if doc_id.endswith(".pdf"):
            doc_id = doc_id[:-4]
        
        updated_chunks = 0
        
        # Update PostgreSQL first (primary source of truth)
        if is_postgres_available():
            try:
                db = await get_db_session()
                if db:
                    async with db:
                        from src.database.repository import DocumentRepository
                        
                        # Build update dict with all Zotero fields
                        update_data = {}
                        # Core
                        if update.title is not None:
                            update_data["title"] = update.title
                        if update.authors is not None:
                            update_data["authors"] = update.authors
                        if update.year is not None:
                            update_data["year"] = update.year
                        if update.abstract is not None:
                            update_data["abstract"] = update.abstract
                        if update.item_type is not None:
                            update_data["item_type"] = update.item_type
                        # Identifiers
                        if update.doi is not None:
                            update_data["doi"] = update.doi
                        if update.isbn is not None:
                            update_data["isbn"] = update.isbn
                        if update.issn is not None:
                            update_data["issn"] = update.issn
                        if update.url is not None:
                            update_data["url"] = update.url
                        # Publication
                        if update.publication is not None:
                            update_data["publication"] = update.publication
                        if update.journal is not None:
                            update_data["journal"] = update.journal
                        if update.volume is not None:
                            update_data["volume"] = update.volume
                        if update.issue is not None:
                            update_data["issue"] = update.issue
                        if update.pages is not None:
                            update_data["pages"] = update.pages
                        if update.edition is not None:
                            update_data["edition"] = update.edition
                        # Publisher
                        if update.publisher is not None:
                            update_data["publisher"] = update.publisher
                        if update.place is not None:
                            update_data["place"] = update.place
                        # Series
                        if update.series is not None:
                            update_data["series"] = update.series
                        if update.series_number is not None:
                            update_data["series_number"] = update.series_number
                        # Book
                        if update.book_title is not None:
                            update_data["book_title"] = update.book_title
                        if update.num_pages is not None:
                            update_data["num_pages"] = update.num_pages
                        # Report/Thesis
                        if update.institution is not None:
                            update_data["institution"] = update.institution
                        if update.report_number is not None:
                            update_data["report_number"] = update.report_number
                        if update.report_type is not None:
                            update_data["report_type"] = update.report_type
                        if update.thesis_type is not None:
                            update_data["thesis_type"] = update.thesis_type
                        # Conference
                        if update.conference_name is not None:
                            update_data["conference_name"] = update.conference_name
                        if update.proceedings_title is not None:
                            update_data["proceedings_title"] = update.proceedings_title
                        # Access
                        if update.accessed_date is not None:
                            update_data["accessed_date"] = update.accessed_date
                        # Classification
                        if update.countries is not None:
                            update_data["countries"] = update.countries
                        if update.sectors is not None:
                            update_data["sectors"] = update.sectors
                        if update.study_type is not None:
                            update_data["study_type"] = update.study_type
                        if update.intervention_type is not None:
                            update_data["intervention_type"] = update.intervention_type
                        if update.needs_review is not None:
                            update_data["needs_review"] = update.needs_review
                        # Extra
                        if update.extra is not None:
                            update_data["extra"] = update.extra
                        
                        # Mark as user-verified
                        update_data["metadata_source"] = "user"
                        update_data["metadata_confidence"] = 1.0
                        
                        # Update in PostgreSQL
                        doc = await DocumentRepository.update(db, doc_id, update_data)
                        if doc:
                            await db.commit()  # Commit the changes!
                            updated_chunks = doc.chunk_count or 0
                            logger.info(f"Updated PostgreSQL metadata for {doc_id}")
                        else:
                            logger.warning(f"Document {doc_id} not found in PostgreSQL")
            except Exception as e:
                logger.warning(f"PostgreSQL update failed: {e}")
        
        # Also update Qdrant payloads for consistency
        try:
            indexer = get_indexer()
            
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
                    with_payload=False,
                    with_vectors=False,
                )
                all_points.extend(results)
                if next_offset is None or len(results) == 0:
                    break
            
            if all_points:
                # Prepare payload update with all Zotero fields
                payload_update = {}
                # Core
                if update.title is not None:
                    payload_update["title"] = update.title
                if update.authors is not None:
                    payload_update["authors"] = update.authors
                if update.year is not None:
                    payload_update["year"] = update.year
                if update.abstract is not None:
                    payload_update["abstract"] = update.abstract
                if update.item_type is not None:
                    payload_update["item_type"] = update.item_type
                # Identifiers
                if update.doi is not None:
                    payload_update["doi"] = update.doi
                if update.isbn is not None:
                    payload_update["isbn"] = update.isbn
                if update.issn is not None:
                    payload_update["issn"] = update.issn
                if update.url is not None:
                    payload_update["url"] = update.url
                # Publication
                if update.publication is not None:
                    payload_update["publication"] = update.publication
                if update.journal is not None:
                    payload_update["journal"] = update.journal
                if update.volume is not None:
                    payload_update["volume"] = update.volume
                if update.issue is not None:
                    payload_update["issue"] = update.issue
                if update.pages is not None:
                    payload_update["pages"] = update.pages
                if update.edition is not None:
                    payload_update["edition"] = update.edition
                # Publisher
                if update.publisher is not None:
                    payload_update["publisher"] = update.publisher
                if update.place is not None:
                    payload_update["place"] = update.place
                # Series
                if update.series is not None:
                    payload_update["series"] = update.series
                if update.series_number is not None:
                    payload_update["series_number"] = update.series_number
                # Book
                if update.book_title is not None:
                    payload_update["book_title"] = update.book_title
                if update.num_pages is not None:
                    payload_update["num_pages"] = update.num_pages
                # Report/Thesis
                if update.institution is not None:
                    payload_update["institution"] = update.institution
                if update.report_number is not None:
                    payload_update["report_number"] = update.report_number
                if update.report_type is not None:
                    payload_update["report_type"] = update.report_type
                if update.thesis_type is not None:
                    payload_update["thesis_type"] = update.thesis_type
                # Conference
                if update.conference_name is not None:
                    payload_update["conference_name"] = update.conference_name
                if update.proceedings_title is not None:
                    payload_update["proceedings_title"] = update.proceedings_title
                # Access
                if update.accessed_date is not None:
                    payload_update["accessed_date"] = update.accessed_date
                # Classification
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
                
                payload_update["metadata_source"] = "user"
                payload_update["metadata_confidence"] = 1.0
                
                # Update all points
                point_ids = [str(p.id) for p in all_points]
                
                indexer.client.set_payload(
                    collection_name=indexer.collection_name,
                    payload=payload_update,
                    points=point_ids,
                )
                
                updated_chunks = len(point_ids)
                logger.info(f"Updated Qdrant metadata for {doc_id}: {len(point_ids)} chunks")
        except Exception as e:
            logger.warning(f"Qdrant update failed: {e}")
        
        if updated_chunks == 0:
            raise HTTPException(status_code=404, detail=f"Document not found: {doc_id}")
        
        invalidate_admin_caches()
        
        return MetadataUpdateResponse(
            success=True,
            document_id=doc_id,
            updated_chunks=updated_chunks,
            message=f"Updated metadata for {updated_chunks} chunks",
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update document metadata: {e}")
        raise HTTPException(status_code=500, detail=str(e))
