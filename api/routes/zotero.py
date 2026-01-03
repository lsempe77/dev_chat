"""
Zotero Integration API Routes for RAG Projects

Handles Zotero account connection, collection listing, and item sync.
"""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from src.auth import AuthenticatedUser, get_current_user, get_supabase_client
from src.utils.logging import get_logger
from src.utils.zotero_client import ZoteroClient, validate_zotero_credentials

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


class ZoteroSyncResponse(BaseModel):
    """Response from Zotero sync operation."""
    success: bool
    items_synced: int = 0
    items_updated: int = 0
    items_failed: int = 0
    pdfs_downloaded: int = 0
    errors: Optional[List[str]] = None
    library_version: Optional[int] = None


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
    4. Optionally download PDFs for new items
    
    Note: This is a placeholder for full sync implementation.
    """
    # Verify project ownership
    project = await get_user_project(user, project_id)
    
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
        
        # Get items (from collection or entire library)
        version = None
        if request.collection_key:
            items, total = client.get_collection_items(request.collection_key)
        else:
            items, total, version = client.get_all_items()
        
        # TODO: Implement full sync logic:
        # 1. Match items with existing documents by DOI
        # 2. Update metadata for matched documents
        # 3. Create new documents for unmatched items (if PDFs available)
        # 4. Download PDFs if sync_pdfs is True
        
        # For now, just update the sync metadata
        supabase = get_supabase_client()
        supabase.table("zotero_connections").update({
            "last_synced_at": datetime.utcnow().isoformat(),
            "total_items_synced": len(items),
            "last_sync_error": None,
        }).eq("id", connection["id"]).execute()
        
        return ZoteroSyncResponse(
            success=True,
            items_synced=len(items),
            items_updated=0,  # TODO: track actual updates
            items_failed=0,
            pdfs_downloaded=0,
            library_version=version if not request.collection_key else None,
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
