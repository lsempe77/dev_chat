"""
RAG Project Management API Routes

Allows authenticated users to create, list, update, and delete their RAG projects.
Each RAG project corresponds to a separate Qdrant collection.
"""

import hashlib
import os
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, BackgroundTasks
from pydantic import BaseModel, Field
from botocore.exceptions import ClientError

from src.auth import AuthenticatedUser, get_current_user, get_supabase_client, is_multi_tenant_enabled
from src.utils.logging import get_logger
from src.ingestion.indexer import QdrantIndexer
from src.config.settings import settings
from .dependencies import get_r2_client

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
    
    # Delete R2 files for this project
    try:
        r2_client = get_r2_client()
        bucket_name = os.getenv("R2_BUCKET_NAME", "devchat-pdfs")
        prefix = f"rags/{project_id}/"
        paginator = r2_client.get_paginator("list_objects_v2")
        
        deleted_count = 0
        for page in paginator.paginate(Bucket=bucket_name, Prefix=prefix):
            for obj in page.get("Contents", []):
                try:
                    r2_client.delete_object(Bucket=bucket_name, Key=obj["Key"])
                    deleted_count += 1
                except Exception:
                    pass
        logger.info(f"Deleted {deleted_count} R2 files for project {project_id}")
    except Exception as e:
        logger.warning(f"Failed to delete R2 files for {project_id}: {e}")
        # Continue anyway
    
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


class SyncResponse(BaseModel):
    """Response for syncing R2 with Supabase."""
    synced: int
    already_exists: int
    errors: int
    message: str


