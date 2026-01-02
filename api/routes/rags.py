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
    
    documents = [
        DocumentResponse(
            id=str(d["id"]),
            filename=d["filename"],
            original_filename=d["original_filename"],
            status=d["status"],
            error_message=d.get("error_message"),
            chunk_count=d.get("chunk_count", 0),
            created_at=d["created_at"],
            processed_at=d.get("processed_at"),
        )
        for d in result.data or []
    ]
    
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
