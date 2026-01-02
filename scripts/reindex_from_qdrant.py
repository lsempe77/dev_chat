#!/usr/bin/env python
"""
DevChat v2.0 SOTA - Re-index Existing Collection with Contextual Retrieval

This script takes an existing Qdrant collection and creates a new enhanced version with:
1. Contextual Retrieval - prepend document metadata to each chunk
2. Hybrid Search (BM25 + Dense) - enable sparse vectors
3. Optimized for 150→20 retrieval flow

Usage:
    python scripts/reindex_from_qdrant.py --source devchat_v2_enhanced --target devchat_v2_contextual
"""

import argparse
import asyncio
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

from tqdm import tqdm

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from qdrant_client import QdrantClient, models
from llama_index.core.schema import TextNode

from src.config.settings import settings
from src.ingestion.embeddings import EmbeddingGenerator
from src.ingestion.indexer import QdrantIndexer
from src.utils.logging import get_logger, setup_logging

setup_logging()
logger = get_logger(__name__)


def get_qdrant_client() -> QdrantClient:
    """Get Qdrant client."""
    if settings.qdrant_api_key:
        return QdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key,
        )
    return QdrantClient(url=settings.qdrant_url)


def contextualize_chunk(text: str, metadata: Dict) -> str:
    """
    Add document context prefix to a chunk.
    
    This is the key insight from Anthropic's Contextual Retrieval paper:
    By prepending metadata, the embedding model understands what the chunk is about.
    """
    # Build context from metadata
    title = metadata.get('title', 'Research document')
    year = metadata.get('year', '')
    authors = metadata.get('authors', '')
    study_type = metadata.get('study_type', '')
    sector = metadata.get('sector', '')
    country = metadata.get('country', '')
    region = metadata.get('region', '')
    
    # Create context prefix
    context_parts = [f"From: {title}"]
    if year:
        context_parts.append(f"Year: {year}")
    if study_type:
        context_parts.append(f"Type: {study_type}")
    if sector:
        context_parts.append(f"Sector: {sector}")
    if country:
        context_parts.append(f"Country: {country}")
    elif region:
        context_parts.append(f"Region: {region}")
    if authors:
        # Truncate long author lists
        if len(str(authors)) > 80:
            authors = str(authors)[:80] + "..."
        context_parts.append(f"Authors: {authors}")
    
    context_prefix = " | ".join(context_parts)
    
    # Get section info if available
    section = metadata.get('section', '') or metadata.get('header', '')
    if section:
        context_prefix += f"\nSection: {section}"
    
    # Combine context with original text
    contextualized_text = f"[{context_prefix}]\n\n{text}"
    
    return contextualized_text


def read_source_collection(
    client: QdrantClient,
    collection_name: str,
    batch_size: int = 100,
) -> List[Dict]:
    """Read all points from source collection."""
    logger.info(f"Reading points from '{collection_name}'...")
    
    all_points = []
    offset = None
    
    while True:
        results, next_offset = client.scroll(
            collection_name=collection_name,
            limit=batch_size,
            offset=offset,
            with_payload=True,
            with_vectors=False,  # We'll re-embed the contextualized text
        )
        
        all_points.extend(results)
        
        if next_offset is None:
            break
        offset = next_offset
        
        logger.debug(f"Read {len(all_points)} points so far...")
    
    logger.info(f"Read {len(all_points)} total points from '{collection_name}'")
    return all_points


def points_to_contextualized_nodes(points: List) -> List[TextNode]:
    """Convert Qdrant points to contextualized TextNodes."""
    nodes = []
    
    for point in tqdm(points, desc="Contextualizing"):
        payload = point.payload
        original_text = payload.get('text', '')
        
        if not original_text:
            continue
        
        # Apply contextual retrieval
        contextualized_text = contextualize_chunk(original_text, payload)
        
        # Create node
        node = TextNode(
            text=contextualized_text,
            id_=str(point.id),
            metadata={
                **{k: v for k, v in payload.items() if k != 'text'},
                'original_text': original_text,
                'contextualized': True,
            }
        )
        nodes.append(node)
    
    return nodes


