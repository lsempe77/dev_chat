#!/usr/bin/env python
"""
DevChat v2.0 SOTA - PDF Processing Script

Batch process PDFs from a directory and ingest into Qdrant.

Usage:
    python scripts/process_pdfs.py --pdf-dir ./pdfs
    python scripts/process_pdfs.py --pdf-dir ./pdfs --output-dir ./processed
    python scripts/process_pdfs.py --pdf-dir ./pdfs --dry-run

Features:
- Uses MinerU for SOTA PDF extraction
- Extracts tables, formulas, and figures
- Chunks and embeds content
- Stores in Qdrant vector database
"""

import argparse
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.config.settings import settings
from src.ingestion.pdf_processor import MinerUProcessor, process_pdfs
from src.ingestion.chunking import MarkdownChunker, ParentChildChunker
from src.ingestion.embeddings import get_embedding_model
from src.ingestion.indexer import QdrantIndexer
from src.utils.logging import get_logger

logger = get_logger(__name__)


def main():
    parser = argparse.ArgumentParser(
        description="Process PDFs and ingest into Qdrant"
    )
    parser.add_argument(
        "--pdf-dir",
        type=Path,
        required=True,
        help="Directory containing PDF files"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory for processed files (default: temp)"
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        default=True,
        help="Search subdirectories for PDFs"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Process PDFs but don't upload to Qdrant"
    )
    parser.add_argument(
        "--no-ocr",
        action="store_true",
        help="Disable OCR for scanned pages"
    )
    parser.add_argument(
        "--extract-images",
        action="store_true",
        help="Extract figures/images from PDFs"
    )
    parser.add_argument(
        "--chunker",
        choices=["markdown", "parent-child"],
        default="markdown",
        help="Chunking strategy (default: markdown)"
    )
    parser.add_argument(
        "--collection",
        type=str,
        default=None,
        help="Qdrant collection name (default: from settings)"
    )
    
    args = parser.parse_args()
    
    # Validate PDF directory
    if not args.pdf_dir.exists():
        logger.error(f"PDF directory not found: {args.pdf_dir}")
        sys.exit(1)
    
    logger.info("=" * 60)
    logger.info("DevChat v2.0 - PDF Processing Pipeline")
    logger.info("=" * 60)
    logger.info(f"PDF Directory: {args.pdf_dir}")
    logger.info(f"Output Directory: {args.output_dir or 'temp'}")
    logger.info(f"Dry Run: {args.dry_run}")
    logger.info(f"Chunker: {args.chunker}")
    logger.info("=" * 60)
    
    # Step 1: Process PDFs with MinerU
    logger.info("\n[1/4] Processing PDFs with MinerU...")
    
    processor = MinerUProcessor(
        output_dir=args.output_dir,
        use_ocr=not args.no_ocr,
        extract_images=args.extract_images,
    )
    
    results = processor.process_directory(args.pdf_dir, recursive=args.recursive)
    
    # Summary
    success_count = sum(1 for r in results if r.success)
    failed_count = len(results) - success_count
    
    logger.info(f"\nPDF Processing Summary:")
    logger.info(f"  Total PDFs: {len(results)}")
    logger.info(f"  Successful: {success_count}")
    logger.info(f"  Failed: {failed_count}")
    
    if failed_count > 0:
        logger.warning("\nFailed PDFs:")
        for r in results:
            if not r.success:
                logger.warning(f"  - {r.file_path}: {r.error}")
    
    # Step 2: Convert to Documents
    logger.info("\n[2/4] Converting to Documents...")
    
    documents = processor.to_documents(results)
    
    if not documents:
        logger.error("No documents created. Exiting.")
        sys.exit(1)
    
    logger.info(f"Created {len(documents)} Documents")
    
    # Print sample metadata
    if documents:
        sample = documents[0]
        logger.info(f"\nSample document metadata:")
        for key, value in sample.metadata.items():
            if key == "abstract" and value:
                logger.info(f"  {key}: {str(value)[:100]}...")
            else:
                logger.info(f"  {key}: {value}")
    
    if args.dry_run:
        logger.info("\n[DRY RUN] Skipping chunking and indexing")
        
        # Just print stats
        total_chars = sum(len(d.text) for d in documents)
        logger.info(f"\nDocument Statistics:")
        logger.info(f"  Total documents: {len(documents)}")
        logger.info(f"  Total characters: {total_chars:,}")
        logger.info(f"  Average chars/doc: {total_chars // len(documents):,}")
        
        # Count tables and formulas
        total_tables = sum(
            d.metadata.get("table_count", 0) for d in documents
        )
        total_formulas = sum(
            1 for d in documents if d.metadata.get("has_formulas", False)
        )
        logger.info(f"  Documents with tables: {total_tables}")
        logger.info(f"  Documents with formulas: {total_formulas}")
        
        logger.info("\n✓ Dry run complete!")
        return
    
    # Step 3: Chunk documents
    logger.info("\n[3/4] Chunking documents...")
    
    if args.chunker == "parent-child":
        chunker = ParentChildChunker()
    else:
        chunker = MarkdownChunker()
    
    nodes = chunker.chunk(documents)
    logger.info(f"Created {len(nodes)} chunks")
    
    # Step 4: Embed and index
    logger.info("\n[4/4] Embedding and indexing...")
    
    embed_model = get_embedding_model()
    indexer = QdrantIndexer(
        collection_name=args.collection or settings.qdrant_collection,
        embed_model=embed_model,
    )
    
    indexer.index_nodes(nodes)
    
    logger.info("\n" + "=" * 60)
    logger.info("✓ PDF processing complete!")
    logger.info("=" * 60)
    logger.info(f"  PDFs processed: {success_count}")
    logger.info(f"  Documents created: {len(documents)}")
    logger.info(f"  Chunks indexed: {len(nodes)}")
    logger.info(f"  Collection: {args.collection or settings.qdrant_collection}")


if __name__ == "__main__":
    main()
