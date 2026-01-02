#!/usr/bin/env python
"""
DevChat v2.0 SOTA - Contextual Retrieval Re-Indexing Script

Implements Anthropic's SOTA RAG stack (2024/2025):
1. Contextual Retrieval - prepend document context to chunks
2. Hybrid Search (BM25 + Dense) - 49% retrieval improvement  
3. Cohere Reranking - additional 18% improvement
4. Optimal top-K (150 → 20) - retrieve more, rerank down

Total expected improvement: 67% reduction in retrieval failures

Usage:
    python scripts/reindex_contextual.py --collection devchat_v2_contextual
    python scripts/reindex_contextual.py --collection devchat_v2_contextual --contextual-mode llm
    python scripts/reindex_contextual.py --collection devchat_v2_contextual --dry-run
"""

import argparse
import asyncio
import sys
import time
from pathlib import Path
from typing import Dict, List

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config.settings import settings
from src.ingestion.chunking import get_chunker
from src.ingestion.contextualizer import ChunkContextualizer, FastContextualizer, get_contextualizer
from src.ingestion.document_loader import DocumentLoader
from src.ingestion.embeddings import EmbeddingGenerator
from src.ingestion.indexer import QdrantIndexer
from src.utils.logging import get_logger, setup_logging

setup_logging()
logger = get_logger(__name__)


def load_documents(source_dir: Path, metadata_file: Path) -> tuple:
    """Load documents and return both docs and doc_dict for contextualization."""
    logger.info(f"Loading documents from {source_dir}")
    
    loader = DocumentLoader(
        markdown_dir=source_dir,
        metadata_file=metadata_file,
    )
    
    documents = loader.load_all()
    logger.info(f"Loaded {len(documents)} documents")
    
    # Create document dict keyed by various IDs for lookup
    doc_dict = {}
    for doc in documents:
        # Key by all possible identifiers
        doc_id = doc.metadata.get('doc_id', '')
        source = doc.metadata.get('source', '')
        title = doc.metadata.get('title', '')
        
        if doc_id:
            doc_dict[doc_id] = doc
        if source:
            doc_dict[source] = doc
            # Also key by filename without extension
            base = Path(source).stem
            doc_dict[base] = doc
    
    return documents, doc_dict


async def contextualize_chunks(
    nodes: List,
    doc_dict: Dict,
    mode: str = "fast",
) -> List:
    """Apply contextual retrieval to chunks."""
    logger.info(f"Contextualizing {len(nodes)} chunks (mode={mode})")
    
    if mode == "llm":
        contextualizer = ChunkContextualizer()
        contextualized = await contextualizer.contextualize_nodes(
            nodes=nodes,
            documents=doc_dict,
            batch_size=10,
            show_progress=True,
        )
    else:
        # Fast mode - metadata only, no LLM calls
        contextualizer = FastContextualizer()
        contextualized = contextualizer.contextualize_nodes(
            nodes=nodes,
            documents=doc_dict,
        )
    
    return contextualized


