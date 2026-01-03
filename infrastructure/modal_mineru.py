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

# Collection name for Qdrant - using enhanced collection with post-processing
QDRANT_COLLECTION_NAME = "devchat_v2_enhanced"

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
        "pydantic>=2.0.0",
        "pydantic-settings>=2.0.0",
        "supabase>=2.0.0",
    )
)

# Volume for caching HuggingFace models (persists across runs)
model_cache = modal.Volume.from_name("mineru-model-cache", create_if_missing=True)

# Secrets
r2_secret = modal.Secret.from_name("r2-credentials")
qdrant_secret = modal.Secret.from_name("qdrant-credentials")
cohere_secret = modal.Secret.from_name("cohere-credentials")
openrouter_secret = modal.Secret.from_name("openrouter-credentials")
supabase_secret = modal.Secret.from_name("SUPABASE")


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


def sanitize_text(text: str) -> str:
    """
    Remove invalid UTF-8 characters (surrogates) from text.
    
    Some PDFs contain malformed Unicode that causes:
    'utf-8' codec can't encode characters: surrogates not allowed
    
    This function removes those problematic characters.
    """
    if not isinstance(text, str):
        return text
    # Encode to UTF-8, replacing errors, then decode back
    return text.encode("utf-8", errors="surrogatepass").decode("utf-8", errors="replace")


