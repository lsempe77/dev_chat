"""
Embedding & Indexing Module

Handles chunking, embedding generation, and Qdrant operations.
Includes Contextual Retrieval (Anthropic's 49% improvement technique).
"""

import asyncio
import hashlib
import os
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Optional, Any

from .config import QDRANT_COLLECTION_NAME
from .utils import sanitize_text


# ============================================================================
# Contextual Retrieval (Anthropic's technique)
# ============================================================================

def generate_contextual_prefix(
    chunk: str,
    full_document: str,
    metadata: dict,
) -> str:
    """
    Generate LLM context prefix for a chunk (Anthropic's Contextual Retrieval).
    
    This prepends each chunk with 2-3 sentences explaining its role in the document,
    improving retrieval accuracy by ~49% according to Anthropic's research.
    
    Uses GPT-4o-mini via OpenRouter for cost efficiency.
    
    Args:
        chunk: The text chunk to contextualize
        full_document: First 8000 chars of the full document
        metadata: Document metadata (title, year, etc.)
        
    Returns:
        Context prefix string (2-3 sentences)
    """
    import httpx
    
    # Build prompt
    prompt = f"""<document>
{full_document[:8000]}
</document>

Here is a chunk from this document:
<chunk>
{chunk}
</chunk>

Provide a short context (2-3 sentences) to situate this chunk within the document.
Include: document type (RCT, qualitative study, review, etc.), section if identifiable, 
and key entities (program name, country, intervention type).
Answer ONLY with the context, nothing else."""

    try:
        response = httpx.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {os.environ.get('OPENROUTER_API_KEY', '')}",
                "Content-Type": "application/json",
            },
            json={
                "model": "openai/gpt-4o-mini",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 150,
                "temperature": 0.3,
            },
            timeout=30.0,
        )
        response.raise_for_status()
        data = response.json()
        context = data["choices"][0]["message"]["content"].strip()
        return context
    except Exception as e:
        print(f"    Warning: Contextual prefix failed: {e}")
        # Fallback to metadata-based prefix
        return _generate_fallback_prefix(metadata)


def _generate_fallback_prefix(metadata: dict) -> str:
    """Generate a simple context prefix from metadata when LLM fails."""
    title = metadata.get("title", "Unknown document")
    year = metadata.get("year", "n.d.")
    study_design = metadata.get("study_design", "")
    countries = metadata.get("countries", [])
    
    parts = [f"From '{title}' ({year})."]
    if study_design:
        parts.append(f"Study design: {study_design}.")
    if countries:
        parts.append(f"Countries: {', '.join(countries[:3])}.")
    
    return " ".join(parts)


def add_contextual_prefixes_batch(
    chunks: List[Dict[str, Any]],
    full_document: str,
    metadata: dict,
    max_workers: int = 5,
) -> List[Dict[str, Any]]:
    """
    Add contextual prefixes to a batch of chunks using thread pool.
    
    Args:
        chunks: List of chunk dicts with 'text' key
        full_document: Full document text for context
        metadata: Document metadata
        max_workers: Number of concurrent LLM calls
        
    Returns:
        Chunks with 'contextual_prefix' and 'text_with_context' added
    """
    print(f"  Adding contextual prefixes to {len(chunks)} chunks...")
    
    def process_chunk(chunk_dict: Dict[str, Any]) -> Dict[str, Any]:
        chunk_text = chunk_dict.get("text", "")
        prefix = generate_contextual_prefix(chunk_text, full_document, metadata)
        return {
            **chunk_dict,
            "contextual_prefix": prefix,
            "text_with_context": f"{prefix}\n\n{chunk_text}",
        }
    
    # Process in batches to avoid overwhelming the API
    enriched_chunks = []
    batch_size = max_workers
    
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i + batch_size]
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            results = list(executor.map(process_chunk, batch))
            enriched_chunks.extend(results)
        
        # Progress indicator
        if (i + batch_size) % 20 == 0 or i + batch_size >= len(chunks):
            print(f"    Enriched {min(i + batch_size, len(chunks))}/{len(chunks)} chunks")
    
    return enriched_chunks


# ============================================================================
# Embedding & Indexing
# ============================================================================

