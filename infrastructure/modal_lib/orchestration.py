"""
Orchestration functions for batch PDF processing.

Contains:
- orchestrate: Process all PDFs in global input-pdfs folder
- orchestrate_rag: Process all PDFs for a specific RAG project
- list_pdfs: List PDFs and processing status
- check_qdrant: Check Qdrant connection status
"""

import os
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Optional

from .config import (
    app,
    base_image,
    r2_secret,
    qdrant_secret,
    cohere_secret,
    supabase_secret,
    QDRANT_COLLECTION_NAME,
)
from .utils import get_r2_client, get_bucket_name
from .processing import process_pdf, process_pdf_rag, check_qdrant_indexed


# ============================================================================
# Global Orchestrator
# ============================================================================

@app.function(
    image=base_image,
    secrets=[r2_secret, qdrant_secret],
    timeout=300,
)
def orchestrate(force_reprocess: bool = False, check_qdrant: bool = True, max_documents: int = 0) -> dict:
    """
    Scan R2 for new PDFs and queue them for processing.
    
    Smart deduplication:
    1. Checks if JSON output exists in R2 (fast)
    2. Optionally checks if chunks exist in Qdrant (thorough)
    3. Can force reprocess with force_reprocess=True
    
    Args:
        force_reprocess: If True, reprocess all PDFs even if outputs exist
        check_qdrant: If True, also verify Qdrant indexing (slower but thorough)
        max_documents: Maximum number of PDFs to queue (0 = unlimited)
        
    Returns:
        dict with counts of queued, skipped, and failed PDFs
    """
    import boto3
    from qdrant_client import QdrantClient
    
    # Safety check for duplicates
    print("Running Qdrant duplication safety check...")
    try:
        qdrant = QdrantClient(
            url=os.environ["QDRANT_URL"],
            api_key=os.environ["QDRANT_API_KEY"],
        )
        
        doc_counts = Counter()
        offset = None
        sample_count = 0
        while sample_count < 2000:
            pts, offset = qdrant.scroll(
                QDRANT_COLLECTION_NAME, limit=500, offset=offset, with_payload=["doc_id"]
            )
            for p in pts:
                doc_counts[p.payload.get("doc_id")] += 1
            sample_count += len(pts)
            if offset is None:
                break
        
        if doc_counts:
            max_dup = max(doc_counts.values())
            worst_doc = max(doc_counts, key=doc_counts.get)
            if max_dup > 10:
                print(f"⚠️ WARNING: Detected high duplication! {worst_doc} has {max_dup} copies")
            else:
                print(f"  ✓ Duplication check passed (max {max_dup}x)")
    except Exception as e:
        print(f"  Note: Could not run duplication check: {e}")
    
    s3 = get_r2_client()
    bucket = get_bucket_name()
    
    # List input PDFs with pagination
    input_prefix = "input-pdfs/"
    pdf_keys = []
    continuation_token = None
    
    while True:
        if continuation_token:
            response = s3.list_objects_v2(Bucket=bucket, Prefix=input_prefix, ContinuationToken=continuation_token)
        else:
            response = s3.list_objects_v2(Bucket=bucket, Prefix=input_prefix)
        
        if "Contents" in response:
            pdf_keys.extend([obj["Key"] for obj in response["Contents"] if obj["Key"].lower().endswith(".pdf")])
        
        if response.get("IsTruncated"):
            continuation_token = response.get("NextContinuationToken")
        else:
            break
    
    if not pdf_keys:
        return {"message": "No PDFs found in input-pdfs/", "queued": 0}
    
    print(f"Found {len(pdf_keys)} PDFs in R2")
    
    # Detect duplicates by base name
    def extract_base_name(pdf_key: str) -> str:
        stem = Path(pdf_key).stem
        if "_" in stem and len(stem.split("_")[0]) == 8:
            return "_".join(stem.split("_")[1:])
        return stem
    
    base_name_to_keys = {}
    for pdf_key in pdf_keys:
        base = extract_base_name(pdf_key)
        if base not in base_name_to_keys:
            base_name_to_keys[base] = []
        base_name_to_keys[base].append(pdf_key)
    
    duplicates = {base: keys for base, keys in base_name_to_keys.items() if len(keys) > 1}
    if duplicates:
        print(f"⚠ Found {len(duplicates)} duplicate base names")
    
    # Check existing outputs
    output_prefix = "outputs/json/"
    existing_outputs = set()
    continuation_token = None
    
    while True:
        if continuation_token:
            response = s3.list_objects_v2(Bucket=bucket, Prefix=output_prefix, ContinuationToken=continuation_token)
        else:
            response = s3.list_objects_v2(Bucket=bucket, Prefix=output_prefix)
        
        if "Contents" in response:
            existing_outputs.update(Path(obj["Key"]).stem for obj in response["Contents"])
        
        if response.get("IsTruncated"):
            continuation_token = response.get("NextContinuationToken")
        else:
            break
    
    print(f"Found {len(existing_outputs)} existing JSON outputs")
    
    indexed_base_names = set()
    for output_name in existing_outputs:
        indexed_base_names.add(extract_base_name(f"{output_name}.pdf"))
    
    # Queue processing
    queued = []
    skipped_r2 = []
    skipped_qdrant = []
    needs_reindex = []
    skipped_limit = []
    skipped_errors = []
    skipped_duplicates = []
    
    for pdf_key in pdf_keys:
        pdf_name = Path(pdf_key).stem
        base_name = extract_base_name(pdf_key)
        
        if base_name in indexed_base_names and pdf_name not in existing_outputs:
            skipped_duplicates.append(pdf_key)
            print(f"  🔄 Skipping duplicate: {pdf_key}")
            continue
        
        has_r2_output = pdf_name in existing_outputs
        
        if has_r2_output and not force_reprocess:
            if check_qdrant:
                is_indexed, chunk_count, qdrant_error = check_qdrant_indexed(pdf_name)
                
                if qdrant_error:
                    skipped_errors.append({"key": pdf_key, "error": qdrant_error})
                    print(f"  ❌ Skipping (Qdrant error): {pdf_key}")
                    continue
                
                if is_indexed:
                    skipped_qdrant.append({"key": pdf_key, "chunks": chunk_count})
                    print(f"  ✓ Skipping (R2 + Qdrant OK): {pdf_key}")
                    continue
                else:
                    if max_documents > 0 and (len(queued) + len(needs_reindex)) >= max_documents:
                        skipped_limit.append(pdf_key)
                        continue
                    needs_reindex.append(pdf_key)
                    print(f"  ⚠ Re-indexing: {pdf_key}")
                    process_pdf.spawn(pdf_key=pdf_key, skip_extraction=True)
                    continue
            else:
                skipped_r2.append(pdf_key)
                continue
        
        if max_documents > 0 and (len(queued) + len(needs_reindex)) >= max_documents:
            skipped_limit.append(pdf_key)
            continue
        
        print(f"  Queuing: {pdf_key}")
        process_pdf.spawn(pdf_key=pdf_key, skip_extraction=False)
        queued.append(pdf_key)
    
    return {
        "queued": len(queued),
        "skipped_r2_only": len(skipped_r2),
        "skipped_fully_indexed": len(skipped_qdrant),
        "skipped_qdrant_errors": len(skipped_errors),
        "skipped_duplicates": len(skipped_duplicates),
        "needs_reindex": len(needs_reindex),
        "skipped_limit": len(skipped_limit),
        "max_documents": max_documents,
        "total": len(pdf_keys),
        "duplicate_groups": len(duplicates),
        "queued_files": queued[:10],
        "reindex_files": needs_reindex[:10],
    }


