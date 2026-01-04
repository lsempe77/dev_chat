"""
Zotero Integration API Routes for RAG Projects

Handles Zotero account connection, collection listing, and item sync.
"""

import hashlib
import os
import unicodedata
from datetime import datetime
from typing import List, Optional
from uuid import UUID


def sanitize_to_ascii(text: str, max_length: int = 200) -> str:
    """
    Sanitize a string to contain only ASCII characters.
    S3/R2 metadata can only contain ASCII characters.
    
    - Converts accented characters to their base form (ä -> a, é -> e)
    - Removes any remaining non-ASCII characters
    - Truncates to max_length
    """
    if not text:
        return text
    # Normalize to NFKD form (decomposes accented chars into base + combining)
    normalized = unicodedata.normalize("NFKD", text)
    # Encode to ASCII, ignoring non-ASCII combining marks
    ascii_bytes = normalized.encode("ascii", "ignore")
    # Decode back to string and truncate
    return ascii_bytes.decode("ascii")[:max_length]


def calculate_zotero_confidence(item: dict) -> float:
    """
    Calculate metadata confidence score based on Zotero field completeness.
    
    Zotero is a trusted source, so we give a base confidence of 0.6.
    Having DOI gives another 0.2 boost (can be verified externally).
    Having complete bibliographic fields gives up to 0.2 more.
    
    Returns: confidence score between 0.6 and 1.0
    """
    base_confidence = 0.6
    
    # DOI is a strong identifier - boost confidence
    has_doi = bool(item.get("doi"))
    doi_bonus = 0.2 if has_doi else 0.0
    
    # Check key fields for completeness
    key_fields = ["title", "authors", "year", "journal", "abstract"]
    present_fields = sum(1 for f in key_fields if item.get(f))
    completeness_score = (present_fields / len(key_fields)) * 0.2
    
    return min(1.0, base_confidence + doi_bonus + completeness_score)

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from src.auth import AuthenticatedUser, get_current_user, get_supabase_client
from src.utils.logging import get_logger
from src.utils.zotero_client import ZoteroClient, validate_zotero_credentials
from .dependencies import get_r2_client

logger = get_logger(__name__)

router = APIRouter(prefix="/rags/{project_id}/zotero", tags=["Zotero Integration"])


# =============================================================================
# Pydantic Models
# =============================================================================

class ZoteroConnectionCreate(BaseModel):
    """Request to create a new Zotero connection."""
    api_key: str = Field(..., description="Zotero API key from https://www.zotero.org/settings/keys")
    zotero_user_id: str = Field(..., description="Zotero user ID (number, not username)")
    library_type: str = Field(default="user", description="'user' or 'group'")
    selected_collection_key: Optional[str] = Field(None, description="Specific collection to sync (optional)")
    sync_pdfs: bool = Field(default=True, description="Whether to download PDF attachments")


class ZoteroConnectionResponse(BaseModel):
    """Response with Zotero connection details (without API key)."""
    id: str
    rag_project_id: str
    zotero_user_id: str
    library_type: str
    selected_collection_key: Optional[str] = None
    auto_sync_enabled: bool = False
    sync_pdfs: bool = True
    last_synced_at: Optional[datetime] = None
    last_sync_version: Optional[int] = None
    total_items_synced: int = 0
    connected_at: datetime
    last_sync_error: Optional[str] = None


class ZoteroLibraryInfo(BaseModel):
    """Info about a Zotero library."""
    library_id: str
    library_type: str
    name: str
    num_items: int
    num_collections: int


class ZoteroCollectionInfo(BaseModel):
    """Info about a Zotero collection."""
    key: str
    name: str
    num_items: int
    parent_collection: Optional[str] = None


class ZoteroValidateRequest(BaseModel):
    """Request to validate Zotero credentials."""
    api_key: str
    zotero_user_id: str
    library_type: str = "user"


class ZoteroValidateResponse(BaseModel):
    """Response from credential validation."""
    valid: bool
    message: Optional[str] = None
    error: Optional[str] = None
    library_info: Optional[ZoteroLibraryInfo] = None
    suggestions: Optional[List[str]] = None


class ZoteroSyncRequest(BaseModel):
    """Request to sync items from Zotero."""
    collection_key: Optional[str] = None  # If None, sync all items
    sync_pdfs: bool = True
    start: int = 0  # Pagination offset for fetching items


