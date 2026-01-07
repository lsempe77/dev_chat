"""
Utility Functions

Common helper functions used across the Modal pipeline.
"""

import os
import re
from typing import Any


# ============================================================================
# R2/S3 Helpers
# ============================================================================

def get_r2_client():
    """Create S3 client configured for Cloudflare R2."""
    import boto3
    
    return boto3.client(
        "s3",
        endpoint_url=f"https://{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )


def get_bucket_name() -> str:
    """Get R2 bucket name from environment."""
    return os.environ.get("R2_BUCKET_NAME", "devchat-pdfs")


# ============================================================================
# Text Sanitization
# ============================================================================

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


def sanitize_dict(obj: Any) -> Any:
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
# Sync Helpers
# ============================================================================

def sync_to_postgres(doc_id: str, metadata: dict, chunk_count: int, page_count: int) -> bool:
    """
    Sync document to PostgreSQL via Supabase.
    
    Used by the legacy process_pdf function.
    """
    from datetime import datetime
    
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_SERVICE_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    
    if not supabase_url or not supabase_key:
        print("  ⚠ Supabase not configured, skipping PostgreSQL sync")
        return False
    
    try:
        from supabase import create_client
        client = create_client(supabase_url, supabase_key)
        
        # Upsert to documents table
        data = {
            "doc_id": doc_id,
            "title": metadata.get("title"),
            "authors": metadata.get("authors", []),
            "year": metadata.get("year"),
            "doi": metadata.get("doi"),
            "journal": metadata.get("journal"),
            "publisher": metadata.get("publisher"),
            "countries": metadata.get("countries", []),
            "sectors": metadata.get("sectors", []),
            "study_type": metadata.get("study_type"),
            "chunk_count": chunk_count,
            "page_count": page_count,
            "metadata_source": metadata.get("metadata_source"),
            "metadata_confidence": metadata.get("metadata_confidence"),
            "needs_review": metadata.get("needs_review", True),
            "updated_at": datetime.now().isoformat(),
        }
        
        client.table("processed_documents").upsert(
            data,
            on_conflict="doc_id"
        ).execute()
        
        print(f"  ✓ Synced to PostgreSQL")
        return True
        
    except Exception as e:
        print(f"  ⚠ PostgreSQL sync error: {e}")
        return False


def ensure_qdrant_indexes():
    """Ensure Qdrant has proper indexes for efficient queries."""
    # This is called from processing functions
    # Left as a stub - actual implementation in embedding.py
    pass