def sanitize_dict(obj):
    """Recursively sanitize all strings in a dict/list structure."""
    if isinstance(obj, str):
        return sanitize_text(obj)
    elif isinstance(obj, dict):
        return {k: sanitize_dict(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [sanitize_dict(item) for item in obj]
    else:
        return obj


# ============================================================================
# Post-Processing for Better RAG (Phase 2)
# ============================================================================

def post_process_content(
    content: str,
    title: str = None,
    authors: list = None,
    year: int = None,
    pdf_name: str = None,
) -> str:
    """
    Clean and enhance MinerU markdown output for better RAG retrieval.
    
    Features:
    - OCR artifact cleanup
    - Running headers/footers removal
    - Reference section removal (reduces citation noise)
    - Sentence boundary repair
    - Table normalization (mark malformed tables)
    - Equation cleanup
    - Document header addition (for context)
    
    Args:
        content: Raw MinerU markdown
        title, authors, year, pdf_name: Document metadata
        
    Returns:
        Enhanced markdown ready for chunking
    """
    import re
    
    original_len = len(content)
    
    # Step 1: Clean OCR artifacts
    # Fix common character substitutions
    content = re.sub(r"\bl(?=\d)", "1", content)  # l -> 1 when followed by digit
    content = re.sub(r"(?<=\d)l\b", "1", content)  # l -> 1 when preceded by digit
    content = re.sub(r"\bO(?=\d)", "0", content)  # O -> 0 when followed by digit
    content = re.sub(r"(?<=\d)O\b", "0", content)  # O -> 0 when preceded by digit
    
    # Fix hyphenation across lines
    content = re.sub(r"(\w+)-\s*\n\s*(\w+)", r"\1\2", content)
    
    # Fix ligatures
    content = content.replace("ﬁ", "fi").replace("ﬂ", "fl")
    content = content.replace("ﬀ", "ff").replace("ﬃ", "ffi").replace("ﬄ", "ffl")
    
    # Step 2: Remove running headers/footers
    # Remove standalone page numbers
    content = re.sub(r"^\s*\d{1,4}\s*$", "", content, flags=re.MULTILINE)
    content = re.sub(r"^.*Page \d+ of \d+.*$", "", content, flags=re.MULTILINE)
    content = re.sub(r"^-\s*\d+\s*-$", "", content, flags=re.MULTILINE)
    # Remove PREPRINT/DRAFT markers
    content = re.sub(r"^.*\bPREPRINT\b.*$", "", content, flags=re.MULTILINE | re.IGNORECASE)
    content = re.sub(r"^.*\bDRAFT\b.*$", "", content, flags=re.MULTILINE | re.IGNORECASE)
    # Remove download notices
    content = re.sub(r"^\s*Downloaded from\s+.*$", "", content, flags=re.MULTILINE | re.IGNORECASE)
    
    # Fix spacing
    content = re.sub(r"  +", " ", content)
    content = re.sub(r"\n{4,}", "\n\n\n", content)
    
    # Step 3: Remove references section (prevents citation noise in retrieval)
    ref_pattern = r"(?i)^#{1,3}\s*(?:\d+\.?\s*)?(?:references?|bibliography|works\s+cited|literature\s+cited)\s*$"
    lines = content.split("\n")
    result_lines = []
    in_references = False
    next_section_pattern = r"^#{1,3}\s+\w"
    
    for line in lines:
        if re.match(ref_pattern, line.strip()):
            in_references = True
            print(f"    Post-processing: Found references section, removing...")
            continue
        
        if in_references:
            # Check if we've hit another main section
            if re.match(next_section_pattern, line.strip()):
                if not re.match(ref_pattern, line.strip()):
                    in_references = False
                    result_lines.append(line)
        else:
            result_lines.append(line)
    
    content = "\n".join(result_lines)
    
    # Step 4: Clean footnote markers
    content = re.sub(r"\[\d{1,3}\](?!\()", "", content)
    content = re.sub(r"^\[\d+\]:\s*.*$", "", content, flags=re.MULTILINE)
    
    # Step 5: Handle malformed tables (mark them for exclusion)
    def is_table_malformed(table_text):
        lines = [l for l in table_text.strip().split("\n") if l.strip()]
        if len(lines) < 2:
            return True
        col_counts = [line.count("|") for line in lines]
        if max(col_counts) - min(col_counts) > 2:
            return True
        has_separator = any("-" * 3 in line and "|" in line for line in lines[:3])
        if not has_separator:
            return True
        return False
    
    table_pattern = r"(\|[^\n]+\|(?:\n\|[^\n]+\|)+)"
    def process_table(match):
        table = match.group(1)
        if is_table_malformed(table):
            return "\n<!-- MALFORMED_TABLE: Content removed for RAG quality -->\n"
        return table
    
    content = re.sub(table_pattern, process_table, content)
    
    # Step 6: Clean up broken equations
    content = re.sub(r"\$\$[^$]{500,}\$\$", "[Complex equation removed]", content)
    content = re.sub(r"\\begin\{equation\}.*?\\end\{equation\}", "[Equation]", content, flags=re.DOTALL)
    content = re.sub(r"\\begin\{align\}.*?\\end\{align\}", "[Equation]", content, flags=re.DOTALL)
    
    # Step 7: Add document header for context
    if title or authors or year:
        header_parts = []
        if title:
            header_parts.append(f"# {title}")
        
        metadata_items = []
        if authors:
            author_str = ", ".join(authors[:3])
            if len(authors) > 3:
                author_str += " et al."
            metadata_items.append(f"**Authors:** {author_str}")
        if year:
            metadata_items.append(f"**Year:** {year}")
        if pdf_name:
            metadata_items.append(f"**Source:** {pdf_name}")
        
        if metadata_items:
            header_parts.append(" | ".join(metadata_items))
        
        if header_parts:
            header_parts.append("\n---\n")
            content = "\n".join(header_parts) + content
    
    # Log results
    final_len = len(content)
    reduction = (1 - final_len / original_len) * 100 if original_len > 0 else 0
    print(f"    Post-processing: {original_len} -> {final_len} chars ({reduction:.1f}% reduction)")
    
    return content


def compute_content_hash(content: bytes) -> str:
    """Compute MD5 hash of content for change detection."""
    return hashlib.md5(content).hexdigest()[:16]


def check_qdrant_indexed(pdf_name: str) -> tuple[bool, int, str | None]:
    """
    Check if a PDF is already indexed in Qdrant.
    
    IMPORTANT: Handles both formats:
    - pdf_name WITHOUT extension (from Path.stem): "033d4e4c_121058373"
    - pdf_name WITH extension (as stored in Qdrant): "033d4e4c_121058373.pdf"
    
    Returns:
        (is_indexed, chunk_count, error_message)
        - error_message is None if check succeeded, otherwise contains error details
    """
    import os
    from qdrant_client import QdrantClient
    from qdrant_client.models import Filter, FieldCondition, MatchValue, MatchAny
    
    try:
        qdrant = QdrantClient(
            url=os.environ["QDRANT_URL"],
            api_key=os.environ["QDRANT_API_KEY"],
        )
        
        # First check if collection exists
        try:
            qdrant.get_collection(QDRANT_COLLECTION_NAME)
        except Exception:
            return False, 0, None  # Collection doesn't exist, not an error
        
        # Build list of names to check (with and without .pdf extension)
        names_to_check = [pdf_name]
        if pdf_name.endswith(".pdf"):
            names_to_check.append(pdf_name[:-4])  # Also check without extension
        else:
            names_to_check.append(pdf_name + ".pdf")  # Also check with extension
        
        # Try to count with filter - check BOTH formats
        try:
            result = qdrant.count(
                collection_name=QDRANT_COLLECTION_NAME,
                count_filter=Filter(
                    should=[
                        FieldCondition(key="pdf_name", match=MatchValue(value=name))
                        for name in names_to_check
                    ]
                ),
            )
            if result.count > 0:
                print(f"    ✓ Found {result.count} chunks for {pdf_name}")
            return result.count > 0, result.count, None
        except Exception as filter_error:
            # If filter fails (no index), fall back to scroll search
            if "index required" in str(filter_error).lower():
                print(f"  Note: No index on pdf_name, using scroll fallback")
                # Scroll through all points to check (slower but works)
                scroll_result = qdrant.scroll(
                    collection_name=QDRANT_COLLECTION_NAME,
                    scroll_filter=None,
                    limit=100,
                    with_payload=["pdf_name"],
                )
                results = scroll_result[0] if isinstance(scroll_result, tuple) else scroll_result
                # Check against all name variants
                count = sum(1 for r in results if r.payload.get("pdf_name") in names_to_check)
                return count > 0, count, None
            raise
            
    except Exception as e:
        error_msg = str(e)
        print(f"  Qdrant check failed: {error_msg}")
        # Return error so caller can decide how to handle
        return False, 0, error_msg


def ensure_qdrant_indexes():
    """
    Ensure payload indexes exist for fast lookups.
    Safely no-ops if indexes already exist.
    """
    import os
    from qdrant_client import QdrantClient
    from qdrant_client.models import PayloadSchemaType

    try:
        qdrant = QdrantClient(
            url=os.environ["QDRANT_URL"],
            api_key=os.environ["QDRANT_API_KEY"],
        )

        indexes = {
            "doc_id": PayloadSchemaType.KEYWORD,
            "pdf_name": PayloadSchemaType.KEYWORD,
        }

        for field, schema in indexes.items():
            try:
                qdrant.create_payload_index(
                    collection_name=QDRANT_COLLECTION_NAME,
                    field_name=field,
                    field_schema=schema,
                )
                print(f"  Created payload index on '{field}'")
            except Exception as e:
                # Ignore "already exists", warn on others
                if "exists" not in str(e).lower():
                    print(f"  Warning: could not create index {field}: {e}")
    except Exception as e:
        print(f"  Warning: failed to ensure Qdrant indexes: {e}")


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
            collection_name=QDRANT_COLLECTION_NAME,
            count_filter=Filter(
                must=[FieldCondition(key="pdf_name", match=MatchValue(value=pdf_name))]
            ),
        ).count
        
        if count_before > 0:
            qdrant.delete(
                collection_name=QDRANT_COLLECTION_NAME,
                points_selector=Filter(
                    must=[FieldCondition(key="pdf_name", match=MatchValue(value=pdf_name))]
                ),
            )
            print(f"  Deleted {count_before} old chunks from Qdrant")
        
        return count_before
    except Exception as e:
        print(f"  Qdrant delete failed: {e}")
        return 0


def sync_to_postgres(doc_id: str, metadata: dict, chunk_count: int, page_count: int) -> bool:
    """
    Sync document metadata to PostgreSQL via Railway backend API.
    
    Called after successful Qdrant indexing to keep Postgres in sync.
    This is non-blocking - failures are logged but don't stop processing.
    
    Args:
        doc_id: Document identifier
        metadata: Enriched metadata dict from metadata pipeline
        chunk_count: Number of chunks indexed
        page_count: Number of pages in document
        
    Returns:
        True if sync succeeded, False otherwise
    """
    import httpx
    import os
    
    # Railway backend URL (production)
    backend_url = os.environ.get("BACKEND_URL", "https://3iechat.up.railway.app")
    sync_endpoint = f"{backend_url}/admin/documents/sync"
    
    # Handle authors - could be string or list
    authors = metadata.get("authors", [])
    if isinstance(authors, str):
        authors = [a.strip() for a in authors.split(",") if a.strip()]
    
    # Handle intervention_type - could be list
    intervention_type = metadata.get("intervention_type")
    if isinstance(intervention_type, list):
        intervention_type = ", ".join(intervention_type)
    
    # Build sync payload
    payload = {
        "doc_id": doc_id,
        "title": metadata.get("title", doc_id),
        "filename": f"{doc_id}.pdf",
        "authors": authors,
        "year": metadata.get("year"),
        "doi": metadata.get("doi"),
        "abstract": metadata.get("abstract"),
        "item_type": metadata.get("item_type"),
        "journal": metadata.get("journal"),
        "publisher": metadata.get("publisher"),
        "volume": metadata.get("volume"),
        "issue": metadata.get("issue"),
        "pages": metadata.get("pages"),
        "cited_by_count": metadata.get("cited_by_count"),
        "is_open_access": metadata.get("is_open_access", False),
        "countries": metadata.get("countries", []),
        "sectors": metadata.get("sectors", []),
        "study_type": metadata.get("study_type"),
        "intervention_type": intervention_type,
        "sdgs": metadata.get("sdgs", []),
        "keywords": metadata.get("keywords", []),
        "chunk_count": chunk_count,
        "page_count": page_count,
        "metadata_source": metadata.get("metadata_source", "extraction"),
        "metadata_confidence": metadata.get("metadata_confidence", 0.0),
        "needs_review": metadata.get("needs_review", True),
    }
    
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(sync_endpoint, json=payload)
            
            if response.status_code == 200:
                result = response.json()
                print(f"  Synced to Postgres: {result.get('action', 'unknown')} (doc_id={doc_id})")
                return True
            else:
                print(f"  Postgres sync failed: HTTP {response.status_code} - {response.text[:200]}")
                return False
                
    except Exception as e:
        # Non-fatal - log and continue
        print(f"  Postgres sync error (non-fatal): {e}")
        return False


# ============================================================================
# Orchestrator (CPU) - Lists PDFs and spawns GPU workers
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
    from collections import Counter
    
    # ==========================================================================
    # SAFETY CHECK: Detect if Qdrant already has excessive duplicates
    # ==========================================================================
    print("Running Qdrant duplication safety check...")
    try:
        from qdrant_client import QdrantClient
        import os
        qdrant = QdrantClient(
            url=os.environ["QDRANT_URL"],
            api_key=os.environ["QDRANT_API_KEY"],
        )
        
        # Sample 2000 points and check for duplicates
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
                print("  Run deduplication before processing more documents!")
                # Don't abort - just warn. User may want to add new docs.
            else:
                print(f"  ✓ Duplication check passed (max {max_dup}x)")
    except Exception as e:
        print(f"  Note: Could not run duplication check: {e}")
    # ==========================================================================
    
    s3 = get_r2_client()
    bucket = get_bucket_name()
    
    # List input PDFs (with pagination for >1000 files)
    input_prefix = "input-pdfs/"
    pdf_keys = []
    continuation_token = None
    
    while True:
        if continuation_token:
            response = s3.list_objects_v2(
                Bucket=bucket, Prefix=input_prefix, ContinuationToken=continuation_token
            )
        else:
            response = s3.list_objects_v2(Bucket=bucket, Prefix=input_prefix)
        
        if "Contents" in response:
            pdf_keys.extend([
                obj["Key"] for obj in response["Contents"]
                if obj["Key"].lower().endswith(".pdf")
            ])
        
        if response.get("IsTruncated"):
            continuation_token = response.get("NextContinuationToken")
        else:
            break
    
    if not pdf_keys:
        return {"message": "No PDFs found in input-pdfs/", "queued": 0}
    
    print(f"Found {len(pdf_keys)} PDFs in R2")
    
    # Detect duplicates by base name (ignoring hash prefix)
    # Format: {hash}_{base_name}.pdf -> extract base_name
    def extract_base_name(pdf_key: str) -> str:
        """Extract base name without hash prefix."""
        stem = Path(pdf_key).stem  # e.g., "abc12345_Author_(2020)"
        if "_" in stem and len(stem.split("_")[0]) == 8:
            # Looks like our format: {8-char-hash}_{base_name}
            return "_".join(stem.split("_")[1:])
        return stem
    
    # Group PDFs by base name to find duplicates
    base_name_to_keys = {}
    for pdf_key in pdf_keys:
        base = extract_base_name(pdf_key)
        if base not in base_name_to_keys:
            base_name_to_keys[base] = []
        base_name_to_keys[base].append(pdf_key)
    
    # Identify duplicates (same base name, different hash)
    duplicates = {base: keys for base, keys in base_name_to_keys.items() if len(keys) > 1}
    if duplicates:
        print(f"⚠ Found {len(duplicates)} duplicate base names with multiple versions:")
        for base, keys in list(duplicates.items())[:5]:
            print(f"    {base}: {[Path(k).stem for k in keys]}")
    
    # Check which ones already have outputs in R2 (with pagination)
    output_prefix = "outputs/json/"
    existing_outputs = set()
    continuation_token = None
    
    while True:
        if continuation_token:
            existing_response = s3.list_objects_v2(
                Bucket=bucket, Prefix=output_prefix, ContinuationToken=continuation_token
            )
        else:
            existing_response = s3.list_objects_v2(Bucket=bucket, Prefix=output_prefix)
        
        if "Contents" in existing_response:
            existing_outputs.update(
                Path(obj["Key"]).stem for obj in existing_response["Contents"]
            )
        
        if existing_response.get("IsTruncated"):
            continuation_token = existing_response.get("NextContinuationToken")
        else:
            break
    
    print(f"Found {len(existing_outputs)} existing JSON outputs in R2")
    
    # Also check Qdrant for indexed base names (to skip duplicates of already-indexed docs)
    indexed_base_names = set()
    for output_name in existing_outputs:
        indexed_base_names.add(extract_base_name(f"{output_name}.pdf"))
    
    # Queue new PDFs for processing
    queued = []
    skipped_r2 = []
    skipped_qdrant = []
    needs_reindex = []
    skipped_limit = []  # PDFs skipped due to max_documents limit
    skipped_errors = []  # PDFs skipped due to Qdrant check errors
    skipped_duplicates = []  # PDFs skipped because another version is already indexed
    
    for pdf_key in pdf_keys:
        pdf_name = Path(pdf_key).stem
        base_name = extract_base_name(pdf_key)
        
        # Check if this is a duplicate of an already-indexed document
        if base_name in indexed_base_names and pdf_name not in existing_outputs:
            skipped_duplicates.append(pdf_key)
            print(f"  🔄 Skipping duplicate (another version indexed): {pdf_key}")
            continue
        
        # Check 1: R2 output exists?
        has_r2_output = pdf_name in existing_outputs
        
        if has_r2_output and not force_reprocess:
            # Check 2: Qdrant indexed? (optional but recommended)
            if check_qdrant:
                is_indexed, chunk_count, qdrant_error = check_qdrant_indexed(pdf_name)
                
                # If Qdrant check failed with error, skip this PDF to avoid duplicate processing
                if qdrant_error:
                    skipped_errors.append({"key": pdf_key, "error": qdrant_error})
                    print(f"  ❌ Skipping (Qdrant error, R2 has output): {pdf_key} - {qdrant_error}")
                    continue
                
                if is_indexed:
                    skipped_qdrant.append({"key": pdf_key, "chunks": chunk_count})
                    print(f"  ✓ Skipping (R2 + Qdrant OK, {chunk_count} chunks): {pdf_key}")
                    continue
                else:
                    # R2 has output but Qdrant missing - needs re-indexing only
                    # Also respect max_documents limit for re-indexing
                    if max_documents > 0 and (len(queued) + len(needs_reindex)) >= max_documents:
                        skipped_limit.append(pdf_key)
                        print(f"  ⏸ Skipping (limit reached): {pdf_key}")
                        continue
                    needs_reindex.append(pdf_key)
                    print(f"  ⚠ Re-indexing (R2 OK, Qdrant missing): {pdf_key}")
                    process_pdf.spawn(pdf_key=pdf_key, skip_extraction=True)
                    continue
            else:
                skipped_r2.append(pdf_key)
                print(f"  Skipping (R2 output exists): {pdf_key}")
                continue
        
        # Check max_documents limit before queuing
        if max_documents > 0 and (len(queued) + len(needs_reindex)) >= max_documents:
            skipped_limit.append(pdf_key)
            print(f"  ⏸ Skipping (limit reached): {pdf_key}")
            continue
        
        # Queue for full processing
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
        "error_files": [e["key"] for e in skipped_errors[:5]],
        "duplicate_files": skipped_duplicates[:5],
    }