def embed_and_index(
    content: str,
    metadata: dict,
    doc_id: str,
    content_list: Optional[list] = None,
    collection_name: Optional[str] = None,
    enable_contextual: bool = True,
) -> int:
    """
    Chunk content, generate embeddings, and upsert to Qdrant.
    
    Uses named vector 'dense' to match existing collection configuration.
    When content_list is provided (from MinerU), uses page-aware chunking
    to preserve page numbers for each chunk.
    
    With enable_contextual=True, applies Anthropic's Contextual Retrieval:
    - Each chunk gets an LLM-generated context prefix
    - The contextualized text is embedded (improves retrieval by ~49%)
    - Original text is preserved separately for synthesis
    
    Returns:
        Number of chunks indexed
    """
    import cohere
    from qdrant_client import QdrantClient
    from qdrant_client.models import PointStruct, VectorParams, Distance, SparseVector
    
    # Initialize clients
    co = cohere.ClientV2(api_key=os.environ["COHERE_API_KEY"])
    qdrant = QdrantClient(
        url=os.environ["QDRANT_URL"],
        api_key=os.environ["QDRANT_API_KEY"],
    )
    
    # Use provided collection name or default
    if collection_name is None:
        collection_name = QDRANT_COLLECTION_NAME
    vector_name = "dense"
    
    # Ensure collection exists
    _ensure_collection(qdrant, collection_name, vector_name)
    
    # Ensure payload indexes
    _ensure_payload_indexes(qdrant, collection_name)
    
    # Chunk content
    CHUNK_SIZE = 256
    CHUNK_OVERLAP = 50
    
    if content_list:
        print(f"  Using page-aware chunking from {len(content_list)} content items (chunk_size={CHUNK_SIZE})...")
        chunks_with_pages = chunk_content_with_pages(content_list, chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP)
    else:
        print(f"  Using simple chunking (chunk_size={CHUNK_SIZE}, no page info available)")
        simple_chunks = chunk_content(content, chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP)
        # Convert to dict format for consistency
        chunks_with_pages = [{"text": c, "page_start": None, "page_end": None, "pages": []} for c in simple_chunks]
    
    if not chunks_with_pages:
        return 0
    
    # Sanitize chunk texts
    for chunk_dict in chunks_with_pages:
        chunk_dict["text"] = sanitize_text(chunk_dict.get("text", ""))
    
    # Apply Contextual Retrieval if enabled
    if enable_contextual and os.environ.get("OPENROUTER_API_KEY"):
        print(f"  Contextual Retrieval enabled - enriching {len(chunks_with_pages)} chunks...")
        # Use full document text for context (first 8000 chars)
        full_doc_text = content[:8000] if content else ""
        chunks_with_pages = add_contextual_prefixes_batch(
            chunks_with_pages, 
            full_doc_text, 
            metadata,
            max_workers=5,
        )
        # Use contextualized text for embedding
        texts_to_embed = [c.get("text_with_context", c["text"]) for c in chunks_with_pages]
    else:
        if enable_contextual:
            print("  Warning: Contextual Retrieval disabled (no OPENROUTER_API_KEY)")
        texts_to_embed = [c["text"] for c in chunks_with_pages]
    
    # Delete existing chunks for this document
    _delete_existing_chunks(qdrant, collection_name, doc_id)
    
    # Generate embeddings in batches
    batch_size = 96
    points = []
    
    for i in range(0, len(texts_to_embed), batch_size):
        batch_texts = texts_to_embed[i:i + batch_size]
        batch_chunks = chunks_with_pages[i:i + batch_size]
        
        response = co.embed(
            texts=batch_texts,
            model="embed-v4.0",
            input_type="search_document",
            embedding_types=["float", "ubinary"],
        )
        
        dense_embeddings = response.embeddings.float_
        
        # Sparse vectors use the contextualized text too
        sparse_vectors = [_generate_sparse_vector(text) for text in batch_texts]
        
        for j, (chunk_data, embed_text, dense_emb, sparse_vec) in enumerate(
            zip(batch_chunks, batch_texts, dense_embeddings, sparse_vectors)
        ):
            chunk_idx = i + j
            point_id = hashlib.md5(f"{doc_id}:{chunk_idx}".encode()).hexdigest()
            
            # Page info from chunk data
            page_info = {
                "page_start": chunk_data.get("page_start"),
                "page_end": chunk_data.get("page_end"),
                "pages": chunk_data.get("pages", []),
            }
            
            # Build payload - store both original and contextualized text
            payload = {
                "text": chunk_data["text"],  # Original text (for synthesis/display)
                "contextual_prefix": chunk_data.get("contextual_prefix", ""),  # Just the prefix
                "text_with_context": chunk_data.get("text_with_context", chunk_data["text"]),  # Full contextualized
                "doc_id": doc_id,
                "pdf_name": metadata.get("pdf_name", doc_id),
                "source": metadata.get("source", ""),
                "chunk_index": chunk_idx,
                **page_info,
                "title": metadata.get("title", ""),
                "authors": metadata.get("authors", []),
                "year": metadata.get("year"),
                "doi": metadata.get("doi"),
                "journal": metadata.get("journal"),
                "publisher": metadata.get("publisher"),
                "cited_by_count": metadata.get("cited_by_count"),
                "is_open_access": metadata.get("is_open_access", False),
                "countries": metadata.get("countries", []),
                "sectors": metadata.get("sectors", []),
                "study_type": metadata.get("study_type"),
                "study_design": metadata.get("study_design"),
                "intervention_type": metadata.get("intervention_type"),
                "sdgs": metadata.get("sdgs", []),
                "keywords": metadata.get("keywords", []),
                "metadata_source": metadata.get("metadata_source", "extraction"),
                "metadata_confidence": metadata.get("metadata_confidence", 0.0),
                "needs_review": metadata.get("needs_review", True),
            }
            
            points.append(
                PointStruct(
                    id=point_id,
                    vector={
                        vector_name: dense_emb,
                        "sparse": sparse_vec,
                    },
                    payload=payload,
                )
            )
    
    qdrant.upsert(collection_name=collection_name, points=points)
    
    print(f"  Indexed {len(points)} chunks (contextual={enable_contextual})")
    return len(points)


