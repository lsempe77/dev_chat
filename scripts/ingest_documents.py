#!/usr/bin/env python
"""
DevChat v2.0 SOTA - Document Ingestion Script

Ingest documents into the vector database.

Usage:
    python scripts/ingest_documents.py --source ./data/markdown --collection devchat_v2
    python scripts/ingest_documents.py --source ./data/markdown --recreate
"""

import argparse
import sys
import time
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config.settings import settings
from src.ingestion.chunking import get_chunker
from src.ingestion.document_loader import DocumentLoader
from src.ingestion.embeddings import EmbeddingGenerator
from src.ingestion.indexer import QdrantIndexer
from src.utils.logging import get_logger, setup_logging

setup_logging()
logger = get_logger(__name__)


def main():
    parser = argparse.ArgumentParser(
        description="Ingest documents into DevChat vector database"
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
        default=settings.qdrant_collection_name,
        help="Qdrant collection name",
    )
    
    parser.add_argument(
        "--chunker",
        type=str,
        choices=["simple", "markdown", "semantic", "parent_child", "hybrid"],
        default="hybrid",
        help="Chunking strategy to use",
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
        help="Process documents but don't index",
    )
    
    args = parser.parse_args()
    
    logger.info("=" * 60)
    logger.info("DevChat v2.0 SOTA - Document Ingestion")
    logger.info("=" * 60)
    logger.info(f"Source: {args.source}")
    logger.info(f"Metadata: {args.metadata}")
    logger.info(f"Collection: {args.collection}")
    logger.info(f"Chunker: {args.chunker}")
    logger.info(f"Recreate: {args.recreate}")
    logger.info(f"Dry run: {args.dry_run}")
    logger.info("=" * 60)
    
    start_time = time.time()
    
    # Step 1: Load documents
    logger.info("\n📂 Step 1: Loading documents...")
    loader = DocumentLoader(
        markdown_dir=Path(args.source),
        metadata_file=Path(args.metadata),
    )
    documents = loader.load_all()
    logger.info(f"✅ Loaded {len(documents)} documents")
    
    if not documents:
        logger.error("❌ No documents found. Check source path.")
        sys.exit(1)
    
    # Step 2: Chunk documents
    logger.info("\n✂️ Step 2: Chunking documents...")
    chunker = get_chunker(args.chunker)
    nodes = chunker.chunk(documents)
    logger.info(f"✅ Created {len(nodes)} chunks")
    
    # Show sample
    if nodes:
        sample = nodes[0]
        logger.info(f"\nSample chunk:")
        logger.info(f"  - Length: {len(sample.text)} chars")
        logger.info(f"  - Metadata: {list(sample.metadata.keys())}")
    
    if args.dry_run:
        logger.info("\n🏃 Dry run - skipping indexing")
        elapsed = time.time() - start_time
        logger.info(f"\n⏱️ Completed in {elapsed:.1f} seconds")
        return
    
    # Step 3: Generate embeddings
    logger.info("\n🧮 Step 3: Generating embeddings...")
    embedding_gen = EmbeddingGenerator()
    nodes = embedding_gen.embed_nodes(nodes, show_progress=True)
    logger.info(f"✅ Generated embeddings for {len(nodes)} chunks")
    
    # Step 4: Index in Qdrant
    logger.info("\n📦 Step 4: Indexing in Qdrant...")
    indexer = QdrantIndexer(collection_name=args.collection)
    
    # Create collection
    indexer.create_collection(recreate=args.recreate)
    
    # Index nodes
    indexer.index_nodes(nodes, batch_size=args.batch_size)
    
    # Get final info
    info = indexer.get_collection_info()
    logger.info(f"✅ Indexed {info.get('points_count', 'N/A')} points")
    
    # Summary
    elapsed = time.time() - start_time
    
    logger.info("\n" + "=" * 60)
    logger.info("✅ INGESTION COMPLETE")
    logger.info("=" * 60)
    logger.info(f"Documents processed: {len(documents)}")
    logger.info(f"Chunks created: {len(nodes)}")
    logger.info(f"Points indexed: {info.get('points_count', 'N/A')}")
    logger.info(f"Collection: {args.collection}")
    logger.info(f"Time elapsed: {elapsed:.1f} seconds")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
