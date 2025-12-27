"""
Admin Jobs Routes

Endpoints for processing job management.
"""

import os

from fastapi import APIRouter, HTTPException

from api.schemas import (
    ProcessingJob,
    ProcessingJobsResponse,
    TriggerProcessingRequest,
    TriggerProcessingResponse,
)
from src.utils.logging import get_logger

from ..dependencies import (
    get_documents_cache,
    get_indexer,
    get_r2_client,
    trigger_modal_processing,
)

logger = get_logger(__name__)

router = APIRouter()


# =============================================================================
# Processing Jobs
# =============================================================================

@router.get("/jobs", response_model=ProcessingJobsResponse)
async def get_processing_jobs():
    """
    Get list of processing jobs with their status.
    
    Shows:
    - Pending: Files in R2 input-pdfs/ that are not yet indexed in Qdrant
    - Completed: Files that have been indexed in Qdrant
    """
    jobs = []
    documents_cache = get_documents_cache()
    
    try:
        # Get files from R2
        r2_client = get_r2_client()
        bucket_name = os.getenv("R2_BUCKET_NAME", "devchat-pdfs")
        
        r2_files = {}
        paginator = r2_client.get_paginator('list_objects_v2')
        for page in paginator.paginate(Bucket=bucket_name, Prefix="input-pdfs/"):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if key.endswith(".pdf"):
                    doc_id = key.split("/")[-1].rsplit(".", 1)[0]
                    r2_files[doc_id] = {
                        "key": key,
                        "size": obj.get("Size", 0),
                        "uploaded_at": obj.get("LastModified"),
                    }
        
        # Get indexed doc_ids from Qdrant
        indexed_doc_ids = set()
        
        # Optimization: Use cache if available
        if documents_cache["data"] is not None:
            # Extract IDs from cached response
            for doc in documents_cache["data"].documents:
                indexed_doc_ids.add(doc.id)
        else:
            # Fallback: Scroll through to get unique doc_ids
            try:
                indexer = get_indexer()
                next_offset = None
                # Limit scroll to avoid timeout - we might miss some if > 5000
                MAX_SCROLL = 5000
                count = 0
                
                while count < MAX_SCROLL:
                    results, next_offset = indexer.client.scroll(
                        collection_name=indexer.collection_name,
                        limit=100,
                        offset=next_offset,
                        with_payload=["doc_id", "pdf_name"],
                        with_vectors=False,
                    )
                    for point in results:
                        payload = point.payload or {}
                        doc_id = payload.get("doc_id") or payload.get("pdf_name")
                        if doc_id:
                            indexed_doc_ids.add(doc_id)
                    
                    count += len(results)
                    if next_offset is None or len(results) == 0:
                        break
            except Exception as e:
                logger.warning(f"Could not get indexed doc_ids: {e}")
        
        # Create job entries
        for doc_id, file_info in r2_files.items():
            is_indexed = doc_id in indexed_doc_ids
            jobs.append(ProcessingJob(
                id=f"job-{doc_id[:8]}",
                filename=file_info["key"].split("/")[-1],
                status="completed" if is_indexed else "queued",
                progress=100 if is_indexed else 0,
                started_at=file_info.get("uploaded_at"),
                completed_at=file_info.get("uploaded_at") if is_indexed else None,
                doc_id=doc_id,
            ))
        
        # Sort: queued first, then by filename
        jobs.sort(key=lambda j: (j.status != "queued", j.filename))
        
    except Exception as e:
        logger.error(f"Failed to get processing jobs: {e}")
        # Return empty list on error
        pass
    
    return ProcessingJobsResponse(
        jobs=jobs,
        queued_count=sum(1 for j in jobs if j.status == "queued"),
        processing_count=sum(1 for j in jobs if j.status == "processing"),
        completed_count=sum(1 for j in jobs if j.status == "completed"),
        failed_count=sum(1 for j in jobs if j.status == "failed"),
    )


@router.post("/jobs/trigger", response_model=TriggerProcessingResponse)
async def trigger_processing_endpoint(request: TriggerProcessingRequest):
    """
    Trigger batch processing of pending PDFs.
    
    Calls the Modal web endpoint to process new PDFs.
    This works from Railway (unlike subprocess which needs modal CLI).
    """
    try:
        # Use the helper function - now returns result or raises
        result = await trigger_modal_processing(
            force_reprocess=request.force_reprocess if hasattr(request, 'force_reprocess') else False,
            max_documents=request.max_documents or 10
        )
        
        if result:
            return TriggerProcessingResponse(
                queued=result.get("queued", 0),
                skipped=result.get("skipped", 0),
                message=result.get("message", "Processing triggered successfully"),
            )
        else:
            return TriggerProcessingResponse(
                queued=0,
                skipped=0,
                message="Processing triggered (no response from Modal)",
            )
    except Exception as e:
        logger.error(f"Modal trigger failed: {e}")
        raise HTTPException(
            status_code=503,
            detail=f"Failed to trigger Modal processing: {str(e)}. Modal may be cold starting - try again in 30 seconds."
        )


# =============================================================================
# Processing Control (Pause/Resume)
# =============================================================================

@router.get("/jobs/status")
async def get_processing_status():
    """
    Get the current processing status (paused or active).
    """
    try:
        r2_client = get_r2_client()
        bucket_name = os.getenv("R2_BUCKET_NAME", "devchat-pdfs")
        
        try:
            r2_client.head_object(Bucket=bucket_name, Key="system/processing_paused")
            return {"status": "paused", "message": "Automatic processing is paused"}
        except Exception:
            return {"status": "active", "message": "Automatic processing is active"}
    except Exception as e:
        logger.error(f"Failed to get processing status: {e}")
        return {"status": "unknown", "error": str(e)}


@router.post("/jobs/pause")
async def pause_processing():
    """
    Pause automatic scheduled processing.
    
    Creates a flag file in R2 that the scheduled job checks.
    Manual triggers still work - this only pauses the hourly scheduled runs.
    """
    try:
        r2_client = get_r2_client()
        bucket_name = os.getenv("R2_BUCKET_NAME", "devchat-pdfs")
        
        # Create the pause flag
        r2_client.put_object(
            Bucket=bucket_name,
            Key="system/processing_paused",
            Body=b"paused",
            ContentType="text/plain",
        )
        
        logger.info("Processing paused")
        return {"success": True, "status": "paused", "message": "Automatic processing paused. Manual triggers still work."}
    except Exception as e:
        logger.error(f"Failed to pause processing: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/jobs/resume")
async def resume_processing():
    """
    Resume automatic scheduled processing.
    
    Removes the pause flag from R2.
    """
    try:
        r2_client = get_r2_client()
        bucket_name = os.getenv("R2_BUCKET_NAME", "devchat-pdfs")
        
        # Remove the pause flag
        try:
            r2_client.delete_object(Bucket=bucket_name, Key="system/processing_paused")
        except Exception:
            pass  # Already not paused
        
        logger.info("Processing resumed")
        return {"success": True, "status": "active", "message": "Automatic processing resumed."}
    except Exception as e:
        logger.error(f"Failed to resume processing: {e}")
        raise HTTPException(status_code=500, detail=str(e))