def _ensure_collection(qdrant, collection_name: str, vector_name: str):
    """Ensure Qdrant collection exists with correct config."""
    from qdrant_client.models import VectorParams, Distance, SparseVectorParams
    
    try:
        collection_info = qdrant.get_collection(collection_name)
        vectors_config = collection_info.config.params.vectors
        
        needs_recreate = False
        if isinstance(vectors_config, dict):
            if vector_name in vectors_config:
                if vectors_config[vector_name].size != 1536:
                    needs_recreate = True
                    print(f"  Collection has wrong dimensions")
            else:
                needs_recreate = True
                print(f"  Collection missing vector '{vector_name}'")
        else:
            needs_recreate = True
            print("  Collection has unnamed vectors, need named 'dense'")
        
        if needs_recreate:
            count = qdrant.count(collection_name).count
            if count > 0:
                print(f"  WARNING: Collection has {count} points, will be deleted!")
            
            qdrant.delete_collection(collection_name)
            print(f"  Deleted old collection")
            raise Exception("Recreate collection")
            
    except Exception:
        print(f"  Creating collection with Cohere 1536-dim dense + sparse vectors...")
        qdrant.create_collection(
            collection_name=collection_name,
            vectors_config={
                vector_name: VectorParams(size=1536, distance=Distance.COSINE)
            },
            sparse_vectors_config={
                "sparse": SparseVectorParams()
            },
        )
        print(f"  Created collection '{collection_name}' with dense + sparse vectors")


def _ensure_payload_indexes(qdrant, collection_name: str):
    """Ensure payload indexes exist for efficient filtering."""
    from qdrant_client.models import PayloadSchemaType
    
    try:
        for field in ["doc_id", "pdf_name"]:
            try:
                qdrant.create_payload_index(
                    collection_name=collection_name,
                    field_name=field,
                    field_schema=PayloadSchemaType.KEYWORD,
                )
                print(f"  Created payload index on '{field}'")
            except Exception:
                pass
    except Exception as e:
        print(f"  Note: Could not create indexes: {e}")