class ZoteroSyncResponse(BaseModel):
    """Response from Zotero sync operation."""
    success: bool
    items_synced: int = 0
    items_updated: int = 0
    items_failed: int = 0
    pdfs_downloaded: int = 0
    errors: Optional[List[str]] = None
    library_version: Optional[int] = None
    # For incremental sync support
    has_more: bool = False  # True if more items available to sync
    total_in_library: int = 0  # Total items in Zotero library/collection
    total_synced_so_far: int = 0  # Total items synced to this project
    next_start: int = 0  # Next offset for pagination


# =============================================================================
# Helper Functions
# =============================================================================

async def get_user_project(user: AuthenticatedUser, project_id: str):
    """Get and verify project ownership."""
    client = get_supabase_client()
    result = client.table("rag_projects").select("*").eq("id", project_id).single().execute()
    
    if not result.data:
        raise HTTPException(status_code=404, detail="RAG project not found")
    
    if result.data["user_id"] != str(user.id):
        raise HTTPException(status_code=403, detail="Access denied")
    
    return result.data


async def get_zotero_connection(project_id: str):
    """Get existing Zotero connection for a project."""
    client = get_supabase_client()
    result = client.table("zotero_connections").select("*").eq("rag_project_id", project_id).execute()
    # Return first result or None (don't use .single() which throws on 0 rows)
    return result.data[0] if result.data else None


# =============================================================================
# Endpoints
# =============================================================================

@router.post("/validate-credentials", response_model=ZoteroValidateResponse)
async def validate_credentials(
    project_id: str,
    request: ZoteroValidateRequest,
    user: AuthenticatedUser = Depends(get_current_user)
):
    """
    Test Zotero credentials without saving connection.
    
    Useful for validating API key before connecting.
    Returns detailed validation results and library info.
    """
    # Verify project ownership
    await get_user_project(user, project_id)
    
    is_valid, error_msg = validate_zotero_credentials(
        request.api_key,
        request.zotero_user_id,
        request.library_type
    )
    
    if is_valid:
        try:
            client = ZoteroClient(
                request.api_key,
                request.zotero_user_id,
                request.library_type
            )
            library_info = client.get_library_info()
            
            return ZoteroValidateResponse(
                valid=True,
                message="Credentials are valid!",
                library_info=ZoteroLibraryInfo(**library_info)
            )
        except Exception as e:
            return ZoteroValidateResponse(
                valid=True,
                message="Credentials validated but couldn't fetch library info",
                error=str(e)
            )
    else:
        return ZoteroValidateResponse(
            valid=False,
            error=error_msg,
            suggestions=[
                "Check that User ID is a number (not username)",
                "Verify Library Type is correct (Personal vs Group)",
                "For group libraries, use the Group ID (not User ID)",
                "Confirm API key has 'Allow library access' permission"
            ]
        )


@router.post("/connect", response_model=ZoteroConnectionResponse)
async def connect_zotero(
    project_id: str,
    request: ZoteroConnectionCreate,
    user: AuthenticatedUser = Depends(get_current_user)
):
    """
    Connect a Zotero account to this RAG project.
    
    Validates credentials and stores connection details.
    Each RAG project can have only one Zotero connection.
    """
    # Verify project ownership
    await get_user_project(user, project_id)
    
    # Validate credentials first
    is_valid, error_msg = validate_zotero_credentials(
        request.api_key,
        request.zotero_user_id,
        request.library_type
    )
    
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid Zotero credentials: {error_msg}"
        )
    
    client = get_supabase_client()
    
    # Check if connection already exists
    existing = await get_zotero_connection(project_id)
    
    if existing:
        # Update existing connection
        result = client.table("zotero_connections").update({
            "api_key": request.api_key,
            "zotero_user_id": request.zotero_user_id,
            "library_type": request.library_type,
            "selected_collection_key": request.selected_collection_key,
            "sync_pdfs": request.sync_pdfs,
            "last_sync_error": None,
            "updated_at": datetime.utcnow().isoformat(),
        }).eq("id", existing["id"]).execute()
        
        connection = result.data[0] if result.data else existing
    else:
        # Create new connection
        result = client.table("zotero_connections").insert({
            "rag_project_id": project_id,
            "api_key": request.api_key,
            "zotero_user_id": request.zotero_user_id,
            "library_type": request.library_type,
            "selected_collection_key": request.selected_collection_key,
            "sync_pdfs": request.sync_pdfs,
            "connected_by": str(user.id),
            "connected_at": datetime.utcnow().isoformat(),
        }).execute()
        
        connection = result.data[0]
    
    return ZoteroConnectionResponse(
        id=connection["id"],
        rag_project_id=connection["rag_project_id"],
        zotero_user_id=connection["zotero_user_id"],
        library_type=connection["library_type"],
        selected_collection_key=connection.get("selected_collection_key"),
        auto_sync_enabled=connection.get("auto_sync_enabled", False),
        sync_pdfs=connection.get("sync_pdfs", True),
        last_synced_at=connection.get("last_synced_at"),
        last_sync_version=connection.get("last_sync_version"),
        total_items_synced=connection.get("total_items_synced", 0),
        connected_at=connection["connected_at"],
        last_sync_error=connection.get("last_sync_error"),
    )


