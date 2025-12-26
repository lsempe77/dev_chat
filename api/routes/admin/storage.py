"""
Admin Storage Routes

Endpoints for file upload and R2 storage management.
"""

import os
from datetime import datetime
from uuid import uuid4

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


# =============================================================================
# File Upload and R2 Management
# =============================================================================

@router.post("/upload", response_model=UploadResponse)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
):
    """
    Upload a document to R2 for processing.
    
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
    
    # Generate universal document ID (used across R2, Qdrant, Modal, etc.)
    unique_id = str(uuid4())[:8]
    safe_filename = file.filename.replace(" ", "_").replace("/", "_")
    base_name = os.path.splitext(safe_filename)[0]
    
    # doc_id format: {8-char-uuid}_{sanitized_basename}
    # This ID is used consistently across all systems
    doc_id = f"{unique_id}_{base_name}"
    
    r2_key = f"input-pdfs/{doc_id}{file_ext}"
    
    try:
        # Read file content
        content = await file.read()
        size_bytes = len(content)
        
        # Upload to R2
        r2_client = get_r2_client()
        bucket_name = os.getenv("R2_BUCKET_NAME", "devchat-pdfs")
        
        r2_client.put_object(
            Bucket=bucket_name,
            Key=r2_key,
            Body=content,
            ContentType=file.content_type or "application/pdf",
            Metadata={
                "doc_id": doc_id,  # Universal document ID
                "original_filename": file.filename,
                "upload_timestamp": datetime.utcnow().isoformat(),
            }
        )
        
        logger.info(f"Uploaded {file.filename} to R2 as {r2_key} (doc_id={doc_id}, {size_bytes} bytes)")
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