# ============================================================================
# RAG Project Orchestrator
# ============================================================================

@app.function(
    image=base_image,
    secrets=[r2_secret, qdrant_secret, cohere_secret, supabase_secret],
    timeout=3600,
)
def orchestrate_rag(
    project_id: str,
    qdrant_collection: Optional[str] = None,
    force_reprocess: bool = False,
    max_documents: int = 0,
) -> dict:
    """
    Process all documents for a specific RAG project.
    
    Called from the backend API when user clicks "Process Documents".
    
    Args:
        project_id: The RAG project UUID
        qdrant_collection: Optional override (default: lookup from database)
        force_reprocess: If True, reprocess all PDFs
        max_documents: Max docs to process (0 = unlimited)
        
    Returns:
        dict with processing stats
    """
    import boto3
    from supabase import create_client
    from qdrant_client import QdrantClient
    
    s3 = get_r2_client()
    bucket = get_bucket_name()
    
    supabase = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])
    
    # Get collection name from database if not provided
    if not qdrant_collection:
        project_result = supabase.table("rag_projects").select("qdrant_collection").eq("id", project_id).single().execute()
        if project_result.data and project_result.data.get("qdrant_collection"):
            collection = project_result.data["qdrant_collection"]
        else:
            collection = f"rag_{project_id}"
    else:
        collection = qdrant_collection
    
    input_prefix = f"rags/{project_id}/input-pdfs/"
    output_prefix = f"rags/{project_id}/outputs/"
    
    print(f"Processing RAG project: {project_id}")
    print(f"  Input prefix: {input_prefix}")
    print(f"  Qdrant collection: {collection}")
    
    # List input PDFs
    pdf_keys = []
    continuation_token = None
    
    while True:
        if continuation_token:
            response = s3.list_objects_v2(Bucket=bucket, Prefix=input_prefix, ContinuationToken=continuation_token)
        else:
            response = s3.list_objects_v2(Bucket=bucket, Prefix=input_prefix)
        
        if "Contents" in response:
            pdf_keys.extend([obj["Key"] for obj in response["Contents"] if obj["Key"].lower().endswith(".pdf")])
        
        if response.get("IsTruncated"):
            continuation_token = response.get("NextContinuationToken")
        else:
            break
    
    if not pdf_keys:
        return {"message": "No PDFs found", "queued": 0, "project_id": project_id}
    
    print(f"Found {len(pdf_keys)} PDFs")
    
    # Check existing outputs
    existing_outputs = set()
    json_prefix = f"{output_prefix}json/"
    continuation_token = None
    
    while True:
        if continuation_token:
            response = s3.list_objects_v2(Bucket=bucket, Prefix=json_prefix, ContinuationToken=continuation_token)
        else:
            response = s3.list_objects_v2(Bucket=bucket, Prefix=json_prefix)
        
        if "Contents" in response:
            for obj in response["Contents"]:
                existing_outputs.add(Path(obj["Key"]).stem)
        
        if response.get("IsTruncated"):
            continuation_token = response.get("NextContinuationToken")
        else:
            break
    
    print(f"Found {len(existing_outputs)} existing outputs")
    
    # Check Qdrant for existing vectors
    qdrant_indexed = set()
    try:
        qdrant = QdrantClient(url=os.environ["QDRANT_URL"], api_key=os.environ["QDRANT_API_KEY"])
        
        try:
            qdrant.get_collection(collection)
            offset = None
            while True:
                results, next_offset = qdrant.scroll(collection_name=collection, limit=100, with_payload=["source"], offset=offset)
                for point in results:
                    source = point.payload.get("source", "")
                    if source:
                        qdrant_indexed.add(source.replace(".pdf", ""))
                if next_offset is None:
                    break
                offset = next_offset
            print(f"Found {len(qdrant_indexed)} documents in Qdrant")
        except Exception:
            print(f"  Collection {collection} doesn't exist yet")
    except Exception as e:
        print(f"  Qdrant check failed: {e}")
    
    # Determine what to process
    to_process = []
    to_reindex = []
    skipped = []
    
    for pdf_key in pdf_keys:
        pdf_name = Path(pdf_key).stem
        doc_id = pdf_name
        
        has_r2_output = doc_id in existing_outputs
        has_qdrant = doc_id in qdrant_indexed
        
        if not force_reprocess:
            if has_r2_output and has_qdrant:
                skipped.append(pdf_key)
                print(f"  ✓ Skipping (R2 + Qdrant OK): {pdf_name}")
                continue
            elif has_r2_output and not has_qdrant:
                if max_documents > 0 and (len(to_process) + len(to_reindex)) >= max_documents:
                    skipped.append(pdf_key)
                    continue
                to_reindex.append(pdf_key)
                print(f"  ⚠ Re-indexing: {pdf_name}")
                continue
        
        if max_documents > 0 and (len(to_process) + len(to_reindex)) >= max_documents:
            skipped.append(pdf_key)
            continue
        
        print(f"  Queuing: {pdf_name}")
        to_process.append(pdf_key)
    
    all_to_process = to_process + to_reindex
    
    if not all_to_process:
        return {
            "project_id": project_id,
            "qdrant_collection": collection,
            "processed": 0,
            "skipped": len(skipped),
            "total": len(pdf_keys),
            "results": [],
        }
    
    print(f"\nProcessing {len(all_to_process)} PDFs...")
    
    # Create processing job
    job_id = None
    try:
        job_result = supabase.table("processing_jobs").insert({
            "rag_project_id": project_id,
            "job_type": "ingest",
            "status": "running",
            "progress": 0,
            "message": f"Processing 0/{len(all_to_process)} documents",
            "started_at": datetime.now().isoformat(),
        }).execute()
        if job_result.data:
            job_id = job_result.data[0]["id"]
            print(f"  Created job: {job_id}")
    except Exception as e:
        print(f"  ⚠ Failed to create job: {e}")
    
    def update_job_progress(completed: int, total: int, status: str = "running", error: str = None):
        if not job_id:
            return
        try:
            progress = int((completed / total) * 100) if total > 0 else 0
            update_data = {
                "progress": progress,
                "message": f"Processed {completed}/{total} documents",
                "status": status,
            }
            if status == "completed":
                update_data["completed_at"] = datetime.now().isoformat()
            if error:
                update_data["error_message"] = error
            supabase.table("processing_jobs").update(update_data).eq("id", job_id).execute()
        except Exception:
            pass
    
    # Process with starmap
    results = []
    success = 0
    failed = 0
    processed_count = 0
    
    for result in process_pdf_rag.starmap(
        [(pdf_key, project_id, collection) for pdf_key in all_to_process],
        return_exceptions=True,
    ):
        processed_count += 1
        if isinstance(result, Exception):
            print(f"  ✗ Error: {result}")
            failed += 1
            results.append({"error": str(result)})
        else:
            print(f"  ✓ Completed: {result.get('pdf_name', result.get('doc_id', 'unknown'))}")
            success += 1
            results.append(result)
        
        update_job_progress(processed_count, len(all_to_process))
    
    final_status = "completed"
    error_msg = f"{failed} documents failed" if failed > 0 else None
    update_job_progress(processed_count, len(all_to_process), status=final_status, error=error_msg)
    
    print(f"\nComplete: {success} succeeded, {failed} failed")
    
    return {
        "project_id": project_id,
        "qdrant_collection": collection,
        "job_id": job_id,
        "processed": success,
        "failed": failed,
        "skipped": len(skipped),
        "total": len(pdf_keys),
        "results": results[:10],
    }


