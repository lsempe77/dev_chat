"""
RAG Project Management API Routes

Allows authenticated users to create, list, update, and delete their RAG projects.
Each RAG project corresponds to a separate Qdrant collection.
"""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from src.auth import AuthenticatedUser, get_current_user, get_supabase_client, is_multi_tenant_enabled
from src.utils.logging import get_logger
from src.ingestion.indexer import QdrantIndexer
from src.config.settings import settings

logger = get_logger(__name__)

router = APIRouter(prefix="/rags", tags=["RAG Projects"])


# =============================================================================
# Pydantic Models
# =============================================================================

class RAGProjectCreate(BaseModel):
    """Request to create a new RAG project."""
    name: str = Field(..., min_length=1, max_length=100, description="Project name")
    description: Optional[str] = Field(None, max_length=500, description="Project description")
    slug: Optional[str] = Field(None, max_length=50, description="URL-friendly identifier")
    is_public: bool = Field(default=False, description="Whether the RAG is publicly accessible")


class RAGProjectUpdate(BaseModel):
    """Request to update a RAG project."""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    slug: Optional[str] = Field(None, max_length=50)
    is_public: Optional[bool] = None


class RAGProjectResponse(BaseModel):
    """Response for a RAG project."""
    id: str
    name: str
    description: Optional[str]
    slug: Optional[str]
    qdrant_collection: str
    is_public: bool
    status: str
    document_count: int
    chunk_count: int
    created_at: datetime
    updated_at: datetime


class RAGProjectListResponse(BaseModel):
    """Response for listing RAG projects."""
    projects: List[RAGProjectResponse]
    total: int


class RAGProjectDetailResponse(RAGProjectResponse):
    """Detailed response for a single RAG project."""
    # Additional stats can be added here
    pass


# =============================================================================
# Helper Functions
# =============================================================================

async def get_user_project(user: AuthenticatedUser, project_id: str) -> dict:
    """
    Get a RAG project owned by the user.
    
    Raises HTTPException if not found or not owned by user.
    """
    client = get_supabase_client()
    
    result = client.table("rag_projects").select("*").eq("id", project_id).eq("user_id", user.id).single().execute()
    
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="RAG project not found"
        )
    
    return result.data


# =============================================================================
# Endpoints
# =============================================================================

@router.get("", response_model=RAGProjectListResponse)
async def list_rag_projects(
    user: AuthenticatedUser = Depends(get_current_user),
) -> RAGProjectListResponse:
    """
    List all RAG projects owned by the current user.
    """
    client = get_supabase_client()
    
    result = client.table("rag_projects").select("*").eq("user_id", user.id).order("created_at", desc=True).execute()
    
    projects = [
        RAGProjectResponse(
            id=str(p["id"]),
            name=p["name"],
            description=p.get("description"),
            slug=p.get("slug"),
            qdrant_collection=p["qdrant_collection"],
            is_public=p.get("is_public", False),
            status=p["status"],
            document_count=p.get("document_count", 0),
            chunk_count=p.get("chunk_count", 0),
            created_at=p["created_at"],
            updated_at=p["updated_at"],
        )
        for p in result.data or []
    ]
    
    return RAGProjectListResponse(projects=projects, total=len(projects))


@router.post("", response_model=RAGProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_rag_project(
    request: RAGProjectCreate,
    user: AuthenticatedUser = Depends(get_current_user),
) -> RAGProjectResponse:
    """
    Create a new RAG project.
    
    This will:
    1. Create a database record
    2. Create a new Qdrant collection for the project
    """
    client = get_supabase_client()
    
    # Check for duplicate name
    existing = client.table("rag_projects").select("id").eq("user_id", user.id).eq("name", request.name).execute()
    
    if existing.data:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A RAG project named '{request.name}' already exists"
        )
    
    try:
        # Create the project record (qdrant_collection is auto-generated by trigger)
        result = client.table("rag_projects").insert({
            "user_id": user.id,
            "name": request.name,
            "description": request.description,
            "slug": request.slug,
            "is_public": request.is_public,
        }).execute()
        
        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create RAG project"
            )
        
        project = result.data[0]
        collection_name = project["qdrant_collection"]
        
        # Create the Qdrant collection
        try:
            indexer = QdrantIndexer(
                collection_name=collection_name,
                url=settings.qdrant_url,
                api_key=settings.qdrant_api_key,
            )
            # This will create the collection if it doesn't exist
            await indexer.ensure_collection_exists()
            logger.info(f"Created Qdrant collection: {collection_name}")
        except Exception as e:
            # Rollback the database record
            client.table("rag_projects").delete().eq("id", project["id"]).execute()
            logger.error(f"Failed to create Qdrant collection: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create vector store collection"
            )
        
        return RAGProjectResponse(
            id=str(project["id"]),
            name=project["name"],
            description=project.get("description"),
            slug=project.get("slug"),
            qdrant_collection=project["qdrant_collection"],
            is_public=project.get("is_public", False),
            status=project["status"],
            document_count=0,
            chunk_count=0,
            created_at=project["created_at"],
            updated_at=project["updated_at"],
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating RAG project: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create RAG project"
        )