# ============================================================================
# RAG Project Orchestrator - Process documents for a specific RAG project
# ============================================================================

@app.function(
    image=base_image,
    secrets=[r2_secret, qdrant_secret, cohere_secret, supabase_secret],
    timeout=3600,  # 1 hour for large batches
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
    
    Flow:
    1. List PDFs in rags/{project_id}/input-pdfs/
    2. Check which ones have outputs in rags/{project_id}/outputs/
    3. Check Qdrant collection for existing embeddings (looked up from database)
    4. Process new PDFs with MinerU + metadata enrichment
    5. Embed to project-specific Qdrant collection
    6. Sync metadata back to Supabase documents table
    
    Args:
        project_id: The RAG project UUID
        qdrant_collection: Optional override (default: lookup from database)
        force_reprocess: If True, reprocess all PDFs
        max_documents: Max docs to process (0 = unlimited)
        
    Returns:
        dict with processing stats
    """
    import boto3
    import os
    import httpx
    from collections import Counter
    
    s3 = get_r2_client()
    bucket = get_bucket_name()
    
    # Get the actual collection name from the database if not provided
    if not qdrant_collection:
        from supabase import create_client
        supabase = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])
        project_result = supabase.table("rag_projects").select("qdrant_collection").eq("id", project_id).single().execute()
        if project_result.data and project_result.data.get("qdrant_collection"):
            collection = project_result.data["qdrant_collection"]
        else:
            # Fallback - should not happen for existing projects
            collection = f"rag_{project_id}"
    else:
        collection = qdrant_collection
    
    # R2 paths for this project
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
            response = s3.list_objects_v2(
                Bucket=bucket, Prefix=input_prefix, ContinuationToken=continuation_token
            )
        else:
            response = s3.list_objects_v2(Bucket=bucket, Prefix=input_prefix)
        
        if "Contents" in response:
            pdf_keys.extend([
                obj["Key"] for obj in response["Contents"]
                if obj["Key"].lower().endswith(".pdf")
            ])
        
        if response.get("IsTruncated"):
            continuation_token = response.get("NextContinuationToken")
        else:
            break
    
    if not pdf_keys:
        print("No PDFs found")
        return {"message": "No PDFs found", "queued": 0, "project_id": project_id}
    
    print(f"Found {len(pdf_keys)} PDFs in R2")
    
    # Check existing outputs
    existing_outputs = set()
    continuation_token = None
    json_prefix = f"{output_prefix}json/"
    
    while True:
        if continuation_token:
            response = s3.list_objects_v2(
                Bucket=bucket, Prefix=json_prefix, ContinuationToken=continuation_token
            )
        else:
            response = s3.list_objects_v2(Bucket=bucket, Prefix=json_prefix)
        
        if "Contents" in response:
            for obj in response["Contents"]:
                # Extract doc_id from json filename
                json_name = Path(obj["Key"]).stem
                existing_outputs.add(json_name)
        
        if response.get("IsTruncated"):
            continuation_token = response.get("NextContinuationToken")
        else:
            break
    
    print(f"Found {len(existing_outputs)} existing outputs")
    
    # Check Qdrant for existing vectors
    qdrant_indexed = set()
    try:
        from qdrant_client import QdrantClient
        from qdrant_client.http.models import ScrollRequest
        
        qdrant = QdrantClient(
            url=os.environ["QDRANT_URL"],
            api_key=os.environ["QDRANT_API_KEY"],
        )
        
        # Check if collection exists
        try:
            qdrant.get_collection(collection)
            # Scroll through to get all unique source values (doc IDs)
            offset = None
            while True:
                results, next_offset = qdrant.scroll(
                    collection_name=collection,
                    limit=100,
                    with_payload=["source"],
                    offset=offset,
                )
                for point in results:
                    source = point.payload.get("source", "")
                    if source:
                        # source is like "docname.pdf" or "docname"
                        qdrant_indexed.add(source.replace(".pdf", ""))
                if next_offset is None:
                    break
                offset = next_offset
            print(f"Found {len(qdrant_indexed)} documents indexed in Qdrant")
        except Exception as e:
            print(f"  Collection {collection} doesn't exist yet")
    except Exception as e:
        print(f"  Qdrant check failed: {e}")
    
    # Determine which PDFs to process
    to_process = []
    to_reindex = []  # Have R2 output but no Qdrant vectors
    skipped = []
    
    for pdf_key in pdf_keys:
        # Generate doc_id the same way as process_pdf_rag
        pdf_name = Path(pdf_key).stem
        doc_id = pdf_name  # Could add hash if needed
        
        has_r2_output = doc_id in existing_outputs
        has_qdrant = doc_id in qdrant_indexed
        
        if not force_reprocess:
            if has_r2_output and has_qdrant:
                # Fully processed
                skipped.append(pdf_key)
                print(f"  ✓ Skipping (R2 + Qdrant OK): {pdf_name}")
                continue
            elif has_r2_output and not has_qdrant:
                # Need to re-embed only
                if max_documents > 0 and (len(to_process) + len(to_reindex)) >= max_documents:
                    skipped.append(pdf_key)
                    print(f"  ⏸ Skipping (limit reached): {pdf_name}")
                    continue
                to_reindex.append(pdf_key)
                print(f"  ⚠ Re-indexing (R2 OK, Qdrant missing): {pdf_name}")
                continue
        
        # Apply limit
        if max_documents > 0 and (len(to_process) + len(to_reindex)) >= max_documents:
            skipped.append(pdf_key)
            print(f"  ⏸ Skipping (limit reached): {pdf_name}")
            continue
        
        # Add to processing queue
        print(f"  Queuing: {pdf_name}")
        to_process.append(pdf_key)
    
    all_to_process = to_process + to_reindex
    
    if not all_to_process:
        print("No new PDFs to process")
        return {
            "project_id": project_id,
            "qdrant_collection": collection,
            "processed": 0,
            "skipped": len(skipped),
            "total": len(pdf_keys),
            "results": [],
        }
    
    print(f"\nProcessing {len(all_to_process)} PDFs ({len(to_process)} new, {len(to_reindex)} re-index)...")
    
    # Use starmap to process all PDFs in parallel and WAIT for completion
    # This is the key fix - spawn() doesn't wait, but starmap() does
    results = []
    success = 0
    failed = 0
    
    for result in process_pdf_rag.starmap(
        [(pdf_key, project_id, collection) for pdf_key in all_to_process],
        return_exceptions=True,
    ):
        if isinstance(result, Exception):
            print(f"  ✗ Error: {result}")
            failed += 1
            results.append({"error": str(result)})
        else:
            print(f"  ✓ Completed: {result.get('pdf_name', 'unknown')}")
            success += 1
            results.append(result)
    
    print(f"\nProcessing complete: {success} succeeded, {failed} failed")
    
    return {
        "project_id": project_id,
        "qdrant_collection": collection,
        "processed": success,
        "failed": failed,
        "skipped": len(skipped),
        "total": len(pdf_keys),
        "results": results[:10],  # First 10 results for summary
    }


@app.function(
    image=base_image,
    secrets=[r2_secret, qdrant_secret, cohere_secret, supabase_secret],
    volumes={"/cache": model_cache},
    gpu="T4",
    timeout=1800,
    retries=2,
)
def process_pdf_rag(
    pdf_key: str,
    project_id: str,
    qdrant_collection: str,
) -> dict:
    """
    Process a single PDF for a RAG project.
    
    Similar to process_pdf but:
    - Uses project-specific R2 paths
    - Uses project-specific Qdrant collection
    - Syncs metadata to documents table with rag_project_id
    
    Args:
        pdf_key: Full R2 key (e.g., rags/{project_id}/input-pdfs/paper.pdf)
        project_id: RAG project UUID for Supabase sync
        qdrant_collection: Qdrant collection name (from database)
    """
    import os
    import tempfile
    import httpx
    from pathlib import Path
    
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
        
        # Sanitize content to remove invalid UTF-8 surrogates
        result["content"] = sanitize_text(result["content"])
        
        # Upload outputs to R2 under project folder
        output_prefix = f"rags/{project_id}/outputs"
        
        md_key = f"{output_prefix}/md/{doc_id}.md"
        s3.put_object(
            Bucket=bucket,
            Key=md_key,
            Body=result["content"].encode("utf-8"),
            ContentType="text/markdown",
        )
        
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
        # Sanitize all strings to remove UTF-8 surrogates
        output_data = sanitize_dict(output_data)
        s3.put_object(
            Bucket=bucket,
            Key=json_key,
            Body=json.dumps(output_data, indent=2, ensure_ascii=False).encode("utf-8"),
            ContentType="application/json",
        )
        
        print(f"  Uploaded: {md_key}")
        
        # Resolve metadata (CrossRef + OpenAlex)
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
        
        # Chunk and embed to Qdrant using project-specific collection
        print(f"  Chunking and embedding to {qdrant_collection}...")
        chunk_count = embed_and_index(
            content=result["content"],
            metadata=enriched_metadata,
            doc_id=doc_id,
            content_list=result.get("content_list"),  # Page-aware chunking if available
            collection_name=qdrant_collection,  # Project-specific collection
        )
        
        print(f"  Indexed {chunk_count} chunks to {qdrant_collection}")
        
        # Validate: if no chunks, something went wrong
        if chunk_count == 0:
            print(f"  ⚠ WARNING: 0 chunks indexed! Content length: {len(result.get('content', ''))}")
            # Don't mark as completed if no chunks - needs investigation
            raise Exception(f"No chunks indexed. Content may be empty or too short.")
        
        # Sync to Supabase with project_id
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
        # Update Supabase status to failed
        try:
            backend_url = os.environ.get("BACKEND_URL", "https://3iechat.up.railway.app")
            with httpx.Client(timeout=10.0) as client:
                client.patch(
                    f"{backend_url}/rags/{project_id}/documents/{doc_id}/status",
                    json={"status": "failed", "error": str(e)},
                )
        except:
            pass
        
        return {
            "success": False,
            "doc_id": doc_id,
            "project_id": project_id,
            "error": str(e),
        }


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
    import os
    from pathlib import Path
    from supabase import create_client
    
    supabase_url = os.environ.get("SUPABASE_URL")
    # Support both naming conventions
    supabase_key = os.environ.get("SUPABASE_SERVICE_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    
    if not supabase_url or not supabase_key:
        print("  ⚠ Supabase credentials not configured")
        return False
    
    try:
        client = create_client(supabase_url, supabase_key)
        
        # Find document by 'filename' field (not original_filename)
        # The doc_id matches the 'filename' field which is the R2 key stem
        result = client.table("documents").select("id, filename").eq("rag_project_id", project_id).execute()
        
        matching_doc = None
        for doc in result.data or []:
            filename = doc.get("filename", "")
            
            # Match by filename field (exact match)
            if filename == doc_id:
                matching_doc = doc
                break
        
        if not matching_doc:
            print(f"  ⚠ Document not found in Supabase: {doc_id}")
            print(f"     Looking in project: {project_id}")
            print(f"     Found {len(result.data or [])} documents in project")
            return False
        
        # Get existing metadata to preserve user edits
        existing_result = client.table("documents").select("metadata").eq("id", matching_doc["id"]).execute()
        existing_metadata = {}
        if existing_result.data and existing_result.data[0].get("metadata"):
            existing_metadata = existing_result.data[0]["metadata"]
        
        # Merge: preserve user edits (fields that were manually changed)
        # User-editable fields that should be preserved if they were manually set
        user_editable_fields = [
            "title", "authors", "year", "abstract", "doi", "item_type",
            "journal", "volume", "issue", "pages", "publisher", "place",
            "institution", "series", "countries", "sectors", "study_type",
            "intervention_type", "needs_review",
        ]
        
        merged_metadata = {**metadata}  # Start with new enriched metadata
        
        # Only preserve user edits if metadata_source was already set (not first processing)
        if existing_metadata.get("metadata_source"):
            for field in user_editable_fields:
                # If existing has a value and new doesn't, keep existing
                if field in existing_metadata and existing_metadata[field] is not None:
                    # Keep user edits unless they're the default extraction values
                    if existing_metadata.get("metadata_source") in ["crossref", "openalex", "user"]:
                        merged_metadata[field] = existing_metadata[field]
        
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
# PDF Processor (GPU) - Runs MinerU extraction
# ============================================================================

@app.function(
    image=base_image,
    gpu="T4",  # or "A10G" for faster processing
    timeout=1800,  # 30 min max per PDF
    secrets=[r2_secret, qdrant_secret, cohere_secret, openrouter_secret],
    volumes={"/cache": model_cache},
    retries=0,  # Disable retries to prevent duplicate processing
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
    json_key = f"outputs/json/{doc_id}.json"
    md_key = None  # Set when we actually upload markdown
    lock_key = f"locks/{doc_id}.lock"
    
    # Check for processing lock (prevents duplicate processing)
    try:
        s3.head_object(Bucket=bucket, Key=lock_key)
        print(f"  ⏸ Lock exists - already being processed by another worker, skipping")
        return {
            "success": True,
            "pdf_key": pdf_key,
            "doc_id": doc_id,
            "skipped": True,
            "reason": "locked_by_another_worker",
        }
    except Exception:
        # No lock exists, create one
        try:
            s3.put_object(
                Bucket=bucket,
                Key=lock_key,
                Body=f"Processing started at {start_time.isoformat()}".encode(),
                ContentType="text/plain",
            )
        except Exception as e:
            print(f"  Warning: Could not create lock: {e}")

    try:
        # Ensure payload indexes exist for faster lookups
        ensure_qdrant_indexes()

        # Check if already indexed in Qdrant (unless forcing)
        if not force_reindex:
            is_indexed, existing_chunks, qdrant_err = check_qdrant_indexed(doc_id)
            if qdrant_err:
                print(f"  Warning: Qdrant check failed: {qdrant_err}, proceeding with processing")
            elif is_indexed and not skip_extraction:
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
            
            # Sanitize content to remove invalid Unicode characters (surrogates)
            # that can cause UTF-8 encoding errors
            result["content"] = sanitize_text(result["content"])
            result["tables"] = sanitize_dict(result["tables"])
            result["formulas"] = sanitize_dict(result["formulas"])
            if result.get("title"):
                result["title"] = sanitize_text(result["title"])
            if result.get("abstract"):
                result["abstract"] = sanitize_text(result["abstract"])
            
            # Apply smart post-processing for better RAG (Phase 2)
            # This removes reference sections, cleans OCR artifacts, adds document headers
            result["content"] = post_process_content(
                content=result["content"],
                title=result.get("title"),
                authors=result.get("authors"),
                year=result.get("year"),
                pdf_name=Path(pdf_key).name,
            )
            
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
        
        # ============================================================
        # Metadata Resolution: CrossRef + OpenAlex + LLM
        # ============================================================
        print(f"  Resolving metadata...")
        enriched_metadata = resolve_metadata(
            content=result["content"],
            title=result.get("title"),
            authors=result.get("authors", []),
            year=result.get("year"),
            pdf_filename=Path(pdf_key).name,
        )
        
        # Merge with required fields
        enriched_metadata["doc_id"] = doc_id
        enriched_metadata["source"] = pdf_key
        
        print(f"  Metadata: source={enriched_metadata['metadata_source']}, confidence={enriched_metadata['metadata_confidence']:.2f}")
        
        # Update JSON output with enriched metadata (if we did extraction)
        if not skip_extraction:
            output_data["metadata"] = {
                "doi": enriched_metadata.get("doi"),
                "journal": enriched_metadata.get("journal"),
                "publisher": enriched_metadata.get("publisher"),
                "cited_by_count": enriched_metadata.get("cited_by_count"),
                "is_open_access": enriched_metadata.get("is_open_access"),
                "countries": enriched_metadata.get("countries", []),
                "sectors": enriched_metadata.get("sectors", []),
                "study_type": enriched_metadata.get("study_type"),
                "intervention_type": enriched_metadata.get("intervention_type"),
                "sdgs": enriched_metadata.get("sdgs", []),
                "keywords": enriched_metadata.get("keywords", []),
                "metadata_source": enriched_metadata.get("metadata_source"),
                "metadata_confidence": enriched_metadata.get("metadata_confidence"),
                "needs_review": enriched_metadata.get("needs_review"),
            }
            # Update main fields from enriched metadata
            output_data["title"] = enriched_metadata.get("title") or output_data.get("title")
            output_data["authors"] = enriched_metadata.get("authors") or output_data.get("authors")
            output_data["year"] = enriched_metadata.get("year") or output_data.get("year")
            
            # Re-upload JSON with metadata
            s3.put_object(
                Bucket=bucket,
                Key=json_key,
                Body=json.dumps(output_data, indent=2, ensure_ascii=False).encode("utf-8"),
                ContentType="application/json",
            )
            print(f"  Updated JSON with enriched metadata")
        
        # Generate embeddings and upsert to Qdrant with enriched metadata
        # Pass content_list for page-aware chunking (if available from MinerU)
        chunk_count = embed_and_index(
            content=result["content"],
            metadata=enriched_metadata,
            doc_id=doc_id,
            content_list=result.get("content_list"),  # Page-aware chunking
        )
        
        print(f"  Indexed: {chunk_count} chunks to Qdrant (doc_id={doc_id})")
        
        # Sync to PostgreSQL for instant admin queries
        page_count = result.get("page_count", 0)
        sync_to_postgres(doc_id, enriched_metadata, chunk_count, page_count)
        
        # Clean up (only if we downloaded a PDF)
        if not skip_extraction and 'pdf_path' in dir():
            pdf_path.unlink(missing_ok=True)
        
        # Delete lock on success
        try:
            s3.delete_object(Bucket=bucket, Key=lock_key)
        except Exception:
            pass
        
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
        # Delete lock on failure so it can be retried later
        try:
            s3.delete_object(Bucket=bucket, Key=lock_key)
        except Exception:
            pass
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
            "content_list": content_list,  # Structured content with page info
            "tables": tables,
            "formulas": formulas,
            "page_count": page_count,
            "title": extract_title(md_content if isinstance(md_content, str) else ""),
            "authors": extract_authors_from_text(md_content if isinstance(md_content, str) else ""),
            "year": extract_year_from_text(md_content if isinstance(md_content, str) else ""),
            "abstract": extract_abstract(md_content if isinstance(md_content, str) else ""),
        }
        
    except Exception as e:
        import traceback
        error_msg = f"{e}\n{traceback.format_exc()}"
        print(f"  MinerU failed: {error_msg}")
        return {"success": False, "error": str(e)}


def extract_title(content: str) -> Optional[str]:
    """Extract title from first lines of content."""
    import re
    
    lines = content.strip().split("\n")
    
    # Strategy 1: Look for markdown header
    for line in lines[:10]:
        line = line.strip()
        if line.startswith("# "):
            title = line[2:].strip()
            if 10 < len(title) < 300:
                return title
    
    # Strategy 2: First substantive line that looks like a title
    # (longer than 10 chars, shorter than 300, doesn't look like an abstract/copyright)
    skip_patterns = [
        r'^abstract', r'^introduction', r'^copyright', r'^©',
        r'^doi:', r'^https?://', r'^table of contents', r'^contents',
        r'^\d+\.', r'^vol\.?\s*\d', r'^issue\s*\d',
    ]
    
    for line in lines[:15]:
        line = line.strip().strip("#").strip()
        if not line or len(line) < 10 or len(line) > 300:
            continue
        
        # Skip if matches unwanted patterns
        line_lower = line.lower()
        if any(re.match(p, line_lower) for p in skip_patterns):
            continue
        
        # Likely a title if it's title-cased or all caps
        return line
    
    return None


def extract_authors_from_text(content: str) -> list:
    """Extract author names from content using patterns."""
    import re
    
    authors = []
    lines = content.split("\n")[:30]  # Check first 30 lines
    
    # Common patterns for author sections
    author_patterns = [
        r'^(?:by|authors?|written by)[:\s]+(.+)',
        r'^([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+(?:\s*,\s*[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)*)',
    ]
    
    for line in lines:
        line = line.strip()
        if not line or len(line) < 5:
            continue
        
        # Skip certain lines
        if any(skip in line.lower() for skip in ['abstract', 'introduction', 'university', 'department', '@']):
            continue
        
        # Pattern 1: Explicit "by" or "authors:"
        for pattern in author_patterns[:1]:
            match = re.match(pattern, line, re.IGNORECASE)
            if match:
                author_str = match.group(1)
                # Split by comma or "and"
                parts = re.split(r',\s*|\s+and\s+', author_str)
                for part in parts:
                    part = part.strip()
                    # Validate: looks like a name (2-4 words, no special chars)
                    if 2 <= len(part.split()) <= 5 and not re.search(r'[@\d\(\)]', part):
                        authors.append(part)
                if authors:
                    return authors[:10]  # Limit
    
    return authors


def extract_year_from_text(content: str) -> Optional[int]:
    """Extract publication year from content using patterns."""
    import re
    
    lines = content.split("\n")[:50]  # Check first 50 lines
    text = " ".join(lines)
    
    # Common year patterns in academic documents
    year_patterns = [
        # Explicit date mentions
        r'(?:published|publication date|date)[:\s]+(?:\w+\s+)?(\d{4})',
        r'(?:january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{4})',
        # Copyright notice
        r'©\s*(\d{4})',
        r'copyright\s+(\d{4})',
        # Working paper style: "WP 2023" or "Working Paper No. 123, 2023"
        r'working paper[^,]*,?\s*(\d{4})',
        # Year in parentheses often near beginning
        r'\((\d{4})\)',
        # Standalone 4-digit year (less reliable, use last)
        r'\b(20[0-2]\d|19[89]\d)\b',
    ]
    
    for pattern in year_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            year = int(match.group(1))
            # Validate year is reasonable (1980-2030)
            if 1980 <= year <= 2030:
                return year
    
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

def embed_and_index(content: str, metadata: dict, doc_id: str, content_list: list = None, collection_name: str = None) -> int:
    """
    Chunk content, generate embeddings, and upsert to Qdrant.
    
    Uses named vector 'dense' to match existing collection configuration.
    When content_list is provided (from MinerU), uses page-aware chunking
    to preserve page numbers for each chunk.
    
    Args:
        content: The document content to embed
        metadata: Document metadata (title, authors, year, source, doc_id)
        doc_id: Universal document identifier (used across all systems)
        content_list: Optional MinerU content list with page_idx for page tracking
        collection_name: Optional Qdrant collection name (default: QDRANT_COLLECTION_NAME)
    
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
    
    # Use provided collection name or default
    if collection_name is None:
        collection_name = QDRANT_COLLECTION_NAME
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
    
    # Chunk content - use page-aware chunking if content_list available
    # Using 256 words per chunk for more granular RAG retrieval
    CHUNK_SIZE = 256
    CHUNK_OVERLAP = 50
    
    if content_list:
        print(f"  Using page-aware chunking from {len(content_list)} content items (chunk_size={CHUNK_SIZE})...")
        chunks_with_pages = chunk_content_with_pages(content_list, chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP)
        chunks = [c["text"] for c in chunks_with_pages]
        chunk_pages = chunks_with_pages  # Keep full info for payload
    else:
        print(f"  Using simple chunking (chunk_size={CHUNK_SIZE}, no page info available)")
        chunks = chunk_content(content, chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP)
        chunk_pages = None
    
    if not chunks:
        return 0
    
    # Sanitize chunks to remove invalid Unicode characters (surrogates)
    # that can cause UTF-8 encoding errors with Cohere API
    chunks = [sanitize_text(chunk) for chunk in chunks]
    
    # Delete existing chunks for this document before adding new ones
    # This prevents duplicates if re-processing with different chunking
    try:
        from qdrant_client.models import Filter, FieldCondition, MatchValue
        qdrant.delete(
            collection_name=collection_name,
            points_selector=Filter(
                must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))]
            ),
        )
        print(f"  Cleared existing chunks for doc_id={doc_id}")
    except Exception as e:
        print(f"  Note: Could not clear existing chunks: {e}")
    
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
            chunk_idx = i + j
            # Use deterministic point ID based on doc_id and chunk_index
            # This ensures upsert properly deduplicates on re-runs
            point_id = hashlib.md5(f"{doc_id}:{chunk_idx}".encode()).hexdigest()
            
            # Get page info if available
            page_info = {}
            if chunk_pages and chunk_idx < len(chunk_pages):
                page_data = chunk_pages[chunk_idx]
                page_info = {
                    "page_start": page_data.get("page_start"),
                    "page_end": page_data.get("page_end"),
                    "pages": page_data.get("pages", []),
                }
            
            points.append(
                PointStruct(
                    id=point_id,
                    vector={vector_name: embedding},  # Named vector
                    payload={
                        # Core fields
                        "text": chunk,
                        "doc_id": doc_id,  # Universal document ID
                        "pdf_name": metadata.get("pdf_name", doc_id),  # Backward compatibility
                        "source": metadata.get("source", ""),
                        "chunk_index": chunk_idx,
                        
                        # Page location info (for PDF navigation)
                        **page_info,
                        
                        # Bibliographic metadata
                        "title": metadata.get("title", ""),
                        "authors": metadata.get("authors", []),
                        "year": metadata.get("year"),
                        "doi": metadata.get("doi"),
                        "journal": metadata.get("journal"),
                        "publisher": metadata.get("publisher"),
                        "cited_by_count": metadata.get("cited_by_count"),
                        "is_open_access": metadata.get("is_open_access", False),
                        
                        # Domain-specific metadata
                        "countries": metadata.get("countries", []),
                        "sectors": metadata.get("sectors", []),
                        "study_type": metadata.get("study_type"),
                        "intervention_type": metadata.get("intervention_type"),
                        "sdgs": metadata.get("sdgs", []),
                        "keywords": metadata.get("keywords", []),
                        
                        # Metadata quality tracking
                        "metadata_source": metadata.get("metadata_source", "extraction"),
                        "metadata_confidence": metadata.get("metadata_confidence", 0.0),
                        "needs_review": metadata.get("needs_review", True),
                    },
                )
            )
    
    # Upsert to Qdrant
    qdrant.upsert(collection_name=collection_name, points=points)
    
    return len(points)


