"""
Admin Storage Routes

Endpoints for file upload and R2 storage management.
"""

import hashlib
import os
from datetime import datetime

from botocore.exceptions import ClientError
from fastapi import APIRouter, BackgroundTasks, File, HTTPException, Query, UploadFile

from api.schemas import UploadResponse
from src.utils.logging import get_logger

from ..dependencies import (
    get_r2_client,
    invalidate_admin_caches,
    trigger_modal_processing,
)

logger = get_logger(__name__)

router = APIRouter()


def compute_content_hash(content: bytes) -> str:
    """
    Compute a stable content hash for deduplication.
    Uses first 8 chars of MD5 for compact IDs while being collision-resistant enough.
    """
    return hashlib.md5(content).hexdigest()[:8]


def find_existing_document(r2_client, bucket_name: str, content_hash: str, base_name: str) -> dict | None:
    """
    Check if a document with the same content hash already exists in R2.
    
    Returns:
        dict with existing doc info if found, None otherwise
    """
    try:
        # List all files with input-pdfs/ prefix
        paginator = r2_client.get_paginator('list_objects_v2')
        for page in paginator.paginate(Bucket=bucket_name, Prefix="input-pdfs/"):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if key.endswith(".pdf"):
                    # Extract doc_id from key
                    filename = key.split("/")[-1]
                    doc_id = filename.rsplit(".", 1)[0]
                    
                    # Check if this file has the same content hash prefix
                    if doc_id.startswith(f"{content_hash}_"):
                        return {
                            "key": key,
                            "doc_id": doc_id,
                            "size": obj.get("Size", 0),
                        }
                    
                    # Also check by base_name for fuzzy match warning
                    # (different hash but same name = possibly same doc re-uploaded)
    except Exception as e:
        logger.warning(f"Error checking for existing documents: {e}")
    
    return None


# =============================================================================
# File Upload and R2 Management
# =============================================================================

@router.post("/upload", response_model=UploadResponse)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    force_upload: bool = Query(False, description="Upload even if duplicate exists"),
):
    """
    Upload a document to R2 for processing.
    
    Uses content-based deduplication:
    - Computes MD5 hash of file content
    - If same content already exists, returns existing doc_id (no duplicate)
    - If force_upload=True, uploads anyway with new ID
    
    The file will be stored in the input-pdfs/ prefix and queued for
    processing by the Modal MinerU pipeline.
    """
    # Validate file type
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")
    
    allowed_extensions = {".pdf", ".docx", ".doc", ".txt", ".md"}
    file_ext = os.path.splitext(file.filename)[1].lower()
    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"File type {file_ext} not allowed. Allowed: {allowed_extensions}"
        )
    
    try:
        # Read file content first for deduplication
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
            existing = find_existing_document(r2_client, bucket_name, content_hash, base_name)
            if existing:
                logger.info(f"Duplicate detected: {file.filename} matches existing {existing['doc_id']}")
                return UploadResponse(
                    success=True,
                    filename=file.filename,
                    r2_key=existing["key"],
                    size_bytes=existing["size"],
                    queued_for_processing=False,  # Already exists, no need to reprocess
                    doc_id=existing["doc_id"],
                    message=f"Document already exists as {existing['doc_id']}. No duplicate created.",
                    is_duplicate=True,
                )
        
        # Generate doc_id using content hash (same content = same ID)
        # Format: {content_hash}_{sanitized_basename}
        doc_id = f"{content_hash}_{base_name}"
        r2_key = f"input-pdfs/{doc_id}{file_ext}"
        
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
            }
        )
        
        logger.info(f"Uploaded {file.filename} to R2 as {r2_key} (doc_id={doc_id}, hash={content_hash}, {size_bytes} bytes)")
        invalidate_admin_caches()
        
        # Automatically trigger processing in background
        background_tasks.add_task(trigger_modal_processing, force_reprocess=False, max_documents=1)
        
        return UploadResponse(
            success=True,
            filename=file.filename,
            r2_key=r2_key,
            size_bytes=size_bytes,
            queued_for_processing=True,
            doc_id=doc_id,  # Return the doc_id for reference
        )
        
    except ClientError as e:
        logger.error(f"R2 upload failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to upload to R2: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Upload failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Upload failed: {str(e)}"
        )


@router.get("/r2/list")
async def list_r2_files(prefix: str = Query("input-pdfs/", description="Prefix to list")):
    """
    List files in R2 bucket.
    """
    try:
        r2_client = get_r2_client()
        bucket_name = os.getenv("R2_BUCKET_NAME", "devchat-pdfs")
        
        response = r2_client.list_objects_v2(
            Bucket=bucket_name,
            Prefix=prefix,
            MaxKeys=100,
        )
        
        files = []
        for obj in response.get("Contents", []):
            files.append({
                "key": obj["Key"],
                "size_bytes": obj["Size"],
                "last_modified": obj["LastModified"].isoformat(),
            })
        
        return {
            "prefix": prefix,
            "file_count": len(files),
            "files": files,
        }
        
    except ClientError as e:
        logger.error(f"R2 list failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list R2: {str(e)}")


