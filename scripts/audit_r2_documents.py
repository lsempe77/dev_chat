#!/usr/bin/env python3
"""
R2 Document Audit Script

Production script to:
1. Scan all documents in R2
2. Compute content hashes for deduplication
3. Identify true duplicates vs legitimate variants
4. Build/update the document registry
5. Generate audit report

Usage:
    python scripts/audit_r2_documents.py --scan          # Full scan with hash computation
    python scripts/audit_r2_documents.py --report        # Generate report from existing registry
    python scripts/audit_r2_documents.py --fix-duplicates  # Mark true duplicates for cleanup
"""
import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from extraction_pipeline.document_registry import (
    DocumentRegistry,
    DocumentType,
    Language,
    compute_content_hash,
)
from extraction_pipeline.r2_utils import get_r2_client, BUCKET_NAME, JSON_PREFIX


def get_all_r2_files() -> List[Dict]:
    """
    Get all JSON files from R2 with their metadata.
    
    Returns list of dicts with:
    - key: Full R2 key
    - filename: Just the filename
    - size: File size in bytes
    - last_modified: Timestamp
    """
    client = get_r2_client()
    paginator = client.get_paginator('list_objects_v2')
    
    files = []
    for page in paginator.paginate(Bucket=BUCKET_NAME, Prefix=JSON_PREFIX):
        for obj in page.get('Contents', []):
            key = obj['Key']
            if key.endswith('.json'):
                files.append({
                    'key': key,
                    'filename': key.split('/')[-1],
                    'size': obj.get('Size', 0),
                    'last_modified': obj.get('LastModified'),
                })
    
    return files


def compute_r2_content_hash(client, key: str) -> Optional[str]:
    """
    Compute content hash for an R2 object.
    
    Downloads first 64KB for fast hash computation.
    Full hash would require downloading entire file.
    """
    try:
        # Get first 64KB for hash (fast, but may miss differences in large files)
        response = client.get_object(Bucket=BUCKET_NAME, Key=key, Range='bytes=0-65535')
        content = response['Body'].read()
        return compute_content_hash(content)
    except Exception as e:
        print(f"  [ERROR] Failed to hash {key}: {e}")
        return None


def full_scan(registry: DocumentRegistry, compute_hashes: bool = True) -> Dict:
    """
    Full scan of R2 bucket, registering all documents.
    
    Args:
        registry: DocumentRegistry instance
        compute_hashes: If True, download and hash content for dedup
        
    Returns:
        Scan statistics
    """
    print("=" * 70)
    print("R2 DOCUMENT AUDIT - FULL SCAN")
    print("=" * 70)
    print(f"Timestamp: {datetime.now().isoformat()}")
    print()
    
    # Get all files
    print("Listing R2 files...")
    files = get_all_r2_files()
    print(f"Found {len(files)} JSON files")
    print()
    
    client = get_r2_client() if compute_hashes else None
    
    stats = {
        'total_files': len(files),
        'new_documents': 0,
        'existing_documents': 0,
        'errors': 0,
        'by_type': defaultdict(int),
        'by_language': defaultdict(int),
    }
    
    # Process each file
    print("Processing files...")
    for i, f in enumerate(files, 1):
        if i % 10 == 0:
            print(f"  Progress: {i}/{len(files)}")
        
        try:
            # Compute content hash if requested
            content_hash = None
            if compute_hashes and client:
                content_hash = compute_r2_content_hash(client, f['key'])
            
            # Register document
            study_id, variant, is_new = registry.register_document(
                filename=f['filename'],
                r2_key=f['key'],
                size_bytes=f['size'],
                content_hash=content_hash,
            )
            
            if is_new:
                stats['new_documents'] += 1
            else:
                stats['existing_documents'] += 1
            
            stats['by_type'][variant.doc_type.value] += 1
            stats['by_language'][variant.language.value] += 1
            
        except Exception as e:
            print(f"  [ERROR] Failed to process {f['filename']}: {e}")
            stats['errors'] += 1
    
    # Save registry
    registry.save()
    print(f"\nRegistry saved to: {registry.registry_path}")
    
    return stats


def generate_report(registry: DocumentRegistry) -> None:
    """Generate detailed audit report."""
    print("=" * 70)
    print("R2 DOCUMENT AUDIT REPORT")
    print("=" * 70)
    print(f"Generated: {datetime.now().isoformat()}")
    print()
    
    summary = registry.summary()
    
    # Overview
    print("OVERVIEW")
    print("-" * 40)
    print(f"Total Studies:     {summary['total_studies']}")
    print(f"Total Documents:   {summary['total_documents']}")
    print(f"With Appendices:   {summary['with_appendix']}")
    print(f"Multilingual:      {summary['multilingual']}")
    print()
    
    # By document type
    print("BY DOCUMENT TYPE")
    print("-" * 40)
    for doc_type, count in summary['by_type'].items():
        print(f"  {doc_type:15} {count:5}")
    print()
    
    # By language
    print("BY LANGUAGE")
    print("-" * 40)
    for lang, count in summary['by_language'].items():
        print(f"  {lang:15} {count:5}")
    print()
    
    # Studies with multiple variants
    print("STUDIES WITH MULTIPLE VARIANTS")
    print("-" * 40)
    multi_variant = [(sid, s) for sid, s in registry.studies.items() if len(s.variants) > 1]
    if multi_variant:
        for study_id, study in sorted(multi_variant, key=lambda x: -len(x[1].variants)):
            print(f"\n{study_id} ({len(study.variants)} variants):")
            for v in study.variants:
                print(f"  - [{v.doc_type.value:10}] [{v.language.value:2}] {v.filename[:60]}")
    else:
        print("  No studies with multiple variants")
    print()
    
    # True duplicates (same content hash)
    print("POTENTIAL TRUE DUPLICATES (same content)")
    print("-" * 40)
    duplicates = registry.find_duplicates()
    if duplicates:
        for content_hash, variants in duplicates.items():
            print(f"\nHash: {content_hash}")
            for v in variants:
                study_id = registry.doc_id_to_study.get(v.doc_id, 'unknown')
                print(f"  - [{study_id}] {v.filename[:60]}")
    else:
        print("  No content duplicates found")
    print()
    
    # Studies needing review
    print("STUDIES NEEDING MANUAL REVIEW")
    print("-" * 40)
    needs_review = []
    
    for study_id, study in registry.studies.items():
        issues = []
        
        # Multiple main documents
        mains = [v for v in study.variants if v.doc_type == DocumentType.MAIN]
        if len(mains) > 1:
            issues.append(f"{len(mains)} main documents (should have 1)")
        
        # Unknown language
        unknowns = [v for v in study.variants if v.language == Language.UNKNOWN]
        if unknowns:
            issues.append(f"{len(unknowns)} unknown language docs")
        
        if issues:
            needs_review.append((study_id, issues))
    
    if needs_review:
        for study_id, issues in needs_review:
            print(f"\n{study_id}:")
            for issue in issues:
                print(f"  ⚠ {issue}")
    else:
        print("  All studies look good!")