def chunk_content(text: str, chunk_size: int = 256, overlap: int = 50) -> list[str]:
    """Split text into overlapping chunks (legacy - no page info)."""
    words = text.split()
    chunks = []
    
    for i in range(0, len(words), chunk_size - overlap):
        chunk = " ".join(words[i:i + chunk_size])
        if chunk.strip():
            chunks.append(chunk)
    
    return chunks


def chunk_content_with_pages(content_list: list, chunk_size: int = 256, overlap: int = 50) -> list[dict]:
    """
    Split structured content into chunks, preserving page numbers.
    
    Args:
        content_list: MinerU content list with page_idx for each item
        chunk_size: Target chunk size in words (default 256 for better RAG precision)
        overlap: Word overlap between chunks
        
    Returns:
        List of dicts with 'text', 'page_start', 'page_end' keys
    """
    if not content_list or not isinstance(content_list, list):
        return []
    
    chunks = []
    current_chunk_words = []
    current_chunk_pages = set()
    
    for item in content_list:
        if not isinstance(item, dict):
            continue
            
        # Get text content
        text = item.get("text", "") or item.get("content", "") or ""
        if not text.strip():
            continue
            
        # Get page number (0-indexed from MinerU)
        page_idx = item.get("page_idx", 0)
        
        words = text.split()
        
        for word in words:
            current_chunk_words.append(word)
            current_chunk_pages.add(page_idx)
            
            # Check if chunk is full
            if len(current_chunk_words) >= chunk_size:
                chunk_text = " ".join(current_chunk_words)
                sorted_pages = sorted(current_chunk_pages)
                chunks.append({
                    "text": chunk_text,
                    "page_start": sorted_pages[0] + 1,  # 1-indexed for display
                    "page_end": sorted_pages[-1] + 1,
                    "pages": [p + 1 for p in sorted_pages],  # All pages in this chunk
                })
                
                # Keep overlap words for next chunk
                current_chunk_words = current_chunk_words[-overlap:] if overlap > 0 else []
                current_chunk_pages = {page_idx}  # Reset but keep current page
    
    # Don't forget the last chunk
    if current_chunk_words:
        chunk_text = " ".join(current_chunk_words)
        if chunk_text.strip():
            sorted_pages = sorted(current_chunk_pages)
            chunks.append({
                "text": chunk_text,
                "page_start": sorted_pages[0] + 1,
                "page_end": sorted_pages[-1] + 1,
                "pages": [p + 1 for p in sorted_pages],
            })
    
    return chunks