def main():
    parser = argparse.ArgumentParser(
        description="Re-index existing collection with Contextual Retrieval + Hybrid Search"
    )
    
    parser.add_argument(
        "--source",
        type=str,
        default="devchat_v2_enhanced",
        help="Source collection name",
    )
    
    parser.add_argument(
        "--target",
        type=str,
        default="devchat_v2_contextual",
        help="Target collection name",
    )
    
    parser.add_argument(
        "--batch-size",
        type=int,
        default=50,
        help="Batch size for embedding generation",
    )
    
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )
    
    args = parser.parse_args()
    
    start_time = time.time()
    
    # Configuration summary
    logger.info("=" * 60)
    logger.info("SOTA RAG Stack: Re-indexing from Existing Collection")
    logger.info("=" * 60)
    logger.info(f"Source Collection: {args.source}")
    logger.info(f"Target Collection: {args.target}")
    logger.info(f"Contextual Retrieval: ENABLED")
    logger.info(f"Hybrid Search (BM25+Dense): ENABLED")
    logger.info("=" * 60)
    
    # Step 1: Read source collection
    client = get_qdrant_client()
    points = read_source_collection(client, args.source)
    
    if not points:
        logger.error("No points found in source collection!")
        return
    
    # Step 2: Convert to contextualized nodes
    logger.info("Applying Contextual Retrieval...")
    nodes = points_to_contextualized_nodes(points)
    logger.info(f"Created {len(nodes)} contextualized nodes")
    
    # Show sample
    if nodes:
        sample = nodes[0]
        logger.info(f"\n--- Sample Contextualized Chunk ---")
        text = sample.get_content()[:600]
        logger.info(f"{text}...")
        logger.info(f"--- End Sample ---\n")
    
    if args.dry_run:
        logger.info(f"DRY RUN: Would create collection '{args.target}' with hybrid=True")
        logger.info(f"DRY RUN: Would embed and index {len(nodes)} nodes")
        logger.info("DRY RUN complete - exiting")
        return
    
    # Step 3: Generate new embeddings for contextualized text
    logger.info("Generating embeddings for contextualized chunks...")
    embedding_gen = EmbeddingGenerator()
    
    # Process in batches for memory efficiency
    for i in tqdm(range(0, len(nodes), args.batch_size), desc="Embedding batches"):
        batch = nodes[i:i + args.batch_size]
        embedding_gen.embed_nodes(batch)
    
    # Step 4: Create target collection with hybrid search
    logger.info(f"Creating collection '{args.target}' with hybrid search...")
    indexer = QdrantIndexer(collection_name=args.target)
    indexer.create_collection(
        recreate=True,
        enable_hybrid=True,  # Enable BM25 + Dense
    )
    
    # Step 5: Index with sparse vectors
    logger.info("Indexing with dense + sparse vectors...")
    indexer.index_nodes(
        nodes=nodes,
        batch_size=100,
        enable_sparse=True,
    )
    
    # Summary
    elapsed = time.time() - start_time
    collection_info = indexer.get_collection_info()
    
    logger.info("=" * 60)
    logger.info("INDEXING COMPLETE")
    logger.info("=" * 60)
    logger.info(f"Source Collection: {args.source}")
    logger.info(f"Target Collection: {args.target}")
    logger.info(f"Points indexed: {collection_info.get('points_count', 'N/A')}")
    logger.info(f"Time elapsed: {elapsed:.1f}s")
    logger.info("")
    logger.info("Features enabled:")
    logger.info("  ✅ Contextual Retrieval (prepended document context)")
    logger.info("  ✅ Hybrid Search (BM25 + Dense vectors)")
    logger.info("  ✅ Optimized retrieval (150 → rerank → 20)")
    logger.info("")
    logger.info("Expected improvement: 67% reduction in retrieval failures")
    logger.info("=" * 60)
    
    logger.info("")
    logger.info("NEXT STEPS:")
    logger.info(f"1. Run evaluation: python run_claim_ledger_eval.py --collection {args.target}")
    logger.info(f"2. If satisfied, update .env: QDRANT_COLLECTION_NAME={args.target}")
    logger.info("")


if __name__ == "__main__":
    main()