@router.get("/{project_id}", response_model=RAGProjectDetailResponse)
async def get_rag_project(
    project_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
) -> RAGProjectDetailResponse:
    """
    Get details of a specific RAG project.
    """
    project = await get_user_project(user, project_id)
    
    return RAGProjectDetailResponse(
        id=str(project["id"]),
        name=project["name"],
        description=project.get("description"),
        slug=project.get("slug"),
        qdrant_collection=project["qdrant_collection"],
        is_public=project.get("is_public", False),
        status=project["status"],
        document_count=project.get("document_count", 0),
        chunk_count=project.get("chunk_count", 0),
        created_at=project["created_at"],
        updated_at=project["updated_at"],
    )


@router.patch("/{project_id}", response_model=RAGProjectResponse)
async def update_rag_project(
    project_id: str,
    request: RAGProjectUpdate,
    user: AuthenticatedUser = Depends(get_current_user),
) -> RAGProjectResponse:
    """
    Update a RAG project's name or description.
    """
    # Verify ownership
    await get_user_project(user, project_id)
    
    client = get_supabase_client()
    
    update_data = {}
    if request.name is not None:
        # Check for duplicate name
        existing = client.table("rag_projects").select("id").eq("user_id", user.id).eq("name", request.name).neq("id", project_id).execute()
        if existing.data:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"A RAG project named '{request.name}' already exists"
            )
        update_data["name"] = request.name
    
    if request.description is not None:
        update_data["description"] = request.description
    
    if request.slug is not None:
        # Check for duplicate slug
        if request.slug:
            existing = client.table("rag_projects").select("id").eq("slug", request.slug).neq("id", project_id).execute()
            if existing.data:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"A RAG project with slug '{request.slug}' already exists"
                )
        update_data["slug"] = request.slug if request.slug else None
    
    if request.is_public is not None:
        update_data["is_public"] = request.is_public
    
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update"
        )
    
    result = client.table("rag_projects").update(update_data).eq("id", project_id).execute()
    
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update project"
        )
    
    project = result.data[0]
    
    return RAGProjectResponse(
        id=str(project["id"]),
        name=project["name"],
        description=project.get("description"),
        slug=project.get("slug"),
        qdrant_collection=project["qdrant_collection"],
        is_public=project.get("is_public", False),
        status=project["status"],
        document_count=project.get("document_count", 0),
        chunk_count=project.get("chunk_count", 0),
        created_at=project["created_at"],
        updated_at=project["updated_at"],
    )


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rag_project(
    project_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Delete a RAG project.
    
    This will:
    1. Delete the Qdrant collection
    2. Delete all associated documents from R2
    3. Delete the database record
    """
    project = await get_user_project(user, project_id)
    collection_name = project["qdrant_collection"]
    
    client = get_supabase_client()
    
    # Delete Qdrant collection
    try:
        indexer = QdrantIndexer(
            collection_name=collection_name,
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key,
        )
        await indexer.delete_collection()
        logger.info(f"Deleted Qdrant collection: {collection_name}")
    except Exception as e:
        logger.warning(f"Failed to delete Qdrant collection {collection_name}: {e}")
        # Continue anyway - collection might not exist
    
    # TODO: Delete R2 files for this project
    # This would require listing and deleting all files with prefix:
    # - input-pdfs/{project_id}/
    # - output-markdown/{project_id}/
    
    # Delete database record (cascade will delete documents and jobs)
    client.table("rag_projects").delete().eq("id", project_id).execute()
    
    logger.info(f"Deleted RAG project: {project_id}")


# =============================================================================
# Public Endpoints (No Auth Required)
# =============================================================================

class PublicRAGResponse(BaseModel):
    """Public-facing RAG info (limited fields)."""
    id: str
    name: str
    description: Optional[str]
    qdrant_collection: str
    is_public: bool


@router.get("/{project_id}/public", response_model=PublicRAGResponse)
async def get_public_rag_project(project_id: str) -> PublicRAGResponse:
    """
    Get public info for a RAG project.
    
    No authentication required, but only works for public projects.
    Accepts either project ID or slug.
    """
    if not is_multi_tenant_enabled():
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Multi-tenant mode not enabled"
        )
    
    client = get_supabase_client()
    
    # Check if project_id looks like a UUID
    import re
    uuid_pattern = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.IGNORECASE)
    is_uuid = bool(uuid_pattern.match(project_id))
    
    result = None
    if is_uuid:
        # Try to find by ID first
        result = client.table("rag_projects").select("*").eq("id", project_id).execute()
    
    if not result or not result.data:
        # Try by slug
        result = client.table("rag_projects").select("*").eq("slug", project_id).execute()
    
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="RAG not found"
        )
    
    project = result.data[0]
    
    if not project.get("is_public", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This RAG is private"
        )
    
    return PublicRAGResponse(
        id=str(project["id"]),
        name=project["name"],
        description=project.get("description"),
        qdrant_collection=project["qdrant_collection"],
        is_public=True,
    )


# =============================================================================
# Per-RAG Document Endpoints
# =============================================================================

class DocumentResponse(BaseModel):
    """Response for a document."""
    id: str
    filename: str
    original_filename: str
    title: Optional[str] = None
    authors: Optional[str] = None
    year: Optional[int] = None
    doi: Optional[str] = None
    status: str
    error_message: Optional[str]
    chunk_count: int
    created_at: datetime
    processed_at: Optional[datetime]


class DocumentListResponse(BaseModel):
    """Response for listing documents."""
    documents: List[DocumentResponse]
    total: int


@router.get("/{project_id}/documents", response_model=DocumentListResponse)
async def list_project_documents(
    project_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
) -> DocumentListResponse:
    """List all documents in a RAG project."""
    project = await get_user_project(user, project_id)
    client = get_supabase_client()
    
    result = client.table("documents").select("*").eq("rag_project_id", project_id).order("created_at", desc=True).execute()
    
    documents = []
    for d in result.data or []:
        # Extract metadata from JSONB field
        metadata = d.get("metadata", {}) or {}
        
        documents.append(DocumentResponse(
            id=str(d["id"]),
            filename=d["filename"],
            original_filename=d["original_filename"],
            title=metadata.get("title"),
            authors=metadata.get("authors"),
            year=metadata.get("year"),
            doi=metadata.get("doi"),
            status=d["status"],
            error_message=d.get("error_message"),
            chunk_count=d.get("chunk_count", 0),
            created_at=d["created_at"],
            processed_at=d.get("processed_at"),
        ))
    
    return DocumentListResponse(documents=documents, total=len(documents))


class JobResponse(BaseModel):
    """Response for a processing job."""
    id: str
    job_type: str
    status: str
    progress: int
    message: Optional[str]
    created_at: datetime


class JobListResponse(BaseModel):
    """Response for listing jobs."""
    jobs: List[JobResponse]


@router.get("/{project_id}/jobs", response_model=JobListResponse)
async def list_project_jobs(
    project_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
) -> JobListResponse:
    """List processing jobs for a RAG project."""
    project = await get_user_project(user, project_id)
    client = get_supabase_client()
    
    result = client.table("processing_jobs").select("*").eq("rag_project_id", project_id).order("created_at", desc=True).limit(50).execute()
    
    jobs = [
        JobResponse(
            id=str(j["id"]),
            job_type=j["job_type"],
            status=j["status"],
            progress=j.get("progress", 0),
            message=j.get("message"),
            created_at=j["created_at"],
        )
        for j in result.data or []
    ]
    
    return JobListResponse(jobs=jobs)


# =============================================================================
# Per-RAG Metadata Endpoints (Zotero-Compatible)
# =============================================================================

class MetadataDetail(BaseModel):
    """Full Zotero-compatible metadata for a document."""
    id: str
    title: str
    filename: str
    authors: List[str] = []
    year: Optional[int] = None
    abstract: Optional[str] = None
    
    # Zotero item type
    item_type: Optional[str] = None
    
    # Identifiers
    doi: Optional[str] = None
    isbn: Optional[str] = None
    issn: Optional[str] = None
    url: Optional[str] = None
    
    # Publication info
    publication: Optional[str] = None
    journal: Optional[str] = None
    volume: Optional[str] = None
    issue: Optional[str] = None
    pages: Optional[str] = None
    
    # Publisher info
    publisher: Optional[str] = None
    place: Optional[str] = None
    
    # 3ie Classification
    countries: List[str] = []
    sectors: List[str] = []
    study_type: Optional[str] = None
    intervention_type: Optional[str] = None
    
    # Processing metadata
    metadata_source: Optional[str] = "extraction"
    metadata_confidence: float = 0.0
    needs_review: bool = True
    chunk_count: int = 0


class MetadataListResponse(BaseModel):
    """Response for listing documents with metadata."""
    documents: List[MetadataDetail]
    total_count: int
    needs_review_count: int


class MetadataUpdateRequest(BaseModel):
    """Request to update document metadata."""
    title: Optional[str] = None
    authors: Optional[List[str]] = None
    year: Optional[int] = None
    abstract: Optional[str] = None
    item_type: Optional[str] = None
    doi: Optional[str] = None
    isbn: Optional[str] = None
    issn: Optional[str] = None
    url: Optional[str] = None
    publication: Optional[str] = None
    journal: Optional[str] = None
    volume: Optional[str] = None
    issue: Optional[str] = None
    pages: Optional[str] = None
    publisher: Optional[str] = None
    place: Optional[str] = None
    countries: Optional[List[str]] = None
    sectors: Optional[List[str]] = None
    study_type: Optional[str] = None
    intervention_type: Optional[str] = None
    needs_review: Optional[bool] = None


@router.get("/{project_id}/metadata", response_model=MetadataListResponse)
async def list_project_metadata(
    project_id: str,
    filter_type: Optional[str] = None,  # "needs_review" or "all"
    user: AuthenticatedUser = Depends(get_current_user),
) -> MetadataListResponse:
    """
    List all documents with full metadata for a RAG project.
    Zotero-compatible fields.
    """
    project = await get_user_project(user, project_id)
    client = get_supabase_client()
    
    # Get documents with metadata
    query = client.table("documents").select("*").eq("rag_project_id", project_id)
    
    result = query.order("created_at", desc=True).execute()
    
    documents = []
    needs_review_count = 0
    
    for d in result.data or []:
        metadata = d.get("metadata", {}) or {}
        
        # Parse authors - could be string or list
        authors_raw = metadata.get("authors", [])
        if isinstance(authors_raw, str):
            authors = [a.strip() for a in authors_raw.split(",") if a.strip()]
        elif isinstance(authors_raw, list):
            authors = authors_raw
        else:
            authors = []
        
        needs_review = metadata.get("needs_review", True)
        if needs_review:
            needs_review_count += 1
        
        # Skip if filtering for needs_review and this doesn't need review
        if filter_type == "needs_review" and not needs_review:
            continue
        
        documents.append(MetadataDetail(
            id=str(d["id"]),
            title=metadata.get("title") or d.get("original_filename", "Unknown"),
            filename=d["original_filename"],
            authors=authors,
            year=metadata.get("year"),
            abstract=metadata.get("abstract"),
            item_type=metadata.get("item_type"),
            doi=metadata.get("doi"),
            isbn=metadata.get("isbn"),
            issn=metadata.get("issn"),
            url=metadata.get("url"),
            publication=metadata.get("publication"),
            journal=metadata.get("journal"),
            volume=metadata.get("volume"),
            issue=metadata.get("issue"),
            pages=metadata.get("pages"),
            publisher=metadata.get("publisher"),
            place=metadata.get("place"),
            countries=metadata.get("countries", []),
            sectors=metadata.get("sectors", []),
            study_type=metadata.get("study_type"),
            intervention_type=metadata.get("intervention_type"),
            metadata_source=metadata.get("metadata_source", "extraction"),
            metadata_confidence=metadata.get("metadata_confidence", 0.0),
            needs_review=needs_review,
            chunk_count=d.get("chunk_count", 0),
        ))
    
    return MetadataListResponse(
        documents=documents,
        total_count=len(result.data or []),
        needs_review_count=needs_review_count,
    )


@router.get("/{project_id}/metadata/{doc_id}")
async def get_document_metadata(
    project_id: str,
    doc_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
) -> MetadataDetail:
    """Get full metadata for a single document."""
    project = await get_user_project(user, project_id)
    client = get_supabase_client()
    
    result = client.table("documents").select("*").eq("id", doc_id).eq("rag_project_id", project_id).single().execute()
    
    if not result.data:
        raise HTTPException(status_code=404, detail="Document not found")
    
    d = result.data
    metadata = d.get("metadata", {}) or {}
    
    authors_raw = metadata.get("authors", [])
    if isinstance(authors_raw, str):
        authors = [a.strip() for a in authors_raw.split(",") if a.strip()]
    elif isinstance(authors_raw, list):
        authors = authors_raw
    else:
        authors = []
    
    return MetadataDetail(
        id=str(d["id"]),
        title=metadata.get("title") or d.get("original_filename", "Unknown"),
        filename=d["original_filename"],
        authors=authors,
        year=metadata.get("year"),
        abstract=metadata.get("abstract"),
        item_type=metadata.get("item_type"),
        doi=metadata.get("doi"),
        isbn=metadata.get("isbn"),
        issn=metadata.get("issn"),
        url=metadata.get("url"),
        publication=metadata.get("publication"),
        journal=metadata.get("journal"),
        volume=metadata.get("volume"),
        issue=metadata.get("issue"),
        pages=metadata.get("pages"),
        publisher=metadata.get("publisher"),
        place=metadata.get("place"),
        countries=metadata.get("countries", []),
        sectors=metadata.get("sectors", []),
        study_type=metadata.get("study_type"),
        intervention_type=metadata.get("intervention_type"),
        metadata_source=metadata.get("metadata_source", "extraction"),
        metadata_confidence=metadata.get("metadata_confidence", 0.0),
        needs_review=metadata.get("needs_review", True),
        chunk_count=d.get("chunk_count", 0),
    )


@router.patch("/{project_id}/metadata/{doc_id}")
async def update_document_metadata(
    project_id: str,
    doc_id: str,
    update: MetadataUpdateRequest,
    user: AuthenticatedUser = Depends(get_current_user),
) -> MetadataDetail:
    """
    Update metadata for a document.
    Also syncs the metadata to Qdrant vectors for search.
    """
    project = await get_user_project(user, project_id)
    client = get_supabase_client()
    
    # Get current document
    result = client.table("documents").select("*").eq("id", doc_id).eq("rag_project_id", project_id).single().execute()
    
    if not result.data:
        raise HTTPException(status_code=404, detail="Document not found")
    
    current_metadata = result.data.get("metadata", {}) or {}
    
    # Merge updates into metadata
    update_dict = update.model_dump(exclude_none=True)
    new_metadata = {**current_metadata, **update_dict}
    
    # Mark as user-verified
    new_metadata["metadata_source"] = "user"
    new_metadata["metadata_confidence"] = 1.0
    if "needs_review" not in update_dict:
        new_metadata["needs_review"] = False
    
    # Update in Supabase
    client.table("documents").update({
        "metadata": new_metadata,
        "updated_at": datetime.utcnow().isoformat(),
    }).eq("id", doc_id).execute()
    
    # Sync to Qdrant vectors
    try:
        indexer = QdrantIndexer(collection_name=project["qdrant_collection"])
        
        # Build Qdrant payload update
        qdrant_update = {}
        if update.title:
            qdrant_update["title"] = update.title
        if update.authors:
            qdrant_update["authors"] = ", ".join(update.authors)
        if update.year:
            qdrant_update["year"] = update.year
        if update.doi:
            qdrant_update["doi"] = update.doi
        if update.countries:
            qdrant_update["country"] = update.countries[0] if update.countries else None
            qdrant_update["countries"] = update.countries
        if update.sectors:
            qdrant_update["sector"] = update.sectors[0] if update.sectors else None
            qdrant_update["sectors"] = update.sectors
        if update.study_type:
            qdrant_update["study_type"] = update.study_type
        
        if qdrant_update:
            # Update all vectors for this document
            indexer.client.set_payload(
                collection_name=project["qdrant_collection"],
                payload=qdrant_update,
                points=indexer.client.scroll(
                    collection_name=project["qdrant_collection"],
                    scroll_filter={
                        "must": [{"key": "doc_id", "match": {"value": doc_id}}]
                    },
                    limit=1000,
                    with_payload=False,
                )[0],
            )
            logger.info(f"Synced metadata to Qdrant for doc {doc_id}")
    except Exception as e:
        logger.warning(f"Failed to sync metadata to Qdrant: {e}")
    
    # Return updated metadata
    return await get_document_metadata(project_id, doc_id, user)


@router.post("/{project_id}/metadata/{doc_id}/enrich")
async def enrich_document_metadata(
    project_id: str,
    doc_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
) -> MetadataDetail:
    """
    Enrich document metadata from CrossRef/OpenAlex using DOI.
    """
    project = await get_user_project(user, project_id)
    client = get_supabase_client()
    
    # Get current document
    result = client.table("documents").select("*").eq("id", doc_id).eq("rag_project_id", project_id).single().execute()
    
    if not result.data:
        raise HTTPException(status_code=404, detail="Document not found")
    
    current_metadata = result.data.get("metadata", {}) or {}
    doi = current_metadata.get("doi")
    
    if not doi:
        raise HTTPException(status_code=400, detail="Document has no DOI for enrichment")
    
    # Lookup in CrossRef
    from src.ingestion.metadata.crossref_client import CrossRefClient
    
    try:
        crossref = CrossRefClient()
        work = await crossref.get_by_doi(doi)
        
        if not work:
            raise HTTPException(status_code=404, detail="DOI not found in CrossRef")
        
        # Update metadata with CrossRef data
        enriched = {
            **current_metadata,
            "title": work.title or current_metadata.get("title"),
            "authors": work.authors or current_metadata.get("authors", []),
            "year": work.year or current_metadata.get("year"),
            "journal": work.journal or current_metadata.get("journal"),
            "publisher": work.publisher or current_metadata.get("publisher"),
            "volume": work.volume or current_metadata.get("volume"),
            "issue": work.issue or current_metadata.get("issue"),
            "pages": work.pages or current_metadata.get("pages"),
            "item_type": work.type or current_metadata.get("item_type"),
            "metadata_source": "crossref",
            "metadata_confidence": 0.95,
            "needs_review": False,
        }
        
        # Update in Supabase
        client.table("documents").update({
            "metadata": enriched,
            "updated_at": datetime.utcnow().isoformat(),
        }).eq("id", doc_id).execute()
        
        logger.info(f"Enriched doc {doc_id} from CrossRef")
        
    except Exception as e:
        logger.error(f"CrossRef enrichment failed: {e}")
        raise HTTPException(status_code=500, detail=f"Enrichment failed: {e}")
    
    return await get_document_metadata(project_id, doc_id, user)


@router.get("/{project_id}/documents/{doc_id}/pdf")
async def get_document_pdf_url(
    project_id: str,
    doc_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Get a presigned URL to view the PDF for a document.
    """
    import os
    from botocore.exceptions import ClientError
    from src.ingestion.r2_client import R2Client
    
    project = await get_user_project(user, project_id)
    client = get_supabase_client()
    
    # Get document
    result = client.table("documents").select("*").eq("id", doc_id).eq("rag_project_id", project_id).single().execute()
    
    if not result.data:
        raise HTTPException(status_code=404, detail="Document not found")
    
    doc = result.data
    
    try:
        r2_client = R2Client()
        bucket_name = os.getenv("R2_BUCKET_NAME", "devchat-pdfs")
        
        # The R2 key could be in different formats
        # Try using the filename field or original_filename
        possible_keys = [
            f"input-pdfs/{doc['filename']}",
            f"input-pdfs/{doc['original_filename']}",
            f"input-pdfs/{doc_id}.pdf",
        ]
        
        r2_key = None
        for key in possible_keys:
            try:
                r2_client.client.head_object(Bucket=bucket_name, Key=key)
                r2_key = key
                break
            except ClientError:
                continue
        
        if not r2_key:
            raise HTTPException(status_code=404, detail="PDF not found in storage")
        
        # Generate presigned URL (valid for 1 hour)
        presigned_url = r2_client.client.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': bucket_name,
                'Key': r2_key,
            },
            ExpiresIn=3600,
        )
        
        return {"url": presigned_url, "expires_in": 3600}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to generate PDF URL: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get PDF URL: {str(e)}")