# ============================================================================
# Metadata Resolution
# ============================================================================

def resolve_metadata(
    content: str,
    title: Optional[str] = None,
    authors: list = None,
    year: Optional[int] = None,
    pdf_filename: Optional[str] = None,
) -> dict:
    """
    Resolve rich metadata using CrossRef, OpenAlex, and LLM.
    
    Flow:
    1. Extract DOI from content
    2. If DOI found: CrossRef lookup → OpenAlex enrichment
    3. If no DOI: Search by title/author
    4. LLM fills domain-specific gaps (countries, sectors, study_type)
    
    Args:
        content: Extracted text from PDF (markdown)
        title: Title from MinerU extraction
        authors: Authors from MinerU extraction
        year: Year from MinerU extraction
        pdf_filename: Original PDF filename
        
    Returns:
        dict with enriched metadata
    """
    import asyncio
    import os
    import httpx
    import re
    
    # Default metadata
    metadata = {
        "title": title or "Unknown Title",
        "authors": authors or [],
        "year": year,
        "doi": None,
        "item_type": None,  # Will be set from CrossRef/OpenAlex
        "journal": None,
        "volume": None,
        "issue": None,
        "pages": None,
        "publisher": None,
        "abstract": None,
        "cited_by_count": None,
        "is_open_access": False,
        "countries": [],
        "sectors": [],
        "study_type": None,
        "intervention_type": None,
        "sdgs": [],
        "keywords": [],
        "metadata_source": "extraction",
        "metadata_confidence": 0.3,
        "needs_review": True,
        "pdf_name": pdf_filename,
    }
    
    # Step 1: Extract DOI from content
    doi = extract_doi_from_text(content[:10000])
    if doi:
        metadata["doi"] = doi
        print(f"  Found DOI: {doi}")
    
    # Step 2: CrossRef + OpenAlex lookup
    async def lookup_apis():
        async with httpx.AsyncClient(timeout=30.0) as client:
            crossref_data = None
            openalex_data = None
            
            if doi:
                # CrossRef lookup
                try:
                    crossref_url = f"https://api.crossref.org/works/{doi}"
                    resp = await client.get(
                        crossref_url,
                        headers={"User-Agent": "DevChat/2.0 (mailto:dev@example.com)"}
                    )
                    if resp.status_code == 200:
                        crossref_data = resp.json().get("message", {})
                        print(f"  CrossRef: found")
                except Exception as e:
                    print(f"  CrossRef error: {e}")
                
                # OpenAlex lookup by DOI
                try:
                    openalex_url = f"https://api.openalex.org/works/https://doi.org/{doi}"
                    resp = await client.get(
                        openalex_url,
                        headers={"User-Agent": "mailto:dev@example.com"}
                    )
                    if resp.status_code == 200:
                        openalex_data = resp.json()
                        print(f"  OpenAlex: found")
                except Exception as e:
                    print(f"  OpenAlex error: {e}")
            
            elif title and len(title) > 10:
                # Search by title
                try:
                    search_title = title[:200].replace('"', '')
                    openalex_url = f"https://api.openalex.org/works?search={search_title}&per_page=1"
                    resp = await client.get(
                        openalex_url,
                        headers={"User-Agent": "mailto:dev@example.com"}
                    )
                    if resp.status_code == 200:
                        results = resp.json().get("results", [])
                        if results:
                            openalex_data = results[0]
                            print(f"  OpenAlex: found via title search")
                except Exception as e:
                    print(f"  OpenAlex search error: {e}")
            
            return crossref_data, openalex_data
    
    try:
        crossref_data, openalex_data = asyncio.run(lookup_apis())
        
        # Merge CrossRef data
        if crossref_data:
            metadata["title"] = crossref_data.get("title", [metadata["title"]])[0] if crossref_data.get("title") else metadata["title"]
            
            # Extract authors
            cr_authors = crossref_data.get("author", [])
            if cr_authors:
                metadata["authors"] = [
                    f"{a.get('given', '')} {a.get('family', '')}".strip()
                    for a in cr_authors
                ]
            
            # Extract year from published date
            published = crossref_data.get("published-print") or crossref_data.get("published-online") or {}
            date_parts = published.get("date-parts", [[]])[0]
            if date_parts:
                metadata["year"] = date_parts[0]
            
            metadata["journal"] = crossref_data.get("container-title", [None])[0] if crossref_data.get("container-title") else None
            metadata["publisher"] = crossref_data.get("publisher")
            metadata["cited_by_count"] = crossref_data.get("is-referenced-by-count")
            metadata["doi"] = crossref_data.get("DOI") or metadata["doi"]
            
            # Extract volume, issue, pages
            metadata["volume"] = crossref_data.get("volume")
            metadata["issue"] = crossref_data.get("issue")
            metadata["pages"] = crossref_data.get("page")
            
            # Map CrossRef type to our item_type
            # CrossRef types: journal-article, book-chapter, proceedings-article, report, etc.
            crossref_type = crossref_data.get("type", "")
            item_type_map = {
                "journal-article": "journalArticle",
                "book-chapter": "bookSection",
                "book": "book",
                "proceedings-article": "conferencePaper",
                "report": "report",
                "report-series": "report",
                "dissertation": "thesis",
                "posted-content": "preprint",  # preprints
                "dataset": "dataset",
                "monograph": "book",
                "reference-book": "book",
                "edited-book": "book",
            }
            metadata["item_type"] = item_type_map.get(crossref_type, "document")
            
            metadata["metadata_source"] = "crossref"
            metadata["metadata_confidence"] = 0.8
            metadata["needs_review"] = False
        
        # Merge OpenAlex data (enrichment)
        if openalex_data:
            if not crossref_data:
                # Use OpenAlex as primary source
                metadata["title"] = openalex_data.get("title") or metadata["title"]
                
                # Authors
                authorships = openalex_data.get("authorships", [])
                if authorships and not metadata["authors"]:
                    metadata["authors"] = [
                        a.get("author", {}).get("display_name", "")
                        for a in authorships
                    ]
                
                metadata["year"] = openalex_data.get("publication_year") or metadata["year"]
                
                # Journal from primary location
                primary_loc = openalex_data.get("primary_location", {}) or {}
                source = primary_loc.get("source", {}) or {}
                metadata["journal"] = source.get("display_name") or metadata["journal"]
                
                metadata["doi"] = openalex_data.get("doi", "").replace("https://doi.org/", "") if openalex_data.get("doi") else metadata["doi"]
                metadata["cited_by_count"] = openalex_data.get("cited_by_count") or metadata["cited_by_count"]
                
                # Extract biblio info (volume, issue, pages) from OpenAlex
                biblio = openalex_data.get("biblio", {}) or {}
                metadata["volume"] = biblio.get("volume") or metadata.get("volume")
                metadata["issue"] = biblio.get("issue") or metadata.get("issue")
                first_page = biblio.get("first_page")
                last_page = biblio.get("last_page")
                if first_page and last_page:
                    metadata["pages"] = f"{first_page}-{last_page}"
                elif first_page:
                    metadata["pages"] = first_page
                
                # Map OpenAlex type to our item_type
                # OpenAlex types: article, book, book-chapter, dataset, dissertation, etc.
                openalex_type = openalex_data.get("type", "")
                oa_type_map = {
                    "article": "journalArticle",
                    "book": "book",
                    "book-chapter": "bookSection",
                    "dissertation": "thesis",
                    "dataset": "dataset",
                    "preprint": "preprint",
                    "report": "report",
                    "review": "journalArticle",
                    "paratext": "document",
                }
                metadata["item_type"] = oa_type_map.get(openalex_type, "journalArticle")  # Default to journalArticle
                
                metadata["metadata_source"] = "openalex"
                metadata["metadata_confidence"] = 0.7
                metadata["needs_review"] = False
            
            # Always use OpenAlex for enrichment
            oa = openalex_data.get("open_access", {}) or {}
            metadata["is_open_access"] = oa.get("is_oa", False)
            
            # SDGs
            sdgs = openalex_data.get("sustainable_development_goals", [])
            metadata["sdgs"] = [s.get("display_name") for s in sdgs if s.get("display_name")]
            
            # Concepts as keywords
            concepts = openalex_data.get("concepts", [])
            metadata["keywords"] = [
                c.get("display_name") for c in concepts[:10]
                if c.get("display_name") and c.get("score", 0) > 0.3
            ]
            
            # Countries from institutions
            authorships = openalex_data.get("authorships", [])
            countries = set()
            for a in authorships:
                for inst in a.get("institutions", []):
                    if inst.get("country_code"):
                        countries.add(inst["country_code"])
            metadata["countries"] = list(countries)
    
    except Exception as e:
        print(f"  Metadata lookup error: {e}")
    
    # Step 3: LLM gap-filling for domain fields
    if not metadata["sectors"] or not metadata["study_type"]:
        openrouter_key = os.environ.get("OPENROUTER_API_KEY")
        if openrouter_key:
            try:
                llm_result = asyncio.run(
                    llm_extract_domain_fields(
                        title=metadata["title"],
                        abstract=metadata.get("abstract") or content[:3000],
                        api_key=openrouter_key,
                    )
                )
                if llm_result:
                    if not metadata["countries"] and llm_result.get("countries"):
                        metadata["countries"] = llm_result["countries"]
                    if llm_result.get("sectors"):
                        metadata["sectors"] = llm_result["sectors"]
                    if llm_result.get("study_type"):
                        metadata["study_type"] = llm_result["study_type"]
                    if llm_result.get("intervention_type"):
                        metadata["intervention_type"] = llm_result["intervention_type"]
                    print(f"  LLM enrichment: sectors={metadata['sectors']}, study_type={metadata['study_type']}")
            except Exception as e:
                print(f"  LLM enrichment error: {e}")
    
    return metadata


