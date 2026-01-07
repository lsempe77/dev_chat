"""
Processing functions for individual PDF documents.

Contains:
- process_pdf: Main GPU function for processing global input-pdfs
- process_pdf_rag: GPU function for processing project-specific PDFs
- sync_to_supabase_rag: Sync metadata to Supabase for RAG projects
- check_qdrant_indexed: Check if document is already indexed
- delete_qdrant_chunks: Remove existing chunks for reprocessing
- ensure_qdrant_indexes: Create payload indexes for fast lookups
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

from .config import (
    app,
    base_image,
    r2_secret,
    qdrant_secret,
    cohere_secret,
    supabase_secret,
    openrouter_secret,
    model_cache,
    QDRANT_COLLECTION_NAME,
)
from .utils import get_r2_client, get_bucket_name, sanitize_text, sanitize_dict
from .extraction import run_mineru, post_process_content
from .metadata import resolve_metadata, classify_study_design_llm
from .embedding import embed_and_index


# ============================================================================
# Qdrant Helper Functions
# ============================================================================

def check_qdrant_indexed(doc_id: str) -> Tuple[bool, int, Optional[str]]:
    """
    Check if a document is already indexed in Qdrant.
    
    Returns:
        tuple: (is_indexed: bool, chunk_count: int, error: Optional[str])
    """
    try:
        from qdrant_client import QdrantClient
        
        qdrant = QdrantClient(
            url=os.environ["QDRANT_URL"],
            api_key=os.environ["QDRANT_API_KEY"],
        )
        
        # Search for chunks with this doc_id
        results = qdrant.scroll(
            collection_name=QDRANT_COLLECTION_NAME,
            scroll_filter={
                "must": [{"key": "doc_id", "match": {"value": doc_id}}]
            },
            limit=1,
            with_payload=False,
        )
        
        points, _ = results
        if points:
            # Count total chunks
            count_result = qdrant.count(
                collection_name=QDRANT_COLLECTION_NAME,
                count_filter={
                    "must": [{"key": "doc_id", "match": {"value": doc_id}}]
                },
            )
            return True, count_result.count, None
        
        return False, 0, None
        
    except Exception as e:
        return False, 0, str(e)


def delete_qdrant_chunks(doc_id: str) -> int:
    """
    Delete all chunks for a document from Qdrant.
    
    Returns:
        int: Number of chunks deleted
    """
    try:
        from qdrant_client import QdrantClient
        from qdrant_client.http.models import FilterSelector, Filter, FieldCondition, MatchValue
        
        qdrant = QdrantClient(
            url=os.environ["QDRANT_URL"],
            api_key=os.environ["QDRANT_API_KEY"],
        )
        
        # Count before delete
        count_before = qdrant.count(
            collection_name=QDRANT_COLLECTION_NAME,
            count_filter=Filter(
                must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))]
            ),
        )
        
        # Delete by filter
        qdrant.delete(
            collection_name=QDRANT_COLLECTION_NAME,
            points_selector=FilterSelector(
                filter=Filter(
                    must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))]
                )
            ),
        )
        
        print(f"  Deleted {count_before.count} existing chunks for {doc_id}")
        return count_before.count
        
    except Exception as e:
        print(f"  Warning: Failed to delete chunks for {doc_id}: {e}")
        return 0


def ensure_qdrant_indexes() -> bool:
    """
    Ensure payload indexes exist for fast lookups.
    
    Creates indexes on:
    - doc_id: For document-level operations
    - source: For legacy compatibility
    """
    try:
        from qdrant_client import QdrantClient
        from qdrant_client.http.models import PayloadSchemaType
        
        qdrant = QdrantClient(
            url=os.environ["QDRANT_URL"],
            api_key=os.environ["QDRANT_API_KEY"],
        )
        
        # Create indexes (idempotent)
        for field in ["doc_id", "source"]:
            try:
                qdrant.create_payload_index(
                    collection_name=QDRANT_COLLECTION_NAME,
                    field_name=field,
                    field_schema=PayloadSchemaType.KEYWORD,
                )
            except Exception:
                pass  # Index already exists
        
        return True
        
    except Exception as e:
        print(f"  Warning: Failed to create indexes: {e}")
        return False


def sync_to_postgres(
    doc_id: str,
    metadata: dict,
    chunk_count: int,
    page_count: int,
) -> bool:
    """
    Sync document metadata to Railway PostgreSQL backend.
    
    This enables instant admin queries without hitting Qdrant.
    """
    import httpx
    
    backend_url = os.environ.get("BACKEND_URL", "https://3iechat.up.railway.app")
    
    payload = {
        "doc_id": doc_id,
        "title": metadata.get("title"),
        "authors": metadata.get("authors"),
        "year": metadata.get("year"),
        "doi": metadata.get("doi"),
        "journal": metadata.get("journal"),
        "abstract": metadata.get("abstract"),
        "cited_by_count": metadata.get("cited_by_count"),
        "is_open_access": metadata.get("is_open_access"),
        "countries": metadata.get("countries", []),
        "sectors": metadata.get("sectors", []),
        "study_type": metadata.get("study_type"),
        "study_design": metadata.get("study_design"),
        "study_design_confidence": metadata.get("study_design_confidence"),
        "intervention_type": metadata.get("intervention_type"),
        "sdgs": metadata.get("sdgs", []),
        "keywords": metadata.get("keywords", []),
        "metadata_source": metadata.get("metadata_source"),
        "metadata_confidence": metadata.get("metadata_confidence"),
        "needs_review": metadata.get("needs_review"),
        "chunk_count": chunk_count,
        "page_count": page_count,
        "processed_at": datetime.now().isoformat(),
    }
    
    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.post(
                f"{backend_url}/admin/documents/sync",
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            
            if response.status_code in (200, 201):
                print(f"  ✓ Synced to PostgreSQL: {doc_id}")
                return True
            else:
                print(f"  ⚠ PostgreSQL sync returned {response.status_code}: {response.text[:200]}")
                return False
                
    except Exception as e:
        print(f"  ⚠ PostgreSQL sync failed: {e}")
        return False


def sync_to_supabase_rag(
    doc_id: str,
    project_id: str,
    metadata: dict,
    chunk_count: int,
    page_count: int,
) -> bool:
    """
    Sync processed document to Supabase for a RAG project.
    
    Updates the documents table directly via Supabase client.
    """
    from supabase import create_client
    
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_SERVICE_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    
    if not supabase_url or not supabase_key:
        print("  ⚠ Supabase credentials not configured")
        return False
    
    try:
        client = create_client(supabase_url, supabase_key)
        
        # Find document by filename field
        result = client.table("documents").select("id, filename").eq("rag_project_id", project_id).execute()
        
        matching_doc = None
        for doc in result.data or []:
            if doc.get("filename") == doc_id:
                matching_doc = doc
                break
        
        if not matching_doc:
            print(f"  ⚠ Document not found in Supabase: {doc_id}")
            return False
        
        # Get existing metadata to preserve user edits
        existing_result = client.table("documents").select("metadata").eq("id", matching_doc["id"]).execute()
        existing_metadata = {}
        if existing_result.data and existing_result.data[0].get("metadata"):
            existing_metadata = existing_result.data[0]["metadata"]
        
        # Preserve reviewed status
        was_reviewed = existing_metadata.get("needs_review") is False
        
        merged_metadata = {**metadata}
        if was_reviewed:
            merged_metadata["needs_review"] = False
        
        # Update the document
        update_data = {
            "status": "completed",
            "chunk_count": chunk_count,
            "processed_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "metadata": {
                **merged_metadata,
                "doc_id": doc_id,
                "chunk_count": chunk_count,
                "page_count": page_count,
            },
        }
        
        client.table("documents").update(update_data).eq("id", matching_doc["id"]).execute()
        print(f"  ✓ Synced to Supabase: {matching_doc['id']}")
        return True
        
    except Exception as e:
        print(f"  ⚠ Supabase sync error: {e}")
        return False


# ============================================================================
# PDF Processing Functions (GPU)
# ============================================================================

@app.function(
    image=base_image,
    gpu="T4",
    timeout=1800,
    secrets=[r2_secret, qdrant_secret, cohere_secret, openrouter_secret],
    volumes={"/cache": model_cache},
    retries=0,
)
def process_pdf(pdf_key: str, skip_extraction: bool = False, force_reindex: bool = False) -> dict:
    """
    Process a single PDF from R2 (global input-pdfs folder).
    
    Args:
        pdf_key: R2 key for the PDF (e.g., "input-pdfs/paper.pdf")
        skip_extraction: Skip MinerU, use existing R2 JSON output
        force_reindex: Delete existing Qdrant chunks before indexing
        
    Returns:
        dict with processing results
    """
    import tempfile
    import asyncio
    
    os.environ["HF_HOME"] = "/cache/huggingface"
    os.environ["TRANSFORMERS_CACHE"] = "/cache/huggingface"
    
    print(f"Processing: {pdf_key} (skip_extraction={skip_extraction})")
    start_time = datetime.now()
    
    s3 = get_r2_client()
    bucket = get_bucket_name()
    
    doc_id = Path(pdf_key).stem
    json_key = f"outputs/json/{doc_id}.json"
    md_key = None
    lock_key = f"locks/{doc_id}.lock"
    
    # Check for processing lock
    try:
        s3.head_object(Bucket=bucket, Key=lock_key)
        print(f"  ⏸ Lock exists - already being processed, skipping")
        return {"success": True, "pdf_key": pdf_key, "doc_id": doc_id, "skipped": True, "reason": "locked"}
    except Exception:
        try:
            s3.put_object(Bucket=bucket, Key=lock_key, Body=f"Processing started at {start_time.isoformat()}".encode())
        except Exception as e:
            print(f"  Warning: Could not create lock: {e}")

    try:
        ensure_qdrant_indexes()

        # Check if already indexed
        if not force_reindex:
            is_indexed, existing_chunks, qdrant_err = check_qdrant_indexed(doc_id)
            if qdrant_err:
                print(f"  Warning: Qdrant check failed: {qdrant_err}")
            elif is_indexed and not skip_extraction:
                print(f"  ✓ Already indexed ({existing_chunks} chunks), skipping")
                return {"success": True, "pdf_key": pdf_key, "doc_id": doc_id, "skipped": True, "reason": "already_indexed"}
        
        if force_reindex:
            delete_qdrant_chunks(doc_id)
        
        # Mode 1: Use existing R2 output
        if skip_extraction:
            try:
                response = s3.get_object(Bucket=bucket, Key=json_key)
                output_data = json.loads(response["Body"].read().decode("utf-8"))
                result = {
                    "success": True,
                    "content": output_data.get("content", ""),
                    "tables": output_data.get("tables", []),
                    "formulas": output_data.get("formulas", []),
                    "title": output_data.get("title"),
                    "authors": output_data.get("authors", []),
                    "year": output_data.get("year"),
                    "page_count": output_data.get("page_count", 0),
                }
                print(f"  Loaded existing JSON: {len(result['content'])} chars")
            except Exception as e:
                print(f"  Failed to load existing JSON: {e}")
                skip_extraction = False
        
        # Mode 2: Full extraction with MinerU
        if not skip_extraction:
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                s3.download_file(bucket, pdf_key, tmp.name)
                pdf_path = Path(tmp.name)
            
            print(f"  Downloaded: {pdf_path} ({pdf_path.stat().st_size / 1024:.1f} KB)")
            
            result = run_mineru(pdf_path)
            
            if not result["success"]:
                raise Exception(result.get("error", "MinerU processing failed"))
            
            print(f"  Extracted: {len(result['content'])} chars, {len(result['tables'])} tables")
            
            # Sanitize content
            result["content"] = sanitize_text(result["content"])
            result["tables"] = sanitize_dict(result["tables"])
            result["formulas"] = sanitize_dict(result["formulas"])
            if result.get("title"):
                result["title"] = sanitize_text(result["title"])
            if result.get("abstract"):
                result["abstract"] = sanitize_text(result["abstract"])
            
            result["content"] = post_process_content(
                content=result["content"],
                title=result.get("title"),
                authors=result.get("authors"),
                year=result.get("year"),
                pdf_name=Path(pdf_key).name,
            )
            
            # Upload outputs to R2
            md_key = f"outputs/md/{doc_id}.md"
            s3.put_object(Bucket=bucket, Key=md_key, Body=result["content"].encode("utf-8"), ContentType="text/markdown")
            
            output_data = {
                "doc_id": doc_id,
                "source_key": pdf_key,
                "processed_at": datetime.now().isoformat(),
                "title": result.get("title"),
                "authors": result.get("authors"),
                "year": result.get("year"),
                "abstract": result.get("abstract"),
                "content": result["content"],
                "tables": result["tables"],
                "formulas": result["formulas"],
                "page_count": result.get("page_count", 0),
            }
            s3.put_object(Bucket=bucket, Key=json_key, Body=json.dumps(output_data, indent=2, ensure_ascii=False).encode("utf-8"), ContentType="application/json")
            
            print(f"  Uploaded: {md_key}, {json_key}")
        
        # Metadata resolution
        print(f"  Resolving metadata...")
        enriched_metadata = resolve_metadata(
            content=result["content"],
            title=result.get("title"),
            authors=result.get("authors", []),
            year=result.get("year"),
            pdf_filename=Path(pdf_key).name,
        )
        enriched_metadata["doc_id"] = doc_id
        enriched_metadata["source"] = pdf_key
        
        print(f"  Metadata: source={enriched_metadata['metadata_source']}, confidence={enriched_metadata['metadata_confidence']:.2f}")
        
        # Study design classification
        print(f"  Classifying study design...")
        openrouter_key = os.environ.get("OPENROUTER_API_KEY")
        if openrouter_key:
            abstract_text = enriched_metadata.get("abstract") or result.get("abstract") or ""
            if not abstract_text and result.get("content"):
                abstract_text = result["content"][:8000]
            
            study_design_result = asyncio.run(
                classify_study_design_llm(
                    title=enriched_metadata.get("title") or result.get("title") or "",
                    abstract_or_content=abstract_text,
                    api_key=openrouter_key,
                )
            )
            enriched_metadata["study_design"] = study_design_result.get("study_design", "unknown")
            enriched_metadata["study_design_confidence"] = study_design_result.get("study_design_confidence", 0.0)
            enriched_metadata["study_design_reasoning"] = study_design_result.get("study_design_reasoning", "")
            print(f"  Study design: {enriched_metadata['study_design']} (conf: {enriched_metadata['study_design_confidence']:.2f})")
        else:
            enriched_metadata["study_design"] = "unknown"
            enriched_metadata["study_design_confidence"] = 0.0
        
        # Embed and index
        chunk_count = embed_and_index(
            content=result["content"],
            metadata=enriched_metadata,
            doc_id=doc_id,
            content_list=result.get("content_list"),
        )
        
        print(f"  Indexed: {chunk_count} chunks to Qdrant")
        
        # Sync to PostgreSQL
        sync_to_postgres(doc_id, enriched_metadata, chunk_count, result.get("page_count", 0))
        
        # Cleanup
        if not skip_extraction and 'pdf_path' in dir():
            pdf_path.unlink(missing_ok=True)
        
        try:
            s3.delete_object(Bucket=bucket, Key=lock_key)
        except Exception:
            pass
        
        elapsed = (datetime.now() - start_time).total_seconds()
        
        return {
            "success": True,
            "doc_id": doc_id,
            "pdf_key": pdf_key,
            "chunks_indexed": chunk_count,
            "elapsed_seconds": elapsed,
            "pages": result.get("page_count", 0),
        }
        
    except Exception as e:
        try:
            s3.delete_object(Bucket=bucket, Key=lock_key)
        except Exception:
            pass
        print(f"  ERROR: {e}")
        return {"success": False, "pdf_key": pdf_key, "error": str(e)}


@app.function(
    image=base_image,
    secrets=[r2_secret, qdrant_secret, cohere_secret, supabase_secret, openrouter_secret],
    volumes={"/cache": model_cache},
    gpu="T4",
    timeout=1800,
    retries=2,
)
def process_pdf_rag(pdf_key: str, project_id: str, qdrant_collection: str) -> dict:
    """
    Process a single PDF for a RAG project.
    
    Similar to process_pdf but uses project-specific paths and collection.
    
    Args:
        pdf_key: Full R2 key (e.g., rags/{project_id}/input-pdfs/paper.pdf)
        project_id: RAG project UUID for Supabase sync
        qdrant_collection: Qdrant collection name
    """
    import tempfile
    import httpx
    import asyncio
    
    s3 = get_r2_client()
    bucket = get_bucket_name()
    
    pdf_name = Path(pdf_key).stem
    doc_id = pdf_name
    
    print(f"\n{'='*60}")
    print(f"Processing: {pdf_name} for project {project_id}")
    print(f"{'='*60}")
    
    try:
        # Download PDF
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_pdf:
            s3.download_file(bucket, pdf_key, tmp_pdf.name)
            pdf_path = Path(tmp_pdf.name)
        
        print(f"  Downloaded: {pdf_path}")
        
        # Process with MinerU
        result = run_mineru(pdf_path)
        
        if not result.get("success"):
            raise Exception(result.get("error", "MinerU processing failed"))
        
        print(f"  MinerU: {result.get('page_count', 0)} pages, {len(result.get('content', ''))} chars")
        
        # Post-process content
        result["content"] = post_process_content(
            content=result["content"],
            title=result.get("title"),
            authors=result.get("authors"),
            year=result.get("year"),
            pdf_name=Path(pdf_key).name,
        )
        
        result["content"] = sanitize_text(result["content"])
        
        # Upload outputs to project folder
        output_prefix = f"rags/{project_id}/outputs"
        
        md_key = f"{output_prefix}/md/{doc_id}.md"
        s3.put_object(Bucket=bucket, Key=md_key, Body=result["content"].encode("utf-8"), ContentType="text/markdown")
        
        json_key = f"{output_prefix}/json/{doc_id}.json"
        output_data = {
            "doc_id": doc_id,
            "project_id": project_id,
            "source_key": pdf_key,
            "processed_at": datetime.now().isoformat(),
            "title": result.get("title"),
            "authors": result.get("authors"),
            "year": result.get("year"),
            "abstract": result.get("abstract"),
            "content": result["content"],
            "page_count": result.get("page_count", 0),
        }
        output_data = sanitize_dict(output_data)
        s3.put_object(Bucket=bucket, Key=json_key, Body=json.dumps(output_data, indent=2, ensure_ascii=False).encode("utf-8"), ContentType="application/json")
        
        print(f"  Uploaded: {md_key}")
        
        # Resolve metadata
        print(f"  Resolving metadata...")
        enriched_metadata = resolve_metadata(
            content=result["content"],
            title=result.get("title"),
            authors=result.get("authors"),
            year=result.get("year"),
            pdf_filename=Path(pdf_key).name,
        )
        enriched_metadata["doc_id"] = doc_id
        enriched_metadata["source"] = pdf_key
        
        print(f"  Metadata: source={enriched_metadata.get('metadata_source')}, confidence={enriched_metadata.get('metadata_confidence', 0):.2f}")
        
        # Study design classification
        print(f"  Classifying study design...")
        openrouter_key = os.environ.get("OPENROUTER_API_KEY")
        if openrouter_key:
            abstract_text = enriched_metadata.get("abstract") or result.get("abstract") or ""
            if not abstract_text and result.get("content"):
                abstract_text = result["content"][:8000]
            
            study_design_result = asyncio.run(
                classify_study_design_llm(
                    title=enriched_metadata.get("title") or result.get("title") or "",
                    abstract_or_content=abstract_text,
                    api_key=openrouter_key,
                )
            )
            enriched_metadata["study_design"] = study_design_result.get("study_design", "unknown")
            enriched_metadata["study_design_confidence"] = study_design_result.get("study_design_confidence", 0.0)
            enriched_metadata["study_design_reasoning"] = study_design_result.get("study_design_reasoning", "")
            print(f"  Study design: {enriched_metadata['study_design']} (conf: {enriched_metadata['study_design_confidence']:.2f})")
        else:
            enriched_metadata["study_design"] = "unknown"
            enriched_metadata["study_design_confidence"] = 0.0
        
        # Embed to project-specific collection
        print(f"  Chunking and embedding to {qdrant_collection}...")
        chunk_count = embed_and_index(
            content=result["content"],
            metadata=enriched_metadata,
            doc_id=doc_id,
            content_list=result.get("content_list"),
            collection_name=qdrant_collection,
        )
        
        print(f"  Indexed {chunk_count} chunks to {qdrant_collection}")
        
        if chunk_count == 0:
            raise Exception("No chunks indexed. Content may be empty or too short.")
        
        # Sync to Supabase
        sync_to_supabase_rag(
            doc_id=doc_id,
            project_id=project_id,
            metadata=enriched_metadata,
            chunk_count=chunk_count,
            page_count=result.get("page_count", 0),
        )
        
        # Cleanup
        pdf_path.unlink(missing_ok=True)
        
        return {
            "success": True,
            "doc_id": doc_id,
            "project_id": project_id,
            "chunks": chunk_count,
            "pages": result.get("page_count", 0),
            "metadata_source": enriched_metadata.get("metadata_source"),
        }
        
    except Exception as e:
        print(f"  ❌ Error: {e}")
        try:
            backend_url = os.environ.get("BACKEND_URL", "https://3iechat.up.railway.app")
            with httpx.Client(timeout=10.0) as client:
                client.patch(f"{backend_url}/rags/{project_id}/documents/{doc_id}/status", json={"status": "failed", "error": str(e)})
        except:
            pass
        
        return {"success": False, "doc_id": doc_id, "project_id": project_id, "error": str(e)}
