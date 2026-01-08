#!/usr/bin/env python
"""
Study Design Classification Job

Classifies all documents in a project by study design type using LLM analysis.
Can be run standalone or integrated into the enrichment pipeline.

Usage:
    python scripts/run_study_design_classification.py [--project-id PROJECT_ID] [--force] [--dry-run]
"""

import asyncio
import argparse
import os
import sys

sys.path.append(os.getcwd())

from dotenv import load_dotenv
load_dotenv()

# Default project ID
DEFAULT_PROJECT_ID = "0816e8d3-ab23-417c-bf3f-e45531411c73"


async def main(project_id: str, force: bool = False, dry_run: bool = False):
    """Run study design classification for a project."""
    from src.ingestion.study_design_classifier import batch_classify_project
    
    print(f"=" * 60)
    print(f"Study Design Classification")
    print(f"=" * 60)
    print(f"Project: {project_id}")
    print(f"Force reclassify: {force}")
    print(f"Dry run: {dry_run}")
    print(f"=" * 60)
    
    stats = await batch_classify_project(
        project_id=project_id,
        force_reclassify=force,
        dry_run=dry_run,
    )
    
    print(f"\n{'=' * 60}")
    print("RESULTS")
    print(f"{'=' * 60}")
    print(f"Total documents: {stats['total']}")
    print(f"Classified:      {stats['classified']}")
    print(f"Skipped:         {stats['skipped']}")
    print(f"Failed:          {stats['failed']}")
    
    print(f"\nBy Study Design:")
    for design, count in sorted(stats['by_design'].items(), key=lambda x: -x[1]):
        print(f"  {design}: {count}")
    
    return stats


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Classify documents by study design")
    parser.add_argument(
        "--project-id",
        default=DEFAULT_PROJECT_ID,
        help=f"RAG project ID (default: {DEFAULT_PROJECT_ID})"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force reclassification even if already classified"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be classified without updating database"
    )
    
    args = parser.parse_args()
    asyncio.run(main(args.project_id, args.force, args.dry_run))