# ============================================================================
# Status Functions
# ============================================================================

@app.function(
    image=base_image,
    secrets=[r2_secret],
    timeout=60,
)
def list_pdfs() -> dict:
    """List PDFs in R2 and their processing status."""
    s3 = get_r2_client()
    bucket = get_bucket_name()
    
    # Count input PDFs
    input_count = 0
    continuation_token = None
    while True:
        if continuation_token:
            response = s3.list_objects_v2(Bucket=bucket, Prefix="input-pdfs/", ContinuationToken=continuation_token)
        else:
            response = s3.list_objects_v2(Bucket=bucket, Prefix="input-pdfs/")
        
        if "Contents" in response:
            input_count += sum(1 for obj in response["Contents"] if obj["Key"].lower().endswith(".pdf"))
        
        if response.get("IsTruncated"):
            continuation_token = response.get("NextContinuationToken")
        else:
            break
    
    # Count processed
    output_count = 0
    continuation_token = None
    while True:
        if continuation_token:
            response = s3.list_objects_v2(Bucket=bucket, Prefix="outputs/json/", ContinuationToken=continuation_token)
        else:
            response = s3.list_objects_v2(Bucket=bucket, Prefix="outputs/json/")
        
        if "Contents" in response:
            output_count += len(response["Contents"])
        
        if response.get("IsTruncated"):
            continuation_token = response.get("NextContinuationToken")
        else:
            break
    
    return {
        "total_input": input_count,
        "processed": output_count,
        "pending": max(0, input_count - output_count),
    }


@app.function(
    image=base_image,
    secrets=[qdrant_secret],
    timeout=30,
)
def check_qdrant_status() -> dict:
    """Check Qdrant connection and collection status."""
    from qdrant_client import QdrantClient
    
    qdrant = QdrantClient(
        url=os.environ["QDRANT_URL"],
        api_key=os.environ["QDRANT_API_KEY"],
    )
    
    try:
        info = qdrant.get_collection(QDRANT_COLLECTION_NAME)
        return {
            "status": "connected",
            "points_count": info.points_count,
            "vectors_count": info.vectors_count,
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}