def run_ingestion(args):
    """Main ingestion pipeline with contextual retrieval."""
    start_time = time.time()
    
    # Configuration summary
    logger.info("=" * 60)
    logger.info("SOTA RAG Stack Configuration (Anthropic 2024)")
    logger.info("=" * 60)
    logger.info(f"Collection: {args.collection}")
    logger.info(f"Contextual Retrieval: ENABLED (mode={args.contextual_mode})")
    logger.info(f"Hybrid Search (BM25+Dense): ENABLED")
    logger.info(f"Initial Retrieval: {settings.retrieval_top_k} chunks")
    logger.info(f"After Reranking: {settings.rerank_top_n} chunks")
    logger.info(f"Chunking Strategy: {args.chunker}")
    logger.info("=" * 60)
    
    if args.dry_run:
        logger.info("DRY RUN - no changes will be made")
    
    # Step 1: Load documents
    source_dir = Path(args.source)
    metadata_file = Path(args.metadata)
    
    documents, doc_dict = load_documents(source_dir, metadata_file)
    
    if not documents:
        logger.error("No documents found!")
        return
    
    # Step 2: Chunk documents
    logger.info(f"Chunking with strategy: {args.chunker}")
    chunker = get_chunker(args.chunker)
    nodes = chunker.chunk(documents)
    logger.info(f"Created {len(nodes)} chunks")
    
    if args.dry_run:
        logger.info(f"DRY RUN: Would contextualize {len(nodes)} chunks")
        logger.info(f"DRY RUN: Would create collection '{args.collection}' with hybrid=True")
        logger.info("DRY RUN complete - exiting")
        return
    
    # Step 3: Contextualize chunks (Anthropic's key insight)
    logger.info("Applying Contextual Retrieval...")
    contextualized_nodes = asyncio.run(
        contextualize_chunks(nodes, doc_dict, mode=args.contextual_mode)
    )
    
    # Show sample of contextualization
    if contextualized_nodes:
        sample = contextualized_nodes[0]
        logger.info(f"\n--- Sample Contextualized Chunk ---")
        text = sample.get_content()[:500]
        logger.info(f"{text}...")
        logger.info(f"--- End Sample ---\n")
    
    # Step 4: Generate embeddings for contextualized text
    logger.info("Generating embeddings for contextualized chunks...")
    embedding_gen = EmbeddingGenerator()
    embedding_gen.embed_nodes(contextualized_nodes)
    
    # Step 5: Create collection with hybrid search enabled
    logger.info(f"Creating collection '{args.collection}' with hybrid search...")
    indexer = QdrantIndexer(collection_name=args.collection)
    indexer.create_collection(
        recreate=args.recreate,
        enable_hybrid=True,  # Phase A: Enable BM25+Dense
    )
    
    # Step 6: Index with sparse vectors
    logger.info("Indexing with dense + sparse vectors...")
    indexer.index_nodes(
        nodes=contextualized_nodes,
        batch_size=args.batch_size,
        enable_sparse=True,  # Phase A: BM25 vectors
    )
    
    # Summary
    elapsed = time.time() - start_time
    collection_info = indexer.get_collection_info()
    
    logger.info("=" * 60)
    logger.info("INDEXING COMPLETE")
    logger.info("=" * 60)
    logger.info(f"Collection: {args.collection}")
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
    
    # Remind to update settings
    logger.info("")
    logger.info("NEXT STEPS:")
    logger.info(f"1. Update .env: QDRANT_COLLECTION_NAME={args.collection}")
    logger.info(f"2. Run evaluation: python run_claim_ledger_eval.py --collection {args.collection}")
    logger.info("")


def main():
    parser = argparse.ArgumentParser(
        description="Re-index with Anthropic's SOTA Contextual Retrieval"
    )
    
    parser.add_argument(
        "--source",
        type=str,
        default=str(settings.markdown_dir),
        help="Path to source documents (markdown files)",
    )
    
    parser.add_argument(
        "--metadata",
        type=str,
        default=str(settings.metadata_file),
        help="Path to metadata CSV file",
    )
    
    parser.add_argument(
        "--collection",
        type=str,
        default="devchat_v2_contextual",
        help="Target collection name",
    )
    
    parser.add_argument(
        "--chunker",
        type=str,
        choices=["simple", "markdown", "semantic", "parent_child", "hybrid"],
        default="hybrid",
        help="Chunking strategy",
    )
    
    parser.add_argument(
        "--contextual-mode",
        type=str,
        choices=["fast", "llm"],
        default="fast",
        help="'fast' uses metadata only, 'llm' uses AI to generate context",
    )
    
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="Recreate collection (delete existing)",
    )
    
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Batch size for indexing",
    )
    
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )
    
    args = parser.parse_args()
    run_ingestion(args)


if __name__ == "__main__":
    main()