def extract_doi_from_text(text: str) -> Optional[str]:
    """Extract DOI from text using regex patterns."""
    import re
    
    patterns = [
        # Standard DOI format
        r'10\.\d{4,}/[^\s\]>)\'"]+',
        # DOI with URL prefix
        r'(?:doi\.org/|doi:)\s*(10\.\d{4,}/[^\s\]>)\'"]+)',
        # DOI in brackets or parentheses
        r'DOI[:\s]+\[?(10\.\d{4,}/[^\s\]>)\'"]+)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            doi = match.group(1) if match.lastindex else match.group(0)
            # Clean up trailing punctuation
            doi = re.sub(r'[.,;:\'")\]]+$', '', doi)
            return doi
    
    return None


async def llm_extract_domain_fields(
    title: str,
    abstract: str,
    api_key: str,
) -> Optional[dict]:
    """Use LLM to extract domain-specific fields."""
    import httpx
    import json
    
    prompt = f"""Analyze this academic paper about development/impact evaluation and extract domain-specific metadata.

TITLE: {title}

ABSTRACT:
{abstract[:2000]}

Extract the following as JSON:
- countries: List of countries studied or mentioned (use official names)
- sectors: List of sectors (e.g., "education", "health", "agriculture", "finance")
- study_type: One of ["RCT", "quasi-experimental", "systematic-review", "meta-analysis", "observational", "qualitative", "mixed-methods", "other"]
- intervention_type: Type of intervention studied

Return ONLY valid JSON, no explanation."""

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "openai/gpt-4o-mini",
                "messages": [
                    {
                        "role": "system",
                        "content": "You are a metadata extraction assistant. Always respond with valid JSON only."
                    },
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.1,
                "max_tokens": 500,
            },
        )
        
        response.raise_for_status()
        data = response.json()
        content = data["choices"][0]["message"]["content"]
        
        # Parse JSON
        content = content.strip()
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])
        
        return json.loads(content)


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
        info = qdrant.get_collection(QDRANT_COLLECTION_NAME)
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
        if "message" in qdrant_status:
            print(f"   Error: {qdrant_status['message']}")
    
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
# Scheduled Processing (DISABLED - use manual trigger from admin UI)
# ============================================================================