@router.get("/pdf/{document_id:path}")
async def get_pdf_url(document_id: str):
    """
    Get a presigned URL to view a PDF document.
    
    Returns a temporary URL (valid for 1 hour) that can be used to view the PDF.
    """
    try:
        r2_client = get_r2_client()
        bucket_name = os.getenv("R2_BUCKET_NAME", "devchat-pdfs")
        
        # Try input-pdfs first (original uploaded PDF)
        r2_key = f"input-pdfs/{document_id}.pdf"
        
        # Check if file exists
        try:
            r2_client.head_object(Bucket=bucket_name, Key=r2_key)
        except ClientError:
            # Try without .pdf extension (in case document_id already has it)
            if document_id.endswith('.pdf'):
                r2_key = f"input-pdfs/{document_id}"
                try:
                    r2_client.head_object(Bucket=bucket_name, Key=r2_key)
                except ClientError:
                    raise HTTPException(status_code=404, detail=f"PDF not found: {document_id}")
            else:
                raise HTTPException(status_code=404, detail=f"PDF not found: {document_id}")
        
        # Generate presigned URL (valid for 1 hour)
        presigned_url = r2_client.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': bucket_name,
                'Key': r2_key,
            },
            ExpiresIn=3600,  # 1 hour
        )
        
        return {
            "document_id": document_id,
            "url": presigned_url,
            "expires_in": 3600,
            "r2_key": r2_key,
        }
        
    except HTTPException:
        raise
    except ClientError as e:
        logger.error(f"Failed to generate presigned URL: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get PDF URL: {str(e)}")


@router.get("/duplicates")
async def find_duplicates():
    """
    Find duplicate PDFs in R2 (same base name with different hash prefixes).
    
    Returns groups of duplicates that should be cleaned up.
    """
    try:
        r2_client = get_r2_client()
        bucket_name = os.getenv("R2_BUCKET_NAME", "devchat-pdfs")
        
        # Get all PDFs
        pdf_files = {}
        paginator = r2_client.get_paginator('list_objects_v2')
        for page in paginator.paginate(Bucket=bucket_name, Prefix="input-pdfs/"):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if key.endswith(".pdf"):
                    doc_id = key.split("/")[-1].rsplit(".", 1)[0]
                    pdf_files[doc_id] = {
                        "key": key,
                        "size": obj.get("Size", 0),
                        "modified": obj.get("LastModified").isoformat() if obj.get("LastModified") else None,
                    }
        
        # Extract base names and find duplicates
        def extract_base_name(doc_id: str) -> str:
            if "_" in doc_id and len(doc_id.split("_")[0]) == 8:
                return "_".join(doc_id.split("_")[1:])
            return doc_id
        
        base_name_groups = {}
        for doc_id, info in pdf_files.items():
            base = extract_base_name(doc_id)
            if base not in base_name_groups:
                base_name_groups[base] = []
            base_name_groups[base].append({"doc_id": doc_id, **info})
        
        # Find duplicates (more than one version)
        duplicates = {
            base: files 
            for base, files in base_name_groups.items() 
            if len(files) > 1
        }
        
        return {
            "total_pdfs": len(pdf_files),
            "unique_base_names": len(base_name_groups),
            "duplicate_groups": len(duplicates),
            "duplicates": duplicates,
        }
        
    except Exception as e:
        logger.error(f"Failed to find duplicates: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/duplicates/cleanup")
async def cleanup_duplicates(dry_run: bool = Query(True, description="If true, only report what would be deleted")):
    """
    Clean up duplicate PDFs, keeping only the one that's indexed in Qdrant.
    
    For each duplicate group:
    1. Check which version is indexed in Qdrant
    2. Keep the indexed version, delete the others
    3. If none indexed, keep the most recent one
    """
    from ..dependencies import get_indexer
    
    try:
        r2_client = get_r2_client()
        bucket_name = os.getenv("R2_BUCKET_NAME", "devchat-pdfs")
        indexer = get_indexer()
        
        # First, find duplicates
        duplicates_result = await find_duplicates()
        duplicates = duplicates_result["duplicates"]
        
        if not duplicates:
            return {"message": "No duplicates found", "deleted": 0}
        
        # Get indexed doc_ids from Qdrant
        indexed_doc_ids = set()
        try:
            next_offset = None
            while True:
                results, next_offset = indexer.client.scroll(
                    collection_name=indexer.collection_name,
                    limit=1000,
                    offset=next_offset,
                    with_payload=["doc_id", "pdf_name"],
                    with_vectors=False,
                )
                for point in results:
                    payload = point.payload or {}
                    doc_id = payload.get("doc_id") or payload.get("pdf_name")
                    if doc_id:
                        indexed_doc_ids.add(doc_id)
                if next_offset is None or len(results) == 0:
                    break
        except Exception as e:
            logger.warning(f"Could not get indexed doc_ids: {e}")
        
        # Determine which files to delete
        to_delete = []
        to_keep = []
        
        for base_name, files in duplicates.items():
            # Find which one is indexed
            indexed_file = None
            for f in files:
                if f["doc_id"] in indexed_doc_ids:
                    indexed_file = f
                    break
            
            if indexed_file:
                # Keep the indexed one, delete others
                for f in files:
                    if f["doc_id"] != indexed_file["doc_id"]:
                        to_delete.append(f)
                    else:
                        to_keep.append(f)
            else:
                # Keep the most recent one
                sorted_files = sorted(files, key=lambda x: x.get("modified", ""), reverse=True)
                to_keep.append(sorted_files[0])
                to_delete.extend(sorted_files[1:])
        
        if dry_run:
            return {
                "dry_run": True,
                "would_delete": len(to_delete),
                "would_keep": len(to_keep),
                "files_to_delete": [f["key"] for f in to_delete],
                "files_to_keep": [f["doc_id"] for f in to_keep],
            }
        
        # Actually delete the files
        deleted = []
        for f in to_delete:
            try:
                r2_client.delete_object(Bucket=bucket_name, Key=f["key"])
                deleted.append(f["key"])
                logger.info(f"Deleted duplicate: {f['key']}")
            except Exception as e:
                logger.error(f"Failed to delete {f['key']}: {e}")
        
        invalidate_admin_caches()
        
        return {
            "dry_run": False,
            "deleted": len(deleted),
            "deleted_files": deleted,
            "kept": len(to_keep),
        }
        
    except Exception as e:
        logger.error(f"Cleanup failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