@router.post("/{project_id}/documents/sync", response_model=SyncResponse)
async def sync_project_documents(
    project_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
) -> SyncResponse:
    """
    Sync R2 files with Supabase documents table.
    
    Finds files in R2 that don't have corresponding Supabase records and creates them.
    This handles orphaned uploads where R2 succeeded but Supabase failed.
    """
    project = await get_user_project(user, project_id)
    
    r2_client = get_r2_client()
    bucket_name = os.getenv("R2_BUCKET_NAME", "devchat-pdfs")
    client = get_supabase_client()
    
    # Get existing documents from Supabase
    result = client.table("documents").select("filename").eq("rag_project_id", project_id).execute()
    existing_filenames = set(d["filename"] for d in result.data or [])
    
    # Get files from R2
    prefix = f"rags/{project_id}/input-pdfs/"
    paginator = r2_client.get_paginator("list_objects_v2")
    
    synced = 0
    already_exists = 0
    errors = 0
    
    for page in paginator.paginate(Bucket=bucket_name, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            filename = key.replace(prefix, "")
            doc_id = os.path.splitext(filename)[0]
            
            if doc_id in existing_filenames:
                already_exists += 1
                continue
            
            # Extract original filename from doc_id (format: hash_originalname)
            parts = doc_id.split("_", 1)
            if len(parts) > 1:
                original_name = parts[1] + ".pdf"
                content_hash = parts[0]
            else:
                original_name = filename
                content_hash = ""
            
            try:
                client.table("documents").insert({
                    "rag_project_id": project_id,
                    "filename": doc_id,
                    "original_filename": original_name,
                    "file_size_bytes": obj.get("Size", 0),
                    "mime_type": "application/pdf",
                    "status": "pending",
                    "r2_input_key": key,
                    "metadata": {"content_hash": content_hash} if content_hash else {},
                }).execute()
                synced += 1
                logger.info(f"Synced orphaned R2 file to Supabase: {doc_id}")
            except Exception as e:
                errors += 1
                logger.error(f"Failed to sync {doc_id}: {e}")
    
    return SyncResponse(
        synced=synced,
        already_exists=already_exists,
        errors=errors,
        message=f"Synced {synced} orphaned files, {already_exists} already existed, {errors} errors",
    )


# =============================================================================
# Document Upload Helpers
# =============================================================================

def compute_content_hash(content: bytes) -> str:
    """Compute SHA-256 hash of content, truncated for use in filenames."""
    return hashlib.sha256(content).hexdigest()[:12]


def find_existing_document_for_project(r2_client, bucket_name: str, project_id: str, content_hash: str, base_name: str) -> dict | None:
    """Check if a document with the same content hash already exists in the project's R2 folder."""
    prefix = f"rags/{project_id}/input-pdfs/"
    try:
        response = r2_client.list_objects_v2(Bucket=bucket_name, Prefix=prefix)
        for obj in response.get("Contents", []):
            key = obj["Key"]
            # Doc ID is the filename without .pdf
            filename = key.replace(prefix, "")
            if filename.startswith(f"{content_hash}_"):
                doc_id = os.path.splitext(filename)[0]
                return {
                    "key": key,
                    "doc_id": doc_id,
                    "size": obj["Size"],
                }
    except Exception as e:
        logger.warning(f"Error checking for duplicates: {e}")
    return None


class UploadResponse(BaseModel):
    """Response for file upload."""
    success: bool
    filename: str
    r2_key: Optional[str] = None
    size_bytes: Optional[int] = None
    queued_for_processing: bool = False
    doc_id: Optional[str] = None
    message: Optional[str] = None
    is_duplicate: bool = False


@router.post("/{project_id}/documents/upload", response_model=UploadResponse)
async def upload_document(
    project_id: str,
    file: UploadFile = File(...),
    force_upload: bool = False,
    user: AuthenticatedUser = Depends(get_current_user),
) -> UploadResponse:
    """
    Upload a PDF document to a RAG project.
    
    Uses content-based deduplication: files with identical content won't be uploaded twice.
    Set force_upload=true to bypass duplicate detection.
    """
    project = await get_user_project(user, project_id)
    
    # Validate file type (only PDFs supported)
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")
    
    file_ext = os.path.splitext(file.filename.lower())[1]
    if file_ext != ".pdf":
        raise HTTPException(
            status_code=400,
            detail=f"Only PDF files are supported. Got: {file_ext}"
        )
    
    try:
        # Read file content for deduplication
        content = await file.read()
        size_bytes = len(content)
        
        # Compute content hash for deduplication
        content_hash = compute_content_hash(content)
        
        safe_filename = file.filename.replace(" ", "_").replace("/", "_")
        base_name = os.path.splitext(safe_filename)[0]
        
        r2_client = get_r2_client()
        bucket_name = os.getenv("R2_BUCKET_NAME", "devchat-pdfs")
        
        # Check for existing document with same content
        if not force_upload:
            existing = find_existing_document_for_project(r2_client, bucket_name, project_id, content_hash, base_name)
            if existing:
                logger.info(f"Duplicate detected: {file.filename} matches existing {existing['doc_id']} in project {project_id}")
                return UploadResponse(
                    success=True,
                    filename=file.filename,
                    r2_key=existing["key"],
                    size_bytes=existing["size"],
                    queued_for_processing=False,
                    doc_id=existing["doc_id"],
                    message=f"Document already exists as {existing['doc_id']}. No duplicate created.",
                    is_duplicate=True,
                )
        
        # Generate doc_id using content hash
        doc_id = f"{content_hash}_{base_name}"
        r2_key = f"rags/{project_id}/input-pdfs/{doc_id}{file_ext}"
        
        # Upload to R2
        r2_client.put_object(
            Bucket=bucket_name,
            Key=r2_key,
            Body=content,
            ContentType=file.content_type or "application/pdf",
            Metadata={
                "doc_id": doc_id,
                "content_hash": content_hash,
                "original_filename": file.filename,
                "upload_timestamp": datetime.utcnow().isoformat(),
                "project_id": project_id,
            }
        )
        
        logger.info(f"Uploaded {file.filename} to R2 as {r2_key} (doc_id={doc_id}, project={project_id}, {size_bytes} bytes)")
        
        # Create document record in database (atomic with R2 - rollback on failure)
        try:
            client = get_supabase_client()
            client.table("documents").upsert({
                "rag_project_id": project_id,
                "filename": doc_id,
                "original_filename": file.filename,
                "file_size_bytes": size_bytes,
                "mime_type": file.content_type or "application/pdf",
                "status": "pending",
                "r2_input_key": r2_key,
                "metadata": {"content_hash": content_hash},
            }, on_conflict="filename,rag_project_id").execute()
        except Exception as db_error:
            # Rollback: delete from R2 if Supabase insert fails
            logger.error(f"Supabase insert failed, rolling back R2 upload: {db_error}")
            try:
                r2_client.delete_object(Bucket=bucket_name, Key=r2_key)
                logger.info(f"Rolled back R2 upload: {r2_key}")
            except Exception as rollback_error:
                logger.error(f"Failed to rollback R2 upload: {rollback_error}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to save document record: {str(db_error)}"
            )
        
        return UploadResponse(
            success=True,
            filename=file.filename,
            r2_key=r2_key,
            size_bytes=size_bytes,
            queued_for_processing=True,
            doc_id=doc_id,
        )
        
    except ClientError as e:
        logger.error(f"R2 upload failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to upload to R2: {str(e)}")
    except Exception as e:
        logger.error(f"Upload failed: {e}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


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
# Processing Trigger - Modal Integration
# =============================================================================

class ProcessResponse(BaseModel):
    """Response for processing trigger."""
    message: str
    queued: int
    skipped: int
    function_id: Optional[str] = None


@router.post("/{project_id}/process", response_model=ProcessResponse)
async def trigger_processing(
    project_id: str,
    force: bool = False,
    user: AuthenticatedUser = Depends(get_current_user),
) -> ProcessResponse:
    """
    Trigger Modal processing for all unprocessed documents in this RAG project.
    
    This calls Modal's orchestrate_rag function which:
    1. Finds all PDFs in rags/{project_id}/input-pdfs/
    2. Processes each with MinerU (text extraction)
    3. Enriches metadata from CrossRef/OpenAlex
    4. Embeds chunks to Qdrant (project-specific collection)
    5. Syncs metadata back to Supabase documents table
    
    Args:
        project_id: The RAG project ID
        force: If True, reprocess all documents (even already processed ones)
    """
    import httpx
    
    project = await get_user_project(user, project_id)
    client = get_supabase_client()
    
    # Get documents that need processing (status != 'completed')
    if force:
        docs_result = client.table("documents").select("id, original_filename, status").eq("rag_project_id", project_id).execute()
    else:
        docs_result = client.table("documents").select("id, original_filename, status").eq("rag_project_id", project_id).neq("status", "completed").execute()
    
    pending_docs = docs_result.data or []
    
    if not pending_docs:
        return ProcessResponse(
            message="No documents to process",
            queued=0,
            skipped=0,
        )
    
    # Update status to 'processing' for all pending docs
    doc_ids = [d["id"] for d in pending_docs]
    client.table("documents").update({
        "status": "processing",
        "updated_at": datetime.utcnow().isoformat(),
    }).in_("id", doc_ids).execute()
    
    # Trigger Modal function
    # Modal needs to know:
    # 1. The R2 prefix to scan: rags/{project_id}/input-pdfs/
    # 2. The Qdrant collection: rag_{project_id}
    # 3. The project_id for syncing back to Supabase
    
    modal_webhook_url = os.environ.get("MODAL_WEBHOOK_URL")
    
    if modal_webhook_url:
        # Call Modal webhook to trigger processing
        try:
            async with httpx.AsyncClient(timeout=30.0) as http_client:
                response = await http_client.post(
                    modal_webhook_url,
                    json={
                        "action": "process_rag_project",
                        "project_id": project_id,
                        "qdrant_collection": project.qdrant_collection,
                        "force_reprocess": force,
                    },
                )
                
                if response.status_code == 200:
                    result = response.json()
                    logger.info(f"Modal triggered for project {project_id}: {result}")
                    return ProcessResponse(
                        message=f"Processing triggered for {len(pending_docs)} documents",
                        queued=len(pending_docs),
                        skipped=0,
                        function_id=result.get("function_id"),
                    )
                else:
                    logger.error(f"Modal webhook failed: {response.status_code} - {response.text}")
                    # Fall through to manual processing message
                    
        except Exception as e:
            logger.error(f"Modal webhook error: {e}")
            # Fall through to manual processing message
    
    # If no Modal webhook or it failed, return instructions for manual trigger
    r2_prefix = f"rags/{project_id}/input-pdfs/"
    qdrant_collection = project.qdrant_collection
    
    return ProcessResponse(
        message=f"Documents marked as queued. Run Modal manually: modal run infrastructure/modal_mineru.py::orchestrate_rag --project-id {project_id}",
        queued=len(pending_docs),
        skipped=0,
    )


@router.delete("/{project_id}/locks")
async def clear_project_locks(
    project_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Clear processing locks for stuck documents.
    Resets any documents stuck in 'processing' status back to 'pending'.
    """
    project = await get_user_project(user, project_id)
    client = get_supabase_client()
    
    # Find stuck documents
    stuck_result = client.table("documents").select("id").eq("rag_project_id", project_id).eq("status", "processing").execute()
    stuck_count = len(stuck_result.data or [])
    
    if stuck_count > 0:
        # Reset to pending
        client.table("documents").update({
            "status": "pending",
            "updated_at": datetime.utcnow().isoformat(),
        }).eq("rag_project_id", project_id).eq("status", "processing").execute()
    
    return {"message": f"Cleared {stuck_count} stuck documents", "cleared": stuck_count}


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
    Enrich document metadata from CrossRef/OpenAlex.
    
    If DOI is present, uses DOI lookup.
    If no DOI, tries to extract DOI from filename or search by title.
    """
    project = await get_user_project(user, project_id)
    client = get_supabase_client()
    
    # Get current document
    result = client.table("documents").select("*").eq("id", doc_id).eq("rag_project_id", project_id).single().execute()
    
    if not result.data:
        raise HTTPException(status_code=404, detail="Document not found")
    
    current_metadata = result.data.get("metadata", {}) or {}
    doi = current_metadata.get("doi")
    original_filename = result.data.get("original_filename", "")
    
    # Try to extract DOI from filename if not present
    # Pattern: files often contain DOI-like strings like "10.xxxx_xxxxx" 
    if not doi:
        import re
        # Look for DOI pattern in filename
        doi_match = re.search(r'10\.\d{4,}/[^\s]+', original_filename.replace('_', '/'))
        if doi_match:
            doi = doi_match.group(0)
            logger.info(f"Extracted DOI from filename: {doi}")
    
    # Import metadata clients
    from src.ingestion.metadata.crossref_client import CrossRefClient
    from src.ingestion.metadata.openalex_client import OpenAlexClient
    
    enriched = {**current_metadata}
    source = None
    
    try:
        if doi:
            # Try CrossRef first
            crossref = CrossRefClient()
            work = await crossref.get_by_doi(doi)
            
            if work:
                enriched.update({
                    "doi": doi,
                    "title": work.title or enriched.get("title"),
                    "authors": work.authors or enriched.get("authors", []),
                    "year": work.year or enriched.get("year"),
                    "journal": work.journal or enriched.get("journal"),
                    "publisher": work.publisher or enriched.get("publisher"),
                    "volume": work.volume or enriched.get("volume"),
                    "issue": work.issue or enriched.get("issue"),
                    "pages": work.pages or enriched.get("pages"),
                    "item_type": work.type or enriched.get("item_type"),
                })
                source = "crossref"
            
            # Also try OpenAlex for additional data
            openalex = OpenAlexClient()
            oa_work = await openalex.get_by_doi(doi)
            
            if oa_work:
                # OpenAlex often has better abstract, concepts, SDGs
                if oa_work.abstract and not enriched.get("abstract"):
                    enriched["abstract"] = oa_work.abstract
                if oa_work.concepts:
                    enriched["keywords"] = [c.display_name for c in oa_work.concepts[:10]]
                if oa_work.is_open_access is not None:
                    enriched["is_open_access"] = oa_work.is_open_access
                if not source:
                    source = "openalex"
        
        else:
            # No DOI - try OpenAlex search by title from filename
            openalex = OpenAlexClient()
            # Clean up filename to get a searchable title
            search_title = original_filename.replace('.pdf', '').replace('_', ' ')
            # Remove common prefixes like hash
            import re
            search_title = re.sub(r'^[a-f0-9]{10,}_', '', search_title)
            
            works = await openalex.search(search_title, limit=1)
            if works and len(works) > 0:
                oa_work = works[0]
                enriched.update({
                    "title": oa_work.title or enriched.get("title"),
                    "authors": oa_work.authors or enriched.get("authors", []),
                    "year": oa_work.year or enriched.get("year"),
                    "doi": oa_work.doi or enriched.get("doi"),
                    "abstract": oa_work.abstract or enriched.get("abstract"),
                })
                if oa_work.concepts:
                    enriched["keywords"] = [c.display_name for c in oa_work.concepts[:10]]
                source = "openalex"
            else:
                raise HTTPException(status_code=404, detail="Could not find metadata. Try adding a DOI manually.")
        
        if source:
            enriched["metadata_source"] = source
            enriched["metadata_confidence"] = 0.95 if doi else 0.7
            enriched["needs_review"] = False
        
        # Update in Supabase
        client.table("documents").update({
            "metadata": enriched,
            "updated_at": datetime.utcnow().isoformat(),
        }).eq("id", doc_id).execute()
        
        logger.info(f"Enriched doc {doc_id} from {source}")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Enrichment failed: {e}")
        raise HTTPException(status_code=500, detail=f"Enrichment failed: {e}")
    
    return await get_document_metadata(project_id, doc_id, user)


@router.post("/{project_id}/metadata/enrich-all")
async def enrich_all_documents(
    project_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Enrich metadata for all documents in a project.
    Returns a summary of enriched vs failed documents.
    """
    import re
    from src.ingestion.metadata.crossref_client import CrossRefClient
    from src.ingestion.metadata.openalex_client import OpenAlexClient
    
    project = await get_user_project(user, project_id)
    client = get_supabase_client()
    
    # Get all documents
    result = client.table("documents").select("*").eq("rag_project_id", project_id).execute()
    
    if not result.data:
        return {"enriched": 0, "failed": 0, "skipped": 0, "total": 0, "details": []}
    
    enriched_count = 0
    failed_count = 0
    skipped_count = 0
    details = []
    
    crossref = CrossRefClient()
    openalex = OpenAlexClient()
    
    for doc in result.data:
        doc_id = doc["id"]
        current_metadata = doc.get("metadata", {}) or {}
        doi = current_metadata.get("doi")
        original_filename = doc.get("original_filename", "")
        
        # Skip if already enriched with high confidence
        if current_metadata.get("metadata_source") and current_metadata.get("metadata_confidence", 0) >= 0.9:
            skipped_count += 1
            details.append({"id": doc_id, "status": "skipped", "reason": "Already enriched"})
            continue
        
        # Try to extract DOI from filename if not present
        if not doi:
            doi_match = re.search(r'10\.\d{4,}/[^\s]+', original_filename.replace('_', '/'))
            if doi_match:
                doi = doi_match.group(0)
        
        try:
            enriched = {**current_metadata}
            source = None
            
            if doi:
                # Try CrossRef
                work = await crossref.get_by_doi(doi)
                if work:
                    enriched.update({
                        "doi": doi,
                        "title": work.title or enriched.get("title"),
                        "authors": work.authors or enriched.get("authors", []),
                        "year": work.year or enriched.get("year"),
                        "journal": work.journal or enriched.get("journal"),
                        "publisher": work.publisher or enriched.get("publisher"),
                        "item_type": work.type or enriched.get("item_type"),
                    })
                    source = "crossref"
                
                # Also try OpenAlex for additional data
                oa_work = await openalex.get_by_doi(doi)
                if oa_work:
                    if oa_work.abstract and not enriched.get("abstract"):
                        enriched["abstract"] = oa_work.abstract
                    if oa_work.concepts:
                        enriched["keywords"] = [c.display_name for c in oa_work.concepts[:10]]
                    if not source:
                        source = "openalex"
            else:
                # Search by title from filename
                search_title = original_filename.replace('.pdf', '').replace('_', ' ')
                search_title = re.sub(r'^[a-f0-9]{10,}_', '', search_title)
                
                works = await openalex.search(search_title, limit=1)
                if works and len(works) > 0:
                    oa_work = works[0]
                    enriched.update({
                        "title": oa_work.title or enriched.get("title"),
                        "authors": oa_work.authors or enriched.get("authors", []),
                        "year": oa_work.year or enriched.get("year"),
                        "doi": oa_work.doi or enriched.get("doi"),
                    })
                    if oa_work.concepts:
                        enriched["keywords"] = [c.display_name for c in oa_work.concepts[:10]]
                    source = "openalex"
            
            if source:
                enriched["metadata_source"] = source
                enriched["metadata_confidence"] = 0.95 if doi else 0.7
                enriched["needs_review"] = False
                
                client.table("documents").update({
                    "metadata": enriched,
                    "updated_at": datetime.utcnow().isoformat(),
                }).eq("id", doc_id).execute()
                
                enriched_count += 1
                details.append({"id": doc_id, "status": "enriched", "source": source})
            else:
                failed_count += 1
                details.append({"id": doc_id, "status": "failed", "reason": "No metadata found"})
                
        except Exception as e:
            failed_count += 1
            details.append({"id": doc_id, "status": "failed", "reason": str(e)})
            logger.warning(f"Failed to enrich doc {doc_id}: {e}")
    
    logger.info(f"Enrich all: {enriched_count} enriched, {failed_count} failed, {skipped_count} skipped")
    
    return {
        "enriched": enriched_count,
        "failed": failed_count,
        "skipped": skipped_count,
        "total": len(result.data),
        "details": details,
    }


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
    
    project = await get_user_project(user, project_id)
    client = get_supabase_client()
    
    # Get document
    result = client.table("documents").select("*").eq("id", doc_id).eq("rag_project_id", project_id).single().execute()
    
    if not result.data:
        raise HTTPException(status_code=404, detail="Document not found")
    
    doc = result.data
    
    try:
        r2_client = get_r2_client()
        bucket_name = os.getenv("R2_BUCKET_NAME", "devchat-pdfs")
        
        # Try the stored r2_input_key first, then fallback to constructed paths
        possible_keys = []
        
        # 1. Use stored R2 key if available
        if doc.get("r2_input_key"):
            possible_keys.append(doc["r2_input_key"])
        
        # 2. Multi-tenant path: rags/{project_id}/input-pdfs/{filename}.pdf
        possible_keys.extend([
            f"rags/{project_id}/input-pdfs/{doc['filename']}.pdf",
            f"rags/{project_id}/input-pdfs/{doc['filename']}",
        ])
        
        # 3. Legacy paths (for backwards compatibility)
        possible_keys.extend([
            f"input-pdfs/{doc['filename']}",
            f"input-pdfs/{doc['original_filename']}",
            f"input-pdfs/{doc_id}.pdf",
        ])
        
        r2_key = None
        for key in possible_keys:
            try:
                r2_client.head_object(Bucket=bucket_name, Key=key)
                r2_key = key
                break
            except ClientError:
                continue
        
        if not r2_key:
            logger.warning(f"PDF not found for doc {doc_id}. Tried keys: {possible_keys}")
            raise HTTPException(status_code=404, detail="PDF not found in storage")
        
        # Generate presigned URL (valid for 1 hour)
        presigned_url = r2_client.generate_presigned_url(
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


# =============================================================================
# Per-RAG Danger Zone Endpoints
# =============================================================================

@router.delete("/{project_id}/vectors")
async def reset_project_vectors(
    project_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Delete all vector embeddings for this project from Qdrant.
    Documents will need to be reprocessed.
    """
    from qdrant_client import models
    
    project = await get_user_project(user, project_id)
    
    try:
        indexer = QdrantIndexer(collection_name=project["qdrant_collection"])
        
        # Delete all points in the collection using FilterSelector
        indexer.client.delete(
            collection_name=project["qdrant_collection"],
            points_selector=models.FilterSelector(
                filter=models.Filter()  # Empty filter = match all
            ),
        )
        
        # Update chunk counts in documents
        client = get_supabase_client()
        client.table("documents").update({
            "chunk_count": 0,
            "status": "pending",
        }).eq("rag_project_id", project_id).execute()
        
        logger.info(f"Reset vectors for project {project_id}")
        return {"message": "Vectors reset successfully", "collection": project["qdrant_collection"]}
        
    except Exception as e:
        logger.error(f"Failed to reset vectors: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to reset vectors: {str(e)}")


@router.delete("/{project_id}/storage")
async def clear_project_storage(
    project_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Delete all PDFs and processed outputs for this project from R2.
    """
    import os
    
    project = await get_user_project(user, project_id)
    
    try:
        r2_client = get_r2_client()
        bucket_name = os.getenv("R2_BUCKET_NAME", "devchat-pdfs")
        deleted_count = 0
        
        # Multi-tenant path: rags/{project_id}/
        prefix = f"rags/{project_id}/"
        paginator = r2_client.get_paginator("list_objects_v2")
        
        # Delete all objects under the project prefix
        for page in paginator.paginate(Bucket=bucket_name, Prefix=prefix):
            for obj in page.get("Contents", []):
                try:
                    r2_client.delete_object(Bucket=bucket_name, Key=obj["Key"])
                    deleted_count += 1
                except Exception as e:
                    logger.warning(f"Failed to delete {obj['Key']}: {e}")
        
        logger.info(f"Cleared {deleted_count} files from R2 for project {project_id}")
        return {"message": "Storage cleared", "deleted": deleted_count}
        
    except Exception as e:
        logger.error(f"Failed to clear storage: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to clear storage: {str(e)}")


@router.delete("/{project_id}/documents")
async def reset_project_documents(
    project_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Delete all document records from the database for this project.
    Does not delete files from R2 or vectors from Qdrant.
    """
    project = await get_user_project(user, project_id)
    client = get_supabase_client()
    
    try:
        # Count documents first
        count_result = client.table("documents").select("id", count="exact").eq("rag_project_id", project_id).execute()
        doc_count = count_result.count or 0
        
        # Delete all documents
        client.table("documents").delete().eq("rag_project_id", project_id).execute()
        
        # Also delete any jobs
        client.table("processing_jobs").delete().eq("rag_project_id", project_id).execute()
        
        logger.info(f"Deleted {doc_count} documents from project {project_id}")
        return {"message": "Documents reset", "deleted": doc_count}
        
    except Exception as e:
        logger.error(f"Failed to reset documents: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to reset documents: {str(e)}")