# @app.function(
#     image=base_image,
#     secrets=[r2_secret, qdrant_secret],
#     schedule=modal.Cron("0 * * * *"),  # Every hour
# )
# def scheduled_processing():
#     """
#     Run orchestrator on schedule to pick up new PDFs.
#     
#     Checks Qdrant for a 'processing_paused' flag before running.
#     This allows admins to pause automatic processing without redeploying.
#     """
#     from datetime import datetime
#     
#     print(f"Scheduled run at {datetime.now().isoformat()}")
#     
#     # Check if processing is paused (stored in R2 as a simple flag file)
#     try:
#         import boto3
#         s3 = get_r2_client()
#         bucket = get_bucket_name()
#         
#         try:
#             s3.head_object(Bucket=bucket, Key="system/processing_paused")
#             print("⏸ Processing is PAUSED. Skipping scheduled run.")
#             return {"status": "paused", "queued": 0}
#         except Exception:
#             # Flag doesn't exist = not paused, proceed
#             pass
#     except Exception as e:
#         print(f"Warning: Could not check pause flag: {e}")
#     
#     # Run the orchestrator with default settings
#     result = orchestrate.remote(max_documents=20)  # Limit per scheduled run
#     print(f"Queued {result['queued']} new PDFs")
#     return result


# ============================================================================
# HTTP Web Endpoint (for Railway trigger)
# ============================================================================

