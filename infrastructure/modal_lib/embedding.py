"""
Embedding & Indexing Module

Handles chunking, embedding generation, and Qdrant operations.
Includes Contextual Retrieval (Anthropic's 49% improvement technique).
Includes Embedding Cache (50-80% cost reduction on re-indexing).
"""

import asyncio
import hashlib
import json
import os
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List, Dict, Optional, Any

from .config import QDRANT_COLLECTION_NAME
from .utils import sanitize_text


# ============================================================================
# Embedding Cache (Modal-compatible, file-based)
# ============================================================================

class ModalEmbeddingCache:
    """
    Simple file-based embedding cache for Modal environment.
    
    Uses content hash as key to enable cache hits across re-indexing.
    Cache is stored in Modal's volume for persistence.
    """
    
    def __init__(self, cache_dir: str = "/cache/embeddings"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._memory_cache: Dict[str, List[float]] = {}
        self.hits = 0
        self.misses = 0
    
    def _hash_key(self, text: str, model_name: str) -> str:
        """Generate cache key from text content and model."""
        content = f"{model_name}:{text}"
        return hashlib.md5(content.encode()).hexdigest()
    
    def _get_cache_file(self, key: str) -> Path:
        """Get cache file path (sharded by first 2 chars)."""
        return self.cache_dir / f"emb_{key[:2]}.json"
    
    def get_batch(
        self, 
        texts: List[str], 
        model_name: str,
    ) -> tuple[List[Optional[List[float]]], List[int]]:
        """
        Check cache for batch of texts.
        
        Returns:
            Tuple of (cached_embeddings, indices_to_embed)
            cached_embeddings[i] is None if not in cache
        """
        results = [None] * len(texts)
        indices_to_embed = []
        
        # Group by cache file for efficiency
        file_keys: Dict[Path, Dict[str, int]] = {}  # file -> {key: index}
        
        for i, text in enumerate(texts):
            key = self._hash_key(text, model_name)
            
            # Check memory cache first
            if key in self._memory_cache:
                results[i] = self._memory_cache[key]
                self.hits += 1
                continue
            
            cache_file = self._get_cache_file(key)
            if cache_file not in file_keys:
                file_keys[cache_file] = {}
            file_keys[cache_file][key] = i
        
        # Load cache files and check
        for cache_file, keys in file_keys.items():
            if cache_file.exists():
                try:
                    with open(cache_file, 'r') as f:
                        cache_data = json.load(f)
                    
                    for key, idx in keys.items():
                        if key in cache_data:
                            embedding = cache_data[key]
                            results[idx] = embedding
                            self._memory_cache[key] = embedding
                            self.hits += 1
                        else:
                            indices_to_embed.append(idx)
                            self.misses += 1
                except (json.JSONDecodeError, IOError):
                    # Cache file corrupted - mark all as misses
                    indices_to_embed.extend(keys.values())
                    self.misses += len(keys)
            else:
                # File doesn't exist - all misses
                indices_to_embed.extend(keys.values())
                self.misses += len(keys)
        
        return results, indices_to_embed
    
    def set_batch(
        self, 
        texts: List[str], 
        embeddings: List[List[float]], 
        model_name: str,
    ):
        """Store embeddings in cache."""
        # Group by cache file
        file_updates: Dict[Path, Dict[str, List[float]]] = {}
        
        for text, embedding in zip(texts, embeddings):
            key = self._hash_key(text, model_name)
            self._memory_cache[key] = embedding
            
            cache_file = self._get_cache_file(key)
            if cache_file not in file_updates:
                # Load existing data
                if cache_file.exists():
                    try:
                        with open(cache_file, 'r') as f:
                            file_updates[cache_file] = json.load(f)
                    except (json.JSONDecodeError, IOError):
                        file_updates[cache_file] = {}
                else:
                    file_updates[cache_file] = {}
            
            file_updates[cache_file][key] = embedding
        
        # Write updated files
        for cache_file, cache_data in file_updates.items():
            try:
                with open(cache_file, 'w') as f:
                    json.dump(cache_data, f)
            except IOError as e:
                print(f"  Warning: Failed to save cache: {e}")
    
    def get_stats(self) -> str:
        """Get cache statistics."""
        total = self.hits + self.misses
        hit_rate = self.hits / total if total > 0 else 0
        return f"Cache: {self.hits}/{total} hits ({hit_rate:.1%})"


# Global cache instance for Modal
_modal_cache: Optional[ModalEmbeddingCache] = None

def get_modal_cache() -> ModalEmbeddingCache:
    """Get or create Modal embedding cache."""
    global _modal_cache
    if _modal_cache is None:
        # Try Modal volume first, fall back to /tmp
        cache_dir = "/cache/embeddings" if os.path.exists("/cache") else "/tmp/embeddings"
        _modal_cache = ModalEmbeddingCache(cache_dir=cache_dir)
    return _modal_cache


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
You MUST include:
1. Document type (RCT, quasi-experimental study, qualitative study, review, working paper, etc.)
2. The SPECIFIC SECTION this chunk is from (e.g., Introduction, Literature Review, Methodology, Data, Results, Discussion, Conclusion, References, Appendix, Tables)
3. Key entities (program name, country, intervention type)

Example format: "This chunk is from the [Results/Methodology/etc.] section of a [study type] evaluating [program] in [country]. It discusses [specific topic]."

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
        # Fallback to metadata-based prefix with section estimation
        return _generate_fallback_prefix(metadata, chunk)


def _generate_fallback_prefix(metadata: dict, chunk_text: str = "") -> str:
    """Generate a simple context prefix from metadata when LLM fails."""
    title = metadata.get("title", "Unknown document")
    year = metadata.get("year", "n.d.")
    study_design = metadata.get("study_design", "")
    countries = metadata.get("countries", [])
    
    # Try to estimate section from chunk content
    section = _estimate_section(chunk_text)
    
    parts = []
    if section:
        parts.append(f"This chunk is from the {section} section of")
    else:
        parts.append("From")
    
    parts[0] += f" '{title}' ({year})."
    
    if study_design:
        parts.append(f"Study design: {study_design}.")
    if countries:
        parts.append(f"Countries: {', '.join(countries[:3])}.")
    
    return " ".join(parts)


def _estimate_section(text: str) -> str:
    """Estimate document section from text content using keyword matching."""
    text_lower = text.lower()
    
    # Section indicators (order matters - check more specific first)
    section_keywords = {
        "References": ["et al.", "journal of", "doi:", "vol.", "pp.", "isbn", "working paper"],
        "Methodology": ["randomized", "sample size", "regression", "data collection", "survey", "questionnaire", "control group", "treatment group"],
        "Results": ["table ", "figure ", "statistically significant", "coefficient", "p-value", "standard error", "percentage point", "increased by", "decreased by"],
        "Introduction": ["this paper", "this study", "we examine", "we analyze", "literature has", "previous research"],
        "Discussion": ["findings suggest", "results indicate", "implications", "limitation", "future research"],
        "Conclusion": ["in conclusion", "to conclude", "in summary", "we find that", "our findings"],
        "Appendix": ["appendix", "supplementary", "robustness check"],
    }
    
    for section, keywords in section_keywords.items():
        matches = sum(1 for kw in keywords if kw in text_lower)
        if matches >= 2:
            return section
    
    return ""


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
    enable_parent_child: bool = True,
    quantization_type: str = "binary",
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
    
    With enable_parent_child=True, applies Parent-Child Chunking (PaperQA2):
    - Child chunks (~200 words) are embedded for precise search
    - Parent chunks (~1000 words) provide context for synthesis
    - When a child matches, the full parent is returned to the LLM
    
    Args:
        quantization_type: 'binary' (32x compression), 'scalar' (int8, 4x), or 'none'
    
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
    
    # Ensure collection exists with specified quantization
    _ensure_collection(qdrant, collection_name, vector_name, quantization_type)
    
    # Ensure payload indexes
    _ensure_payload_indexes(qdrant, collection_name)
    
    # Chunk content - choose strategy
    if content_list and enable_parent_child:
        # Parent-Child Chunking (PaperQA2 approach)
        print(f"  Using Parent-Child chunking from {len(content_list)} content items...")
        chunks_with_pages = chunk_content_parent_child(
            content_list,
            child_size=200,
            parent_size=1000,
            child_overlap=40,
        )
    elif content_list:
        # Original page-aware chunking
        CHUNK_SIZE = 256
        CHUNK_OVERLAP = 50
        print(f"  Using page-aware chunking from {len(content_list)} content items (chunk_size={CHUNK_SIZE})...")
        chunks_with_pages = chunk_content_with_pages(content_list, chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP)
    else:
        # Legacy simple chunking
        CHUNK_SIZE = 256
        CHUNK_OVERLAP = 50
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
    
    # Initialize embedding cache
    cache = get_modal_cache()
    enable_cache = os.environ.get("EMBEDDING_CACHE_ENABLED", "true").lower() == "true"
    
    # Check cache for all texts first
    model_name = "embed-v4.0"
    if enable_cache:
        cached_embeddings, indices_to_embed = cache.get_batch(texts_to_embed, model_name)
        texts_needing_embedding = [texts_to_embed[i] for i in indices_to_embed]
        print(f"  Embedding cache: {len(texts_to_embed) - len(indices_to_embed)}/{len(texts_to_embed)} cached")
    else:
        cached_embeddings = [None] * len(texts_to_embed)
        indices_to_embed = list(range(len(texts_to_embed)))
        texts_needing_embedding = texts_to_embed
    
    # Generate embeddings only for uncached texts
    batch_size = 96
    new_embeddings = []
    
    if texts_needing_embedding:
        for i in range(0, len(texts_needing_embedding), batch_size):
            batch_texts = texts_needing_embedding[i:i + batch_size]
            
            response = co.embed(
                texts=batch_texts,
                model=model_name,
                input_type="search_document",
                embedding_types=["float"],
            )
            
            new_embeddings.extend(response.embeddings.float_)
        
        # Store new embeddings in cache
        if enable_cache:
            cache.set_batch(texts_needing_embedding, new_embeddings, model_name)
    
    # Merge cached and new embeddings
    all_embeddings = list(cached_embeddings)  # Start with cached (with Nones)
    new_emb_idx = 0
    for idx in indices_to_embed:
        all_embeddings[idx] = new_embeddings[new_emb_idx]
        new_emb_idx += 1
    
    # Build points with embeddings
    points = []
    for chunk_idx, (chunk_data, embed_text, dense_emb) in enumerate(
        zip(chunks_with_pages, texts_to_embed, all_embeddings)
    ):
        point_id = hashlib.md5(f"{doc_id}:{chunk_idx}".encode()).hexdigest()
        sparse_vec = _generate_sparse_vector(embed_text)
        
        # Page info from chunk data
        page_info = {
            "page_start": chunk_data.get("page_start"),
            "page_end": chunk_data.get("page_end"),
            "pages": chunk_data.get("pages", []),
        }
        
        # Build payload - store both original and contextualized text
        # With parent-child chunking, also store parent_text and parent_id
        payload = {
            "text": chunk_data["text"],  # Child text (for display/citation)
            "parent_text": chunk_data.get("parent_text", chunk_data["text"]),  # Parent text (for synthesis)
            "parent_id": chunk_data.get("parent_id", ""),  # Parent ID (for deduplication)
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
        
        # Qdrant automatically handles binary quantization of dense vectors
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
    
    # Print cache stats
    if enable_cache:
        print(f"  {cache.get_stats()}")
    
    print(f"  Indexed {len(points)} chunks (contextual={enable_contextual}, cache={enable_cache})")
    return len(points)


def _ensure_collection(qdrant, collection_name: str, vector_name: str, quantization_type: str = "binary"):
    """
    Ensure Qdrant collection exists with correct config including quantization and HNSW tuning.
    
    Args:
        qdrant: QdrantClient instance
        collection_name: Name of the collection
        vector_name: Name of the dense vector field (e.g., 'dense')
        quantization_type: Quantization strategy - 'binary' (32x compression), 
                          'scalar' (4x compression, int8), or 'none'
    """
    from qdrant_client.models import (
        VectorParams, 
        Distance, 
        SparseVectorParams, 
        BinaryQuantization, 
        BinaryQuantizationConfig,
        ScalarQuantization,
        ScalarQuantizationConfig,
        ScalarType,
        HnswConfigDiff,
    )
    
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
            
            # Check if quantization is enabled (any type)
            quant_config = collection_info.config.quantization_config
            if quant_config is None and quantization_type != "none":
                needs_recreate = True
                print(f"  Collection missing quantization config (expected: {quantization_type})")
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
            
    except Exception as e:
        # Build quantization config based on type
        quant_config = None
        quant_name = "no quantization"
        
        if quantization_type == "binary":
            # Binary: ~32x compression, fastest, best for Cohere embed-v4
            quant_config = BinaryQuantization(
                binary=BinaryQuantizationConfig(
                    always_ram=True,  # Keep quantized vectors in RAM for speed
                )
            )
            quant_name = "binary quantization (32x compression)"
        elif quantization_type == "scalar":
            # Scalar: ~4x compression, int8 quantization, better precision than binary
            quant_config = ScalarQuantization(
                scalar=ScalarQuantizationConfig(
                    type=ScalarType.INT8,
                    quantile=0.99,  # Calibration quantile for better precision
                    always_ram=True,
                )
            )
            quant_name = "scalar quantization (int8, 4x compression)"
        # else: None = no quantization
        
        print(f"  Creating collection with Cohere 1536-dim dense + sparse + {quant_name} + HNSW tuning...")
        qdrant.create_collection(
            collection_name=collection_name,
            vectors_config={
                vector_name: VectorParams(
                    size=1536, 
                    distance=Distance.COSINE,
                    # HNSW tuning for better recall
                    # m=16: Number of edges per node (default 16, higher = better recall, more memory)
                    # ef_construct=200: Search depth during indexing (default 100, higher = better recall)
                    hnsw_config=HnswConfigDiff(
                        m=16,
                        ef_construct=200,
                    ),
                ),
            },
            sparse_vectors_config={
                "sparse": SparseVectorParams()
            },
            quantization_config=quant_config,
        )
        print(f"  Created collection '{collection_name}' with dense + sparse + {quant_name} + HNSW(m=16, ef_construct=200)")


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


def chunk_content_parent_child(
    content_list: list,
    child_size: int = 200,
    parent_size: int = 1000,
    child_overlap: int = 40,
) -> List[Dict[str, Any]]:
    """
    Create parent-child chunks for improved retrieval (PaperQA2 technique).
    
    - Child chunks (~200 words) are embedded for precise search
    - Parent chunks (~1000 words) provide context for synthesis
    - When a child matches, the full parent is returned to the LLM
    
    Args:
        content_list: MinerU content list with page_idx for each item
        child_size: Target child chunk size in words (embedded)
        parent_size: Target parent chunk size in words (for synthesis)
        child_overlap: Word overlap between child chunks
        
    Returns:
        List of child chunk dicts with 'text', 'parent_text', 'parent_id', page info
    """
    import uuid
    
    if not content_list or not isinstance(content_list, list):
        return []
    
    # Step 1: Flatten content into word stream with page tracking
    word_stream = []  # [(word, page_idx), ...]
    
    for item in content_list:
        if not isinstance(item, dict):
            continue
        text = item.get("text", "") or item.get("content", "") or ""
        if not text.strip():
            continue
        page_idx = item.get("page_idx", 0)
        for word in text.split():
            word_stream.append((word, page_idx))
    
    if not word_stream:
        return []
    
    # Step 2: Create parent chunks
    parents = []
    for i in range(0, len(word_stream), parent_size):
        parent_words_pages = word_stream[i:i + parent_size]
        if not parent_words_pages:
            continue
            
        parent_text = " ".join([w for w, _ in parent_words_pages])
        parent_pages = sorted(set([p for _, p in parent_words_pages]))
        
        parents.append({
            "parent_id": str(uuid.uuid4())[:8],
            "text": parent_text,
            "page_start": parent_pages[0] + 1,
            "page_end": parent_pages[-1] + 1,
            "pages": [p + 1 for p in parent_pages],
            "word_start": i,
            "word_end": min(i + parent_size, len(word_stream)),
        })
    
    # Step 3: Create child chunks within each parent
    children = []
    
    for parent in parents:
        parent_word_stream = word_stream[parent["word_start"]:parent["word_end"]]
        
        # Create overlapping children within this parent
        step = child_size - child_overlap
        for j in range(0, len(parent_word_stream), step):
            child_words_pages = parent_word_stream[j:j + child_size]
            if not child_words_pages:
                continue
                
            child_text = " ".join([w for w, _ in child_words_pages])
            child_pages = sorted(set([p for _, p in child_words_pages]))
            
            if child_text.strip():
                children.append({
                    "text": child_text,  # Child text (embedded)
                    "parent_text": parent["text"],  # Full parent (for synthesis)
                    "parent_id": parent["parent_id"],
                    "page_start": child_pages[0] + 1,
                    "page_end": child_pages[-1] + 1,
                    "pages": [p + 1 for p in child_pages],
                })
    
    print(f"  Parent-Child chunking: {len(parents)} parents → {len(children)} children")
    return children


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
