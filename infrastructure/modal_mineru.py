"""
MinerU PDF Processing on Modal with Cloudflare R2 Storage

Architecture:
    Cloudflare R2 (/input-pdfs/) → Modal (GPU) → R2 (/outputs/) + Qdrant Cloud

Setup:
    1. pip install modal
    2. modal token new
    3. Create Modal secrets: r2-credentials, qdrant-credentials, cohere-credentials
    4. modal deploy infrastructure/modal_mineru.py

Usage:
    # Process all new PDFs in R2 bucket
    modal run infrastructure/modal_mineru.py::orchestrate
    
    # Process single PDF
    modal run infrastructure/modal_mineru.py::process_single --pdf-key "input-pdfs/paper.pdf"
    
    # Schedule hourly processing
    # (Configured via Modal dashboard or modal.Schedule)

Environment Variables (Modal Secrets):
    R2:
        - R2_ACCOUNT_ID
        - R2_ACCESS_KEY_ID  
        - R2_SECRET_ACCESS_KEY
        - R2_BUCKET_NAME
    
    Qdrant:
        - QDRANT_URL
        - QDRANT_API_KEY
    
    Cohere:
        - COHERE_API_KEY
"""

import modal
import json
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Optional

# ============================================================================
# Modal App Configuration
# ============================================================================

app = modal.App("devchat-mineru")

# Base image with system dependencies
base_image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install(
        "libgl1-mesa-glx",
        "libglib2.0-0", 
        "libsm6",
        "libxext6",
        "libxrender-dev",
    )
    .pip_install(
        "mineru[core]>=2.6.0",
        "boto3",
        "cohere>=5.0.0",
        "qdrant-client>=1.7.0",
        "httpx",
    )
)

# Volume for caching HuggingFace models (persists across runs)
model_cache = modal.Volume.from_name("mineru-model-cache", create_if_missing=True)

# Secrets
r2_secret = modal.Secret.from_name("r2-credentials")
qdrant_secret = modal.Secret.from_name("qdrant-credentials")
cohere_secret = modal.Secret.from_name("cohere-credentials")


# ============================================================================
# R2 Client Helper
# ============================================================================

