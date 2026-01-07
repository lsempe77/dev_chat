"""
Modal MinerU Library

Modular components for PDF processing pipeline.

Modules:
- config: Modal app, image, secrets, volumes
- utils: Helper functions (R2 client, sanitization)
- extraction: MinerU PDF extraction
- metadata: CrossRef, OpenAlex, LLM enrichment
- embedding: Chunking, embedding, Qdrant operations
- processing: PDF processing functions (GPU)
- orchestration: Batch processing orchestration
"""

from .config import (
    app,
    base_image,
    model_cache,
    r2_secret,
    qdrant_secret,
    cohere_secret,
    openrouter_secret,
    supabase_secret,
    QDRANT_COLLECTION_NAME,
)

from .utils import (
    get_r2_client,
    get_bucket_name,
    sanitize_text,
    sanitize_dict,
)

from .extraction import (
    run_mineru,
    post_process_content,
    extract_title,
    extract_abstract,
)

from .metadata import (
    resolve_metadata,
    classify_study_design_llm,
)

from .embedding import (
    embed_and_index,
    chunk_content,
    chunk_content_with_pages,
)

from .processing import (
    process_pdf,
    process_pdf_rag,
    check_qdrant_indexed,
    delete_qdrant_chunks,
    ensure_qdrant_indexes,
    sync_to_postgres,
    sync_to_supabase_rag,
)

from .orchestration import (
    orchestrate,
    orchestrate_rag,
    list_pdfs,
    check_qdrant_status,
)

__all__ = [
    # Config
    "app",
    "base_image",
    "model_cache",
    "r2_secret",
    "qdrant_secret",
    "cohere_secret",
    "openrouter_secret",
    "supabase_secret",
    "QDRANT_COLLECTION_NAME",
    # Utils
    "get_r2_client",
    "get_bucket_name",
    "sanitize_text",
    "sanitize_dict",
    # Extraction
    "run_mineru",
    "post_process_content",
    "extract_title",
    "extract_abstract",
    # Metadata
    "resolve_metadata",
    "classify_study_design_llm",
    # Embedding
    "embed_and_index",
    "chunk_content",
    "chunk_content_with_pages",
    # Processing
    "process_pdf",
    "process_pdf_rag",
    "check_qdrant_indexed",
    "delete_qdrant_chunks",
    "ensure_qdrant_indexes",
    "sync_to_postgres",
    "sync_to_supabase_rag",
    # Orchestration
    "orchestrate",
    "orchestrate_rag",
    "list_pdfs",
    "check_qdrant_status",
]