@router.get("/connection", response_model=Optional[ZoteroConnectionResponse])
async def get_connection(
    project_id: str,
    user: AuthenticatedUser = Depends(get_current_user)
):
    """
    Get the current Zotero connection for this RAG project.
    
    Returns null if no connection exists.
    API key is never returned.
    """
    # Verify project ownership
    await get_user_project(user, project_id)
    
    connection = await get_zotero_connection(project_id)
    
    if not connection:
        return None
    
    return ZoteroConnectionResponse(
        id=connection["id"],
        rag_project_id=connection["rag_project_id"],
        zotero_user_id=connection["zotero_user_id"],
        library_type=connection["library_type"],
        selected_collection_key=connection.get("selected_collection_key"),
        auto_sync_enabled=connection.get("auto_sync_enabled", False),
        sync_pdfs=connection.get("sync_pdfs", True),
        last_synced_at=connection.get("last_synced_at"),
        last_sync_version=connection.get("last_sync_version"),
        total_items_synced=connection.get("total_items_synced", 0),
        connected_at=connection["connected_at"],
        last_sync_error=connection.get("last_sync_error"),
    )


@router.delete("/disconnect")
async def disconnect_zotero(
    project_id: str,
    user: AuthenticatedUser = Depends(get_current_user)
):
    """
    Disconnect Zotero from this RAG project.
    
    This does NOT delete any synced documents or metadata.
    """
    # Verify project ownership
    await get_user_project(user, project_id)
    
    connection = await get_zotero_connection(project_id)
    
    if not connection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No Zotero connection found"
        )
    
    client = get_supabase_client()
    client.table("zotero_connections").delete().eq("id", connection["id"]).execute()
    
    return {"message": "Zotero disconnected successfully"}


@router.get("/collections", response_model=List[ZoteroCollectionInfo])
async def list_collections(
    project_id: str,
    user: AuthenticatedUser = Depends(get_current_user)
):
    """
    List all collections in the connected Zotero library.
    
    Requires an existing Zotero connection.
    """
    # Verify project ownership
    await get_user_project(user, project_id)
    
    connection = await get_zotero_connection(project_id)
    
    if not connection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No Zotero connection found. Please connect Zotero first."
        )
    
    try:
        client = ZoteroClient(
            connection["api_key"],
            connection["zotero_user_id"],
            connection["library_type"]
        )
        collections = client.list_collections()
        
        return [
            ZoteroCollectionInfo(
                key=c["key"],
                name=c["name"],
                num_items=c["num_items"],
                parent_collection=c["parent_collection"]
            )
            for c in collections
        ]
    except Exception as e:
        logger.error(f"Failed to list Zotero collections: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch collections: {str(e)}"
        )


@router.get("/library-info", response_model=ZoteroLibraryInfo)
async def get_library_info(
    project_id: str,
    user: AuthenticatedUser = Depends(get_current_user)
):
    """
    Get info about the connected Zotero library.
    
    Requires an existing Zotero connection.
    """
    # Verify project ownership
    await get_user_project(user, project_id)
    
    connection = await get_zotero_connection(project_id)
    
    if not connection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No Zotero connection found. Please connect Zotero first."
        )
    
    try:
        client = ZoteroClient(
            connection["api_key"],
            connection["zotero_user_id"],
            connection["library_type"]
        )
        info = client.get_library_info()
        
        return ZoteroLibraryInfo(**info)
    except Exception as e:
        logger.error(f"Failed to get Zotero library info: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch library info: {str(e)}"
        )