def identify_actions(registry: DocumentRegistry) -> List[Dict]:
    """
    Identify recommended cleanup actions.
    
    Returns list of recommended actions with justification.
    """
    actions = []
    
    # Find true content duplicates
    duplicates = registry.find_duplicates()
    for content_hash, variants in duplicates.items():
        # Keep the first one, mark others for removal
        keep = variants[0]
        for remove in variants[1:]:
            actions.append({
                'action': 'REMOVE_DUPLICATE',
                'doc_id': remove.doc_id,
                'r2_key': remove.r2_key,
                'reason': f"Duplicate of {keep.doc_id} (same content hash: {content_hash})",
                'keep': keep.doc_id,
            })
    
    # Find studies where appendix is same as main (common upload error)
    for study_id, study in registry.studies.items():
        mains = [v for v in study.variants if v.doc_type == DocumentType.MAIN]
        appendices = [v for v in study.variants if v.doc_type == DocumentType.APPENDIX]
        
        for main in mains:
            for appendix in appendices:
                if main.content_hash and main.content_hash == appendix.content_hash:
                    actions.append({
                        'action': 'REVIEW_APPENDIX',
                        'doc_id': appendix.doc_id,
                        'r2_key': appendix.r2_key,
                        'reason': f"Appendix has same content as main document {main.doc_id}",
                        'main_doc': main.doc_id,
                    })
    
    return actions


def export_for_extraction(registry: DocumentRegistry, output_path: Path) -> None:
    """
    Export registry to a format suitable for the extraction pipeline.
    
    Creates a CSV with one row per main document (or all variants if needed).
    """
    import csv
    
    rows = []
    for study_id, study in registry.studies.items():
        main = study.main_document
        if main:
            rows.append({
                'study_id': study_id,
                'doc_id': main.doc_id,
                'filename': main.filename,
                'r2_key': main.r2_key,
                'doc_type': main.doc_type.value,
                'language': main.language.value,
                'has_appendix': study.has_appendix,
                'variant_count': len(study.variants),
            })
    
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    
    print(f"Exported {len(rows)} studies to {output_path}")


def main():
    parser = argparse.ArgumentParser(description="R2 Document Audit Script")
    parser.add_argument('--scan', action='store_true', help='Full scan with hash computation')
    parser.add_argument('--quick-scan', action='store_true', help='Quick scan without hash computation')
    parser.add_argument('--report', action='store_true', help='Generate report from existing registry')
    parser.add_argument('--export', type=str, help='Export extraction manifest to CSV')
    parser.add_argument('--actions', action='store_true', help='List recommended cleanup actions')
    parser.add_argument('--registry', type=str, help='Path to registry JSON file')
    
    args = parser.parse_args()
    
    # Initialize registry
    registry_path = Path(args.registry) if args.registry else None
    registry = DocumentRegistry(registry_path)
    
    # Execute requested operation
    if args.scan:
        stats = full_scan(registry, compute_hashes=True)
        print("\nSCAN STATISTICS")
        print("-" * 40)
        print(f"Total files:      {stats['total_files']}")
        print(f"New documents:    {stats['new_documents']}")
        print(f"Already known:    {stats['existing_documents']}")
        print(f"Errors:           {stats['errors']}")
        
    elif args.quick_scan:
        stats = full_scan(registry, compute_hashes=False)
        print("\nQUICK SCAN STATISTICS")
        print("-" * 40)
        print(f"Total files:      {stats['total_files']}")
        print(f"New documents:    {stats['new_documents']}")
        print(f"Already known:    {stats['existing_documents']}")
        
    elif args.report:
        generate_report(registry)
        
    elif args.export:
        export_for_extraction(registry, Path(args.export))
        
    elif args.actions:
        actions = identify_actions(registry)
        print("=" * 70)
        print("RECOMMENDED CLEANUP ACTIONS")
        print("=" * 70)
        if actions:
            for action in actions:
                print(f"\n[{action['action']}]")
                print(f"  Doc ID: {action['doc_id']}")
                print(f"  R2 Key: {action['r2_key']}")
                print(f"  Reason: {action['reason']}")
        else:
            print("No cleanup actions needed!")
    
    else:
        # Default: show summary
        if registry.studies:
            summary = registry.summary()
            print(f"Registry has {summary['total_studies']} studies, {summary['total_documents']} documents")
            print("Use --scan, --report, --actions, or --export for more details")
        else:
            print("Registry is empty. Run --scan first.")


if __name__ == '__main__':
    main()