def _delete_existing_chunks(qdrant, collection_name: str, doc_id: str):
    """Delete existing chunks for a document."""
    from qdrant_client.models import Filter, FieldCondition, MatchValue
    
    try:
        qdrant.delete(
            collection_name=collection_name,
            points_selector=Filter(
                must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))]
            ),
        )
        print(f"  Cleared existing chunks for doc_id={doc_id}")
    except Exception as e:
        print(f"  Note: Could not clear existing chunks: {e}")


# ============================================================================
# Chunking
# ============================================================================

def chunk_content(text: str, chunk_size: int = 256, overlap: int = 50) -> List[str]:
    """Split text into overlapping chunks (legacy - no page info)."""
    words = text.split()
    chunks = []
    
    for i in range(0, len(words), chunk_size - overlap):
        chunk = " ".join(words[i:i + chunk_size])
        if chunk.strip():
            chunks.append(chunk)
    
    return chunks


def chunk_content_with_pages(
    content_list: list,
    chunk_size: int = 256,
    overlap: int = 50,
) -> List[Dict[str, Any]]:
    """
    Split structured content into chunks, preserving page numbers.
    
    Args:
        content_list: MinerU content list with page_idx for each item
        chunk_size: Target chunk size in words
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
            
        text = item.get("text", "") or item.get("content", "") or ""
        if not text.strip():
            continue
            
        page_idx = item.get("page_idx", 0)
        words = text.split()
        
        for word in words:
            current_chunk_words.append(word)
            current_chunk_pages.add(page_idx)
            
            if len(current_chunk_words) >= chunk_size:
                chunk_text = " ".join(current_chunk_words)
                sorted_pages = sorted(current_chunk_pages)
                chunks.append({
                    "text": chunk_text,
                    "page_start": sorted_pages[0] + 1,
                    "page_end": sorted_pages[-1] + 1,
                    "pages": [p + 1 for p in sorted_pages],
                })
                
                current_chunk_words = current_chunk_words[-overlap:] if overlap > 0 else []
                current_chunk_pages = {page_idx}
    
    # Last chunk
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
# Sparse Vectors
# ============================================================================

def _generate_sparse_vector(text: str):
    """Generate a BM25-style sparse vector for text."""
    from qdrant_client.models import SparseVector
    
    text_clean = re.sub(r'[^\w\s]', ' ', text.lower())
    words = text_clean.split()
    
    stopwords = {
        'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
        'of', 'with', 'by', 'from', 'as', 'is', 'was', 'are', 'were', 'been',
        'be', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
        'could', 'should', 'may', 'might', 'must', 'shall', 'can', 'need',
        'this', 'that', 'these', 'those', 'it', 'its', 'they', 'them', 'their',
        'we', 'our', 'you', 'your', 'he', 'she', 'his', 'her', 'i', 'me', 'my',
        'which', 'who', 'whom', 'what', 'where', 'when', 'why', 'how',
        'all', 'each', 'every', 'both', 'few', 'more', 'most', 'other',
        'some', 'such', 'no', 'nor', 'not', 'only', 'own', 'same', 'so',
        'than', 'too', 'very', 'just', 'also', 'now', 'here', 'there',
    }
    
    words = [w for w in words if w not in stopwords and len(w) > 2]
    
    if not words:
        return SparseVector(indices=[], values=[])
    
    term_counts = Counter(words)
    
    # Use a dict to handle hash collisions - aggregate values for same index
    index_values = {}
    for term, count in term_counts.items():
        term_idx = abs(hash(term)) % 1000000
        # If collision, add the counts together
        index_values[term_idx] = index_values.get(term_idx, 0.0) + float(count)
    
    # Convert to sorted lists (Qdrant requires unique indices)
    indices = sorted(index_values.keys())
    values = [index_values[idx] for idx in indices]
    
    return SparseVector(indices=indices, values=values)


# ============================================================================
# Qdrant Index Management
# ============================================================================

def ensure_qdrant_indexes():
    """Ensure Qdrant has proper indexes - called at processing start."""
    # This is now handled in _ensure_payload_indexes during embed_and_index
    pass