@router.post("/sync", response_model=ZoteroSyncResponse)
async def sync_from_zotero(
    project_id: str,
    request: ZoteroSyncRequest,
    user: AuthenticatedUser = Depends(get_current_user)
):
    """
    Sync items from Zotero to this RAG project.
    
    This will:
    1. Fetch items from Zotero (optionally from a specific collection)
    2. Match with existing documents by DOI/title
    3. Update metadata for matched documents
    4. Optionally download PDFs for new items and upload to R2
    """
    # Verify project ownership
    project = await get_user_project(user, project_id)
    
    connection = await get_zotero_connection(project_id)
    
    if not connection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No Zotero connection found. Please connect Zotero first."
        )
    
    errors: List[str] = []
    items_synced = 0
    items_updated = 0
    items_failed = 0
    pdfs_downloaded = 0
    
    try:
        zotero_client = ZoteroClient(
            connection["api_key"],
            connection["zotero_user_id"],
            connection["library_type"]
        )
        
        supabase = get_supabase_client()
        r2_client = get_r2_client()
        bucket_name = os.getenv("R2_BUCKET_NAME", "devchat-pdfs")
        
        # Get items with attachment info (paginated)
        # Limited to 20 items per sync to avoid Railway 120s timeout
        # Each item may need PDF download from Zotero + upload to R2
        logger.info(f"Fetching items from Zotero for project {project_id}, start={request.start}")
        items, next_raw_start, has_more_items = zotero_client.get_items_with_attachments(
            collection_key=request.collection_key,
            limit=50,  # Items per API call (raw, including attachments/notes)
            start=request.start,  # Pagination offset (raw API offset)
            max_items=20  # Total max filtered items per sync (reduced to avoid timeout)
        )
        
        logger.info(f"Found {len(items)} items in Zotero (raw offset {request.start} -> {next_raw_start})")
        
        # Get existing documents for matching
        existing_docs = supabase.table("documents").select(
            "id, filename, original_filename, metadata"
        ).eq("rag_project_id", project_id).execute()
        
        # Build lookup maps for matching
        doi_map = {}  # DOI -> document
        title_map = {}  # lowercase title -> document
        zotero_key_set = set()  # Already synced Zotero keys
        for doc in existing_docs.data:
            meta = doc.get("metadata", {}) or {}
            if meta.get("doi"):
                doi_map[meta["doi"].lower().strip()] = doc
            if meta.get("title"):
                title_map[meta["title"].lower().strip()] = doc
            if meta.get("zotero_key"):
                zotero_key_set.add(meta["zotero_key"])
        
        items_skipped = 0
        
        for item in items:
            try:
                item_key = item["key"]
                item_title = item.get("title", "")
                item_doi = item.get("doi", "")
                
                # Skip if this Zotero item was already synced
                if item_key in zotero_key_set:
                    items_skipped += 1
                    logger.debug(f"Skipping already-synced Zotero item: {item_key}")
                    continue
                
                # Try to match with existing document
                matched_doc = None
                match_method = None
                
                if item_doi:
                    normalized_doi = item_doi.lower().strip()
                    if normalized_doi in doi_map:
                        matched_doc = doi_map[normalized_doi]
                        match_method = "doi"
                
                if not matched_doc and item_title:
                    normalized_title = item_title.lower().strip()
                    if normalized_title in title_map:
                        matched_doc = title_map[normalized_title]
                        match_method = "title"
                
                if matched_doc:
                    # Update metadata for matched document
                    zotero_metadata = {
                        "zotero_key": item_key,
                        "zotero_synced_at": datetime.utcnow().isoformat(),
                        "item_type": item.get("item_type"),
                        "authors": item.get("authors", []),
                        "year": item.get("year"),
                        "journal": item.get("journal"),
                        "volume": item.get("volume"),
                        "issue": item.get("issue"),
                        "pages": item.get("pages"),
                        "abstract": item.get("abstract"),
                        "doi": item.get("doi") or matched_doc.get("metadata", {}).get("doi"),
                        "url": item.get("url"),
                        "metadata_source": "zotero",
                        "has_pdf": item.get("has_pdf", False),
                    }
                    
                    # Merge with existing metadata
                    existing_meta = matched_doc.get("metadata", {}) or {}
                    merged_meta = {**existing_meta, **zotero_metadata}
                    merged_meta["metadata_confidence"] = calculate_zotero_confidence(item)
                    
                    supabase.table("documents").update({
                        "metadata": merged_meta,
                        "metadata_confidence": calculate_zotero_confidence(item),
                    }).eq("id", matched_doc["id"]).execute()
                    
                    items_updated += 1
                    logger.debug(f"Updated metadata for document {matched_doc['id']} from Zotero item {item_key} (matched by {match_method})")
                    
                elif request.sync_pdfs:
                    # No match - try to download PDF (this checks for attachments lazily)
                    pdf_result = zotero_client.download_pdf_bytes(item_key)
                    
                    if pdf_result:
                        pdf_bytes, original_filename = pdf_result
                        
                        # Generate content hash
                        content_hash = hashlib.sha256(pdf_bytes).hexdigest()[:16]
                        safe_filename = original_filename.replace(" ", "_").replace("/", "_")
                        base_name = os.path.splitext(safe_filename)[0]
                        # Sanitize to ASCII for S3 metadata compatibility
                        ascii_base_name = sanitize_to_ascii(base_name)
                        
                        # Check if this exact content already exists
                        existing_hash = supabase.table("documents").select("id").eq(
                            "rag_project_id", project_id
                        ).ilike("metadata->>content_hash", content_hash).execute()
                        
                        if existing_hash.data:
                            logger.debug(f"Skipping {original_filename} - content already exists")
                            items_synced += 1
                            continue
                        
                        # Upload to R2 - use ASCII-safe doc_id for S3 metadata
                        doc_id = f"{content_hash}_{ascii_base_name}"
                        r2_key = f"rags/{project_id}/input-pdfs/{doc_id}.pdf"
                        
                        r2_client.put_object(
                            Bucket=bucket_name,
                            Key=r2_key,
                            Body=pdf_bytes,
                            ContentType="application/pdf",
                            Metadata={
                                "doc_id": doc_id,
                                "content_hash": content_hash,
                                "original_filename": sanitize_to_ascii(original_filename),
                                "upload_timestamp": datetime.utcnow().isoformat(),
                                "project_id": project_id,
                                "source": "zotero",
                                "zotero_key": item_key,
                            }
                        )
                        
                        # Create document record
                        doc_metadata = {
                            "content_hash": content_hash,
                            "zotero_key": item_key,
                            "zotero_synced_at": datetime.utcnow().isoformat(),
                            "title": item.get("title"),
                            "item_type": item.get("item_type"),
                            "authors": item.get("authors", []),
                            "year": item.get("year"),
                            "journal": item.get("journal"),
                            "volume": item.get("volume"),
                            "issue": item.get("issue"),
                            "pages": item.get("pages"),
                            "abstract": item.get("abstract"),
                            "doi": item.get("doi"),
                            "url": item.get("url"),
                            "metadata_source": "zotero",
                            "has_pdf": True,
                            "metadata_confidence": calculate_zotero_confidence(item),
                        }
                        
                        supabase.table("documents").upsert({
                            "rag_project_id": project_id,
                            "filename": doc_id,
                            "original_filename": original_filename,
                            "file_size_bytes": len(pdf_bytes),
                            "mime_type": "application/pdf",
                            "status": "pending",
                            "r2_input_key": r2_key,
                            "metadata": doc_metadata,
                            "metadata_confidence": calculate_zotero_confidence(item),
                        }, on_conflict="filename,rag_project_id").execute()
                        
                        pdfs_downloaded += 1
                        logger.info(f"Downloaded and uploaded PDF from Zotero: {original_filename}")
                    else:
                        # No PDF found - create metadata-only record
                        doc_id = f"zotero_{item_key}"
                        safe_title = (item.get("title") or "Untitled")[:100].replace(" ", "_").replace("/", "_")
                        
                        # Check if this zotero item already exists
                        existing_zotero = supabase.table("documents").select("id").eq(
                            "rag_project_id", project_id
                        ).eq("filename", doc_id).execute()
                        
                        if not existing_zotero.data:
                            doc_metadata = {
                                "zotero_key": item_key,
                                "zotero_synced_at": datetime.utcnow().isoformat(),
                                "title": item.get("title"),
                                "item_type": item.get("item_type"),
                                "authors": item.get("authors", []),
                                "year": item.get("year"),
                                "journal": item.get("journal"),
                                "volume": item.get("volume"),
                                "issue": item.get("issue"),
                                "pages": item.get("pages"),
                                "abstract": item.get("abstract"),
                                "doi": item.get("doi"),
                                "url": item.get("url"),
                                "metadata_source": "zotero",
                                "has_pdf": False,
                                "metadata_confidence": calculate_zotero_confidence(item),
                            }
                            
                            supabase.table("documents").insert({
                                "rag_project_id": project_id,
                                "filename": doc_id,
                                "original_filename": f"{safe_title}.pdf",
                                "file_size_bytes": 0,
                                "mime_type": "application/pdf",
                                "status": "no_pdf",
                                "metadata": doc_metadata,
                                "metadata_confidence": calculate_zotero_confidence(item),
                            }).execute()
                            logger.debug(f"Created metadata-only record for: {item.get('title')}")
                
                else:
                    # No match and no PDF - still create a metadata-only record
                    # Use zotero_key as unique identifier
                    doc_id = f"zotero_{item_key}"
                    safe_title = (item.get("title") or "Untitled")[:100].replace(" ", "_").replace("/", "_")
                    
                    # Check if this zotero item already exists
                    existing_zotero = supabase.table("documents").select("id").eq(
                        "rag_project_id", project_id
                    ).eq("filename", doc_id).execute()
                    
                    if existing_zotero.data:
                        logger.debug(f"Skipping {item_title} - already synced")
                        items_synced += 1
                        continue
                    
                    doc_metadata = {
                        "zotero_key": item_key,
                        "zotero_synced_at": datetime.utcnow().isoformat(),
                        "title": item.get("title"),
                        "item_type": item.get("item_type"),
                        "authors": item.get("authors", []),
                        "year": item.get("year"),
                        "journal": item.get("journal"),
                        "volume": item.get("volume"),
                        "issue": item.get("issue"),
                        "pages": item.get("pages"),
                        "abstract": item.get("abstract"),
                        "doi": item.get("doi"),
                        "url": item.get("url"),
                        "metadata_source": "zotero",
                        "has_pdf": False,  # Flag: no PDF available
                        "metadata_confidence": calculate_zotero_confidence(item),
                    }
                    
                    supabase.table("documents").insert({
                        "rag_project_id": project_id,
                        "filename": doc_id,
                        "original_filename": f"{safe_title}.pdf",  # Placeholder name
                        "file_size_bytes": 0,
                        "mime_type": "application/pdf",
                        "status": "no_pdf",  # Special status for items without PDF
                        "metadata": doc_metadata,
                        "metadata_confidence": calculate_zotero_confidence(item),
                    }).execute()
                    
                    logger.debug(f"Created metadata-only record for: {item_title}")
                
                items_synced += 1
                
            except Exception as item_error:
                items_failed += 1
                error_msg = f"Failed to sync item {item.get('key', 'unknown')}: {str(item_error)}"
                errors.append(error_msg)
                logger.warning(error_msg)
        
        # Update sync metadata
        supabase.table("zotero_connections").update({
            "last_synced_at": datetime.utcnow().isoformat(),
            "total_items_synced": items_synced,
            "last_sync_error": errors[0] if errors else None,
        }).eq("id", connection["id"]).execute()
        
        logger.info(f"Zotero sync complete: {items_synced} synced, {items_updated} updated, {pdfs_downloaded} PDFs, {items_skipped} skipped, {items_failed} failed")
        
        # Get total items in library and total synced so far
        total_in_library = zotero_client.zot.num_items()
        total_synced_docs = supabase.table("documents").select("id", count="exact").eq(
            "rag_project_id", project_id
        ).execute()
        total_synced_so_far = total_synced_docs.count or 0
        
        # Use raw offset from get_items_with_attachments for proper pagination
        # next_raw_start tracks raw API position (including attachments/notes)
        # has_more_items comes from the function and accounts for filtered items
        
        return ZoteroSyncResponse(
            success=items_failed == 0,
            items_synced=items_synced,
            items_updated=items_updated,
            items_failed=items_failed,
            pdfs_downloaded=pdfs_downloaded,
            errors=errors if errors else None,
            library_version=None,
            has_more=has_more_items,
            total_in_library=total_in_library,
            total_synced_so_far=total_synced_so_far,
            next_start=next_raw_start,
        )
        
    except Exception as e:
        logger.error(f"Zotero sync failed: {e}")
        
        # Record the error
        supabase = get_supabase_client()
        supabase.table("zotero_connections").update({
            "last_sync_error": str(e),
        }).eq("id", connection["id"]).execute()
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Sync failed: {str(e)}"
        )