def get_r2_client():
    """Create S3 client configured for Cloudflare R2."""
    import boto3
    import os
    
    return boto3.client(
        "s3",
        endpoint_url=f"https://{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )


def get_bucket_name():
    import os
    return os.environ.get("R2_BUCKET_NAME", "devchat-pdfs")


def compute_content_hash(content: bytes) -> str:
    """Compute MD5 hash of content for change detection."""
    return hashlib.md5(content).hexdigest()[:16]


def check_qdrant_indexed(pdf_name: str) -> tuple[bool, int]:
    """
    Check if a PDF is already indexed in Qdrant.
    
    Returns:
        (is_indexed, chunk_count)
    """
    import os
    from qdrant_client import QdrantClient
    from qdrant_client.models import Filter, FieldCondition, MatchValue
    
    try:
        qdrant = QdrantClient(
            url=os.environ["QDRANT_URL"],
            api_key=os.environ["QDRANT_API_KEY"],
        )
        
        # First check if collection exists
        try:
            qdrant.get_collection("devchat_v2")
        except Exception:
            return False, 0
        
        # Try to count with filter - this requires payload index
        try:
            result = qdrant.count(
                collection_name="devchat_v2",
                count_filter=Filter(
                    must=[FieldCondition(key="pdf_name", match=MatchValue(value=pdf_name))]
                ),
            )
            return result.count > 0, result.count
        except Exception as filter_error:
            # If filter fails (no index), fall back to scroll search
            if "index required" in str(filter_error).lower():
                print(f"  Note: No index on pdf_name, using scroll fallback")
                # Scroll through all points to check (slower but works)
                results, _ = qdrant.scroll(
                    collection_name="devchat_v2",
                    scroll_filter=None,
                    limit=100,
                    with_payload=["pdf_name"],
                )
                count = sum(1 for r in results if r.payload.get("pdf_name") == pdf_name)
                return count > 0, count
            raise
            
    except Exception as e:
        print(f"  Qdrant check failed: {e}")
        return False, 0


def delete_qdrant_chunks(pdf_name: str) -> int:
    """
    Delete all chunks for a PDF from Qdrant (for re-indexing).
    
    Returns:
        Number of points deleted
    """
    import os
    from qdrant_client import QdrantClient
    from qdrant_client.models import Filter, FieldCondition, MatchValue
    
    try:
        qdrant = QdrantClient(
            url=os.environ["QDRANT_URL"],
            api_key=os.environ["QDRANT_API_KEY"],
        )
        
        # Get count before delete
        count_before = qdrant.count(
            collection_name="devchat_v2",
            count_filter=Filter(
                must=[FieldCondition(key="pdf_name", match=MatchValue(value=pdf_name))]
            ),
        ).count
        
        if count_before > 0:
            qdrant.delete(
                collection_name="devchat_v2",
                points_selector=Filter(
                    must=[FieldCondition(key="pdf_name", match=MatchValue(value=pdf_name))]
                ),
            )
            print(f"  Deleted {count_before} old chunks from Qdrant")
        
        return count_before
    except Exception as e:
        print(f"  Qdrant delete failed: {e}")
        return 0


# ============================================================================
# Orchestrator (CPU) - Lists PDFs and spawns GPU workers
# ============================================================================

@app.function(
    image=base_image,
    secrets=[r2_secret, qdrant_secret],
    timeout=300,
)
def orchestrate(force_reprocess: bool = False, check_qdrant: bool = True) -> dict:
    """
    Scan R2 for new PDFs and queue them for processing.
    
    Smart deduplication:
    1. Checks if JSON output exists in R2 (fast)
    2. Optionally checks if chunks exist in Qdrant (thorough)
    3. Can force reprocess with force_reprocess=True
    
    Args:
        force_reprocess: If True, reprocess all PDFs even if outputs exist
        check_qdrant: If True, also verify Qdrant indexing (slower but thorough)
        
    Returns:
        dict with counts of queued, skipped, and failed PDFs
    """
    import boto3
    
    s3 = get_r2_client()
    bucket = get_bucket_name()
    
    # List input PDFs
    input_prefix = "input-pdfs/"
    response = s3.list_objects_v2(Bucket=bucket, Prefix=input_prefix)
    
    if "Contents" not in response:
        return {"message": "No PDFs found in input-pdfs/", "queued": 0}
    
    pdf_keys = [
        obj["Key"] for obj in response["Contents"]
        if obj["Key"].lower().endswith(".pdf")
    ]
    
    print(f"Found {len(pdf_keys)} PDFs in R2")
    
    # Check which ones already have outputs in R2
    output_prefix = "outputs/json/"
    existing_response = s3.list_objects_v2(Bucket=bucket, Prefix=output_prefix)
    existing_outputs = set()
    
    if "Contents" in existing_response:
        existing_outputs = {
            Path(obj["Key"]).stem for obj in existing_response["Contents"]
        }
    
    print(f"Found {len(existing_outputs)} existing JSON outputs in R2")
    
    # Queue new PDFs for processing
    queued = []
    skipped_r2 = []
    skipped_qdrant = []
    needs_reindex = []
    
    for pdf_key in pdf_keys:
        pdf_name = Path(pdf_key).stem
        
        # Check 1: R2 output exists?
        has_r2_output = pdf_name in existing_outputs
        
        if has_r2_output and not force_reprocess:
            # Check 2: Qdrant indexed? (optional but recommended)
            if check_qdrant:
                is_indexed, chunk_count = check_qdrant_indexed(pdf_name)
                if is_indexed:
                    skipped_qdrant.append({"key": pdf_key, "chunks": chunk_count})
                    print(f"  ✓ Skipping (R2 + Qdrant OK, {chunk_count} chunks): {pdf_key}")
                    continue
                else:
                    # R2 has output but Qdrant missing - needs re-indexing only
                    needs_reindex.append(pdf_key)
                    print(f"  ⚠ Re-indexing (R2 OK, Qdrant missing): {pdf_key}")
                    process_pdf.spawn(pdf_key=pdf_key, skip_extraction=True)
                    continue
            else:
                skipped_r2.append(pdf_key)
                print(f"  Skipping (R2 output exists): {pdf_key}")
                continue
        
        # Queue for full processing
        print(f"  Queuing: {pdf_key}")
        process_pdf.spawn(pdf_key=pdf_key, skip_extraction=False)
        queued.append(pdf_key)
    
    return {
        "queued": len(queued),
        "skipped_r2_only": len(skipped_r2),
        "skipped_fully_indexed": len(skipped_qdrant),
        "needs_reindex": len(needs_reindex),
        "total": len(pdf_keys),
        "queued_files": queued[:10],
        "reindex_files": needs_reindex[:10],
    }


# ============================================================================
# PDF Processor (GPU) - Runs MinerU extraction
# ============================================================================

@app.function(
    image=base_image,
    gpu="T4",  # or "A10G" for faster processing
    timeout=1800,  # 30 min max per PDF
    secrets=[r2_secret, qdrant_secret, cohere_secret],
    volumes={"/cache": model_cache},
    retries=2,
)
def process_pdf(pdf_key: str, skip_extraction: bool = False, force_reindex: bool = False) -> dict:
    """
    Process a single PDF from R2.
    
    Smart processing:
    1. If skip_extraction=True, loads existing JSON from R2 and only re-indexes
    2. If force_reindex=True, deletes existing Qdrant chunks first
    3. Computes content hash for change detection
    
    Args:
        pdf_key: R2 key for the PDF (e.g., "input-pdfs/paper.pdf")
        skip_extraction: Skip MinerU, use existing R2 JSON output
        force_reindex: Delete existing Qdrant chunks before indexing
        
    Returns:
        dict with processing results
    """
    import os
    import tempfile
    
    # Set HuggingFace cache to persistent volume
    os.environ["HF_HOME"] = "/cache/huggingface"
    os.environ["TRANSFORMERS_CACHE"] = "/cache/huggingface"
    
    print(f"Processing: {pdf_key} (skip_extraction={skip_extraction})")
    start_time = datetime.now()
    
    s3 = get_r2_client()
    bucket = get_bucket_name()
    
    # Extract doc_id from the R2 key
    # R2 key format: input-pdfs/{doc_id}.pdf where doc_id = {8-char-uuid}_{sanitized_name}
    # This doc_id is the universal identifier across R2, Qdrant, and admin systems
    doc_id = Path(pdf_key).stem  # e.g., "a1b2c3d4_impact_evaluation_kenya"
    
    try:
        # Check if already indexed in Qdrant (unless forcing)
        if not force_reindex:
            is_indexed, existing_chunks = check_qdrant_indexed(doc_id)
            if is_indexed and not skip_extraction:
                print(f"  ✓ Already indexed ({existing_chunks} chunks), skipping")
                return {
                    "success": True,
                    "pdf_key": pdf_key,
                    "doc_id": doc_id,
                    "skipped": True,
                    "reason": "already_indexed",
                    "existing_chunks": existing_chunks,
                }
        
        # If re-indexing, delete old chunks first
        if force_reindex:
            delete_qdrant_chunks(doc_id)
        
        # Mode 1: Skip extraction, use existing R2 output
        if skip_extraction:
            json_key = f"outputs/json/{doc_id}.json"
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
                print(f"  Failed to load existing JSON, falling back to full extraction: {e}")
                skip_extraction = False
        
        # Mode 2: Full extraction with MinerU
        if not skip_extraction:
            # Download PDF to temp file
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                s3.download_file(bucket, pdf_key, tmp.name)
                pdf_path = Path(tmp.name)
            
            print(f"  Downloaded: {pdf_path} ({pdf_path.stat().st_size / 1024:.1f} KB)")
            
            # Process with MinerU
            result = run_mineru(pdf_path)
            
            if not result["success"]:
                raise Exception(result.get("error", "MinerU processing failed"))
            
            print(f"  Extracted: {len(result['content'])} chars, {len(result['tables'])} tables")
            
            # Upload outputs to R2 (only for new extractions)
            # Use doc_id consistently for output paths
            md_key = f"outputs/md/{doc_id}.md"
            s3.put_object(
                Bucket=bucket,
                Key=md_key,
                Body=result["content"].encode("utf-8"),
                ContentType="text/markdown",
            )
            
            # Structured JSON with doc_id included
            json_key = f"outputs/json/{doc_id}.json"
            output_data = {
                "doc_id": doc_id,  # Universal document ID
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
            s3.put_object(
                Bucket=bucket,
                Key=json_key,
                Body=json.dumps(output_data, indent=2, ensure_ascii=False).encode("utf-8"),
                ContentType="application/json",
            )
            
            print(f"  Uploaded: {md_key}, {json_key}")
        
        # Generate embeddings and upsert to Qdrant
        # Pass doc_id to be stored in every chunk's payload
        chunk_count = embed_and_index(
            content=result["content"],
            metadata={
                "doc_id": doc_id,  # Universal document ID
                "source": pdf_key,
                "title": result.get("title", doc_id),
                "authors": result.get("authors", []),
                "year": result.get("year"),
            },
            doc_id=doc_id,
        )
        
        print(f"  Indexed: {chunk_count} chunks to Qdrant (doc_id={doc_id})")
        
        # Clean up (only if we downloaded a PDF)
        if not skip_extraction and 'pdf_path' in dir():
            pdf_path.unlink(missing_ok=True)
        
        elapsed = (datetime.now() - start_time).total_seconds()
        
        return {
            "success": True,
            "doc_id": doc_id,
            "pdf_key": pdf_key,
            "md_key": md_key,
            "json_key": json_key,
            "chunks_indexed": chunk_count,
            "elapsed_seconds": elapsed,
            "pages": result.get("page_count", 0),
        }
        
    except Exception as e:
        print(f"  ERROR: {e}")
        return {
            "success": False,
            "pdf_key": pdf_key,
            "error": str(e),
        }


def run_mineru(pdf_path: Path) -> dict:
    """Run MinerU extraction on a PDF file using MinerU 2.6.x API."""
    import tempfile
    import os
    import json as json_lib
    
    try:
        # MinerU 2.6.x imports
        from mineru.cli.common import prepare_env, read_fn
        from mineru.data.data_reader_writer import FileBasedDataWriter
        from mineru.backend.pipeline.pipeline_analyze import doc_analyze as pipeline_doc_analyze
        from mineru.backend.pipeline.pipeline_middle_json_mkcontent import union_make as pipeline_union_make
        from mineru.backend.pipeline.model_json_to_middle_json import result_to_middle_json as pipeline_result_to_middle_json
        from mineru.utils.enum_class import MakeMode
        
        # Read PDF bytes
        pdf_bytes = read_fn(str(pdf_path))
        pdf_file_name = pdf_path.stem
        
        # Create output directory
        output_dir = tempfile.mkdtemp(prefix="mineru_")
        
        # Run pipeline analysis
        infer_results, all_image_lists, all_pdf_docs, lang_list, ocr_enabled_list = pipeline_doc_analyze(
            [pdf_bytes],
            ["en"],  # Language
            parse_method="auto",
            formula_enable=True,
            table_enable=True,
        )
        
        if not infer_results:
            return {"success": False, "error": "No results from pipeline analysis"}
        
        # Process first (and only) PDF
        model_list = infer_results[0]
        images_list = all_image_lists[0]
        pdf_doc = all_pdf_docs[0]
        _lang = lang_list[0]
        _ocr_enable = ocr_enabled_list[0]
        
        # Prepare output directories
        local_image_dir, local_md_dir = prepare_env(output_dir, pdf_file_name, "auto")
        image_writer = FileBasedDataWriter(local_image_dir)
        
        # Convert to middle JSON
        middle_json = pipeline_result_to_middle_json(
            model_list, images_list, pdf_doc, image_writer, _lang, _ocr_enable, True
        )
        
        pdf_info = middle_json["pdf_info"]
        
        # Get page count
        page_count = len(pdf_info) if isinstance(pdf_info, list) else pdf_info.get("page_num", 0)
        
        # Generate markdown content
        image_dir = os.path.basename(local_image_dir)
        md_content = pipeline_union_make(pdf_info, MakeMode.MM_MD, image_dir)
        
        # Generate content list for structured extraction
        content_list = pipeline_union_make(pdf_info, MakeMode.CONTENT_LIST, image_dir)
        
        # Extract tables from content list
        tables = []
        if isinstance(content_list, list):
            for item in content_list:
                if isinstance(item, dict) and item.get("type") == "table":
                    tables.append({
                        "html": item.get("table_body", item.get("content", "")),
                        "caption": item.get("table_caption", ""),
                        "page": item.get("page_idx", 0),
                    })
        
        # Extract formulas from content list
        formulas = []
        if isinstance(content_list, list):
            for item in content_list:
                if isinstance(item, dict) and item.get("type") in ["equation", "formula"]:
                    formulas.append({
                        "latex": item.get("text", item.get("content", "")),
                        "page": item.get("page_idx", 0),
                    })
        
        # Clean up temp directory
        import shutil
        shutil.rmtree(output_dir, ignore_errors=True)
        
        return {
            "success": True,
            "content": md_content if isinstance(md_content, str) else str(md_content),
            "tables": tables,
            "formulas": formulas,
            "page_count": page_count,
            "title": extract_title(md_content if isinstance(md_content, str) else ""),
            "authors": [],
            "year": None,
            "abstract": extract_abstract(md_content if isinstance(md_content, str) else ""),
        }
        
    except Exception as e:
        import traceback
        error_msg = f"{e}\n{traceback.format_exc()}"
        print(f"  MinerU failed: {error_msg}")
        return {"success": False, "error": str(e)}


def extract_title(content: str) -> Optional[str]:
    """Extract title from first lines of content."""
    lines = content.strip().split("\n")
    for line in lines[:5]:
        line = line.strip().strip("#").strip()
        if len(line) > 10 and len(line) < 200:
            return line
    return None


def extract_abstract(content: str) -> Optional[str]:
    """Extract abstract if present."""
    content_lower = content.lower()
    if "abstract" in content_lower[:2000]:
        start = content_lower.find("abstract")
        # Find next section header or limit to ~500 words
        end = min(start + 3000, len(content))
        for marker in ["\n#", "\n1.", "\nintroduction", "\n1 introduction"]:
            pos = content_lower.find(marker, start + 50)
            if pos > start:
                end = min(end, pos)
        return content[start:end].strip()
    return None


# ============================================================================
# Embedding & Indexing
# ============================================================================

def embed_and_index(content: str, metadata: dict, doc_id: str) -> int:
    """
    Chunk content, generate embeddings, and upsert to Qdrant.
    
    Uses named vector 'dense' to match existing collection configuration.
    
    Args:
        content: The document content to embed
        metadata: Document metadata (title, authors, year, source, doc_id)
        doc_id: Universal document identifier (used across all systems)
    
    Returns:
        Number of chunks indexed
    """
    import os
    import cohere
    from qdrant_client import QdrantClient
    from qdrant_client.models import PointStruct, VectorParams, Distance
    import uuid
    
    # Initialize clients
    co = cohere.ClientV2(api_key=os.environ["COHERE_API_KEY"])
    qdrant = QdrantClient(
        url=os.environ["QDRANT_URL"],
        api_key=os.environ["QDRANT_API_KEY"],
    )
    
    collection_name = "devchat_v2"
    vector_name = "dense"  # Named vector in existing collection
    
    # Ensure collection exists with correct config for Cohere embed-v4.0 (1536 dims)
    try:
        collection_info = qdrant.get_collection(collection_name)
        vectors_config = collection_info.config.params.vectors
        
        # Check if we need to recreate (wrong dimensions or config)
        needs_recreate = False
        if isinstance(vectors_config, dict):
            if vector_name in vectors_config:
                if vectors_config[vector_name].size != 1536:
                    needs_recreate = True
                    print(f"  Collection has wrong dimensions: {vectors_config[vector_name].size} (need 1536)")
            else:
                needs_recreate = True
                print(f"  Collection missing vector '{vector_name}'")
        else:
            # Unnamed vector config
            needs_recreate = True
            print("  Collection has unnamed vectors, need named 'dense'")
        
        if needs_recreate:
            # Check if collection is empty before recreating
            count = qdrant.count(collection_name).count
            if count > 0:
                print(f"  WARNING: Collection has {count} points, will be deleted!")
            
            qdrant.delete_collection(collection_name)
            print(f"  Deleted old collection")
            raise Exception("Recreate collection")
            
    except Exception as e:
        print(f"  Creating collection with Cohere 1536-dim vectors...")
        qdrant.create_collection(
            collection_name=collection_name,
            vectors_config={
                vector_name: VectorParams(size=1536, distance=Distance.COSINE)
            },
        )
        print(f"  Created collection '{collection_name}' with named vector '{vector_name}'")
    
    # Ensure payload index exists for efficient filtering by doc_id
    try:
        from qdrant_client.models import PayloadSchemaType
        for field in ["doc_id", "pdf_name"]:  # Index both for backward compatibility
            try:
                qdrant.create_payload_index(
                    collection_name=collection_name,
                    field_name=field,
                    field_schema=PayloadSchemaType.KEYWORD,
                )
                print(f"  Created payload index on '{field}'")
            except Exception:
                pass  # Index might already exist
    except Exception as e:
        print(f"  Note: Could not create indexes: {e}")
    
    # Simple chunking (semantic chunking could be added)
    chunks = chunk_content(content, chunk_size=512, overlap=50)
    
    if not chunks:
        return 0
    
    # Generate embeddings in batches
    batch_size = 96
    points = []
    
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i + batch_size]
        
        response = co.embed(
            texts=batch,
            model="embed-v4.0",
            input_type="search_document",
            embedding_types=["float"],
        )
        
        embeddings = response.embeddings.float_
        
        for j, (chunk, embedding) in enumerate(zip(batch, embeddings)):
            point_id = str(uuid.uuid4())
            points.append(
                PointStruct(
                    id=point_id,
                    vector={vector_name: embedding},  # Named vector
                    payload={
                        "text": chunk,
                        "doc_id": doc_id,  # Universal document ID
                        "pdf_name": doc_id,  # Backward compatibility
                        "source": metadata.get("source", ""),
                        "title": metadata.get("title", ""),
                        "authors": metadata.get("authors", []),
                        "year": metadata.get("year"),
                        "chunk_index": i + j,
                    },
                )
            )
    
    # Upsert to Qdrant
    qdrant.upsert(collection_name=collection_name, points=points)
    
    return len(points)


def chunk_content(text: str, chunk_size: int = 512, overlap: int = 50) -> list[str]:
    """Split text into overlapping chunks."""
    words = text.split()
    chunks = []
    
    for i in range(0, len(words), chunk_size - overlap):
        chunk = " ".join(words[i:i + chunk_size])
        if chunk.strip():
            chunks.append(chunk)
    
    return chunks


# ============================================================================
# Utility Functions
# ============================================================================

@app.function(
    image=base_image,
    secrets=[r2_secret],
)
def list_pdfs() -> dict:
    """List all PDFs in R2 bucket."""
    s3 = get_r2_client()
    bucket = get_bucket_name()
    
    input_response = s3.list_objects_v2(Bucket=bucket, Prefix="input-pdfs/")
    output_response = s3.list_objects_v2(Bucket=bucket, Prefix="outputs/json/")
    
    input_pdfs = [
        obj["Key"] for obj in input_response.get("Contents", [])
        if obj["Key"].lower().endswith(".pdf")
    ]
    
    processed = [
        Path(obj["Key"]).stem for obj in output_response.get("Contents", [])
    ]
    
    return {
        "total_input": len(input_pdfs),
        "processed": len(processed),
        "pending": len(set(Path(p).stem for p in input_pdfs) - set(processed)),
        "input_pdfs": input_pdfs[:20],
        "processed_names": processed[:20],
    }


@app.function(
    image=base_image,
    secrets=[qdrant_secret],
)
def check_qdrant() -> dict:
    """Check Qdrant collection status."""
    import os
    from qdrant_client import QdrantClient
    
    qdrant = QdrantClient(
        url=os.environ["QDRANT_URL"],
        api_key=os.environ["QDRANT_API_KEY"],
    )
    
    try:
        info = qdrant.get_collection("devchat_v2")
        return {
            "status": "connected",
            "points_count": info.points_count,
            "vectors_count": info.vectors_count,
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ============================================================================
# CLI Entry Points
# ============================================================================

@app.local_entrypoint()
def main(
    action: str = "status",
    pdf_key: str = None,
    force: bool = False,
):
    """
    CLI for MinerU processing.
    
    Actions:
        status  - Show R2 and Qdrant status
        run     - Process all pending PDFs
        single  - Process a single PDF (requires --pdf-key)
    """
    if action == "status":
        print("\n📁 R2 Storage:")
        r2_status = list_pdfs.remote()
        print(f"   Input PDFs: {r2_status['total_input']}")
        print(f"   Processed: {r2_status['processed']}")
        print(f"   Pending: {r2_status['pending']}")
        
        print("\n🔍 Qdrant:")
        qdrant_status = check_qdrant.remote()
        print(f"   Status: {qdrant_status['status']}")
        if "points_count" in qdrant_status:
            print(f"   Vectors: {qdrant_status['points_count']}")
    
    elif action == "run":
        print("\n🚀 Starting batch processing...")
        result = orchestrate.remote(force_reprocess=force)
        print(f"   Queued: {result['queued']}")
        print(f"   Skipped: {result['skipped']}")
        print(f"   Total: {result['total']}")
    
    elif action == "single":
        if not pdf_key:
            print("❌ --pdf-key required for single processing")
            return
        print(f"\n📄 Processing: {pdf_key}")
        result = process_pdf.remote(pdf_key=pdf_key)
        print(f"   Success: {result['success']}")
        if result["success"]:
            print(f"   Chunks indexed: {result['chunks_indexed']}")
            print(f"   Time: {result['elapsed_seconds']:.1f}s")
        else:
            print(f"   Error: {result.get('error')}")
    
    else:
        print(f"Unknown action: {action}")
        print("Use: status, run, or single")


# ============================================================================
# Scheduled Processing (Optional)
# ============================================================================

@app.function(
    image=base_image,
    secrets=[r2_secret],
    schedule=modal.Cron("0 * * * *"),  # Every hour
)
def scheduled_processing():
    """Run orchestrator on schedule to pick up new PDFs."""
    print(f"Scheduled run at {datetime.now().isoformat()}")
    result = orchestrate.remote()
    print(f"Queued {result['queued']} new PDFs")
    return result


# ============================================================================
# HTTP Web Endpoint (for Railway trigger)
# ============================================================================

@app.function(
    image=base_image,
    secrets=[r2_secret, qdrant_secret, cohere_secret],
    timeout=600,
)
@modal.web_endpoint(method="POST")
def trigger_processing(request: dict = None) -> dict:
    """
    HTTP endpoint to trigger PDF processing from Railway/Vercel.
    
    POST body (all optional):
        {
            "force_reprocess": false,
            "check_qdrant": true,
            "max_documents": 10,
            "api_key": "optional-secret-key"
        }
    
    Returns:
        {
            "success": true,
            "queued": 5,
            "skipped": 3,
            "message": "Processing started"
        }
    
    URL will be like:
        https://[your-workspace]--devchat-mineru-trigger-processing.modal.run
    """
    import os
    from datetime import datetime
    
    print(f"Trigger received at {datetime.now().isoformat()}")
    
    # Parse request body
    if request is None:
        request = {}
    
    force_reprocess = request.get("force_reprocess", False)
    check_qdrant = request.get("check_qdrant", True)
    max_documents = request.get("max_documents", 10)
    
    # Optional API key validation
    expected_key = os.environ.get("TRIGGER_API_KEY")
    if expected_key:
        provided_key = request.get("api_key")
        if provided_key != expected_key:
            return {
                "success": False,
                "error": "Invalid or missing API key",
                "queued": 0,
            }
    
    try:
        # Call the orchestrator (spawns in Modal's infrastructure)
        result = orchestrate.remote(
            force_reprocess=force_reprocess,
            check_qdrant=check_qdrant
        )
        
        return {
            "success": True,
            "queued": result.get("queued", 0),
            "skipped": result.get("skipped", 0),
            "message": f"Processing triggered. Queued {result.get('queued', 0)} PDFs.",
        }
        
    except Exception as e:
        print(f"Error in trigger: {e}")
        return {
            "success": False,
            "error": str(e),
            "queued": 0,
        }