@app.function(
    image=base_image,
    secrets=[r2_secret, qdrant_secret, cohere_secret, supabase_secret],
    timeout=600,
)
@modal.fastapi_endpoint(method="POST")
def trigger_processing(request: dict = None) -> dict:
    """
    HTTP endpoint to trigger PDF processing from Railway/Vercel.
    
    POST body (all optional):
        {
            "project_id": "uuid",           # If provided, process for this RAG project
            "force_reprocess": false,
            "check_qdrant": true,
            "max_documents": 0,             # 0 = unlimited
            "api_key": "optional-secret-key"
        }
    
    Returns:
        {
            "success": true,
            "processed": 5,
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
    
    project_id = request.get("project_id")  # RAG project UUID
    force_reprocess = request.get("force_reprocess", False)
    check_qdrant = request.get("check_qdrant", True)
    max_documents = request.get("max_documents", 0)  # 0 = unlimited
    
    # SAFETY: force_reprocess requires explicit confirmation
    if force_reprocess and not request.get("confirm_force", False):
        return {
            "success": False,
            "error": "force_reprocess=true requires confirm_force=true to prevent accidental reprocessing",
            "queued": 0,
            "hint": "Add 'confirm_force': true to your request if you really want to reprocess everything"
        }
    
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
        # If project_id is provided, use project-specific orchestrator
        if project_id:
            print(f"Processing RAG project: {project_id}")
            result = orchestrate_rag.remote(
                project_id=project_id,
                force_reprocess=force_reprocess,
                max_documents=max_documents
            )
            
            return {
                "success": True,
                "project_id": project_id,
                "processed": result.get("processed", 0),
                "failed": result.get("failed", 0),
                "skipped": result.get("skipped", 0),
                "total": result.get("total", 0),
                "message": f"Processed {result.get('processed', 0)} PDFs for project {project_id}.",
            }
        else:
            # Legacy: process global input-pdfs folder
            result = orchestrate.remote(
                force_reprocess=force_reprocess,
                check_qdrant=check_qdrant,
                max_documents=max_documents
            )
            
            return {
                "success": True,
                "queued": result.get("queued", 0),
                "reindexed": result.get("needs_reindex", 0),
                "skipped_limit": result.get("skipped_limit", 0),
                "skipped_errors": result.get("skipped_qdrant_errors", 0),
                "max_documents": max_documents,
                "message": f"Processing triggered. Queued {result.get('queued', 0)} PDFs, re-indexing {result.get('needs_reindex', 0)}.",
            }
        
    except Exception as e:
        print(f"Error in trigger: {e}")
        return {
            "success": False,
            "error": str(e),
            "queued": 0,
        }
