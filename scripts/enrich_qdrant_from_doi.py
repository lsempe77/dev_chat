"""
Enrich Qdrant vectors with metadata from CrossRef/OpenAlex via DOI lookup.

This script:
1. Reads all unique documents from Qdrant
2. Extracts DOIs from text or metadata
3. Looks up metadata from CrossRef
4. Updates Qdrant vectors with authors, year, etc.
"""
import os
import re
import asyncio
from collections import defaultdict
from typing import Optional

from qdrant_client import QdrantClient

# Add project root to path
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.ingestion.metadata.crossref_client import CrossRefClient
from src.ingestion.metadata.openalex_client import OpenAlexClient


# Connect to Qdrant
url = os.environ.get('QDRANT_URL')
key = os.environ.get('QDRANT_API_KEY')
qdrant_client = QdrantClient(url=url, api_key=key)

COLLECTION_NAME = 'devchat_v2_contextual'


def extract_doi_from_text(text: str) -> Optional[str]:
    """Extract DOI from text content."""
    # Common DOI patterns
    patterns = [
        r'(?:doi[:\s]*)?(?:https?://)?(?:dx\.)?doi\.org/([^\s\]]+)',
        r'(?:DOI|doi)[:\s]+([^\s\]]+)',
        r'10\.\d{4,}/[^\s\]]+',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            doi = match.group(1) if match.lastindex else match.group(0)
            # Clean up DOI
            doi = doi.rstrip('.,;:)')
            if doi.startswith('10.'):
                return doi
    return None


async def enrich_from_crossref(doi: str) -> dict:
    """Look up metadata from CrossRef."""
    try:
        client = CrossRefClient()
        work = await client.get_by_doi(doi)
        if work:
            return {
                'authors': ', '.join(work.authors) if work.authors else None,
                'year': work.year,
                'journal': work.journal,
                'doi': doi,
            }
    except Exception as e:
        print(f"    CrossRef error: {e}")
    return {}


async def enrich_from_openalex(doi: str) -> dict:
    """Look up metadata from OpenAlex."""
    try:
        client = OpenAlexClient()
        work = await client.get_by_doi(doi)
        if work:
            return {
                'authors': ', '.join(work.authors) if work.authors else None,
                'year': work.year,
                'journal': work.journal,
                'doi': doi,
                'cited_by_count': work.cited_by_count,
                'is_open_access': work.is_open_access,
            }
    except Exception as e:
        print(f"    OpenAlex error: {e}")
    return {}


async def main():
    print(f"Connecting to Qdrant collection: {COLLECTION_NAME}")
    
    # Get collection info
    info = qdrant_client.get_collection(COLLECTION_NAME)
    print(f"Total vectors: {info.points_count}")
    
    # Scroll through all points to get unique documents
    all_points = []
    offset = None
    batch_size = 100
    
    while True:
        result = qdrant_client.scroll(
            collection_name=COLLECTION_NAME,
            limit=batch_size,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        points, next_offset = result
        all_points.extend(points)
        
        if next_offset is None:
            break
        offset = next_offset
    
    print(f"Retrieved {len(all_points)} points")
    
    # Group by doc_id
    by_doc = defaultdict(list)
    for point in all_points:
        doc_id = point.payload.get('doc_id', 'unknown')
        by_doc[doc_id].append(point)
    
    print(f"Found {len(by_doc)} unique documents")
    
    # Track results
    enriched_count = 0
    no_doi_count = 0
    already_has_metadata = 0
    failed_count = 0
    updates = []
    
    for doc_id, points in by_doc.items():
        title = points[0].payload.get('title', '')
        existing_authors = points[0].payload.get('authors')
        existing_year = points[0].payload.get('year')
        
        # Skip if already has metadata
        if existing_authors and existing_year:
            already_has_metadata += 1
            continue
        
        # Skip image-only entries
        if title.startswith('!['):
            continue
        
        # Try to find DOI in the text content
        doi = None
        for point in points[:3]:  # Check first few chunks
            text = point.payload.get('text', '') or point.payload.get('original_text', '')
            doi = extract_doi_from_text(text)
            if doi:
                break
        
        if not doi:
            no_doi_count += 1
            print(f"  ✗ {title[:50]}... - No DOI found")
            continue
        
        print(f"  → {title[:50]}... (DOI: {doi})")
        
        # Try CrossRef first, then OpenAlex
        metadata = await enrich_from_crossref(doi)
        if not metadata.get('authors'):
            metadata = await enrich_from_openalex(doi)
        
        if metadata.get('authors') or metadata.get('year'):
            enriched_count += 1
            print(f"    ✓ Found: authors={metadata.get('authors', 'N/A')[:30]}..., year={metadata.get('year', 'N/A')}")
            
            # Queue updates for all points with this doc_id
            for point in points:
                updates.append({
                    'id': point.id,
                    'payload': {k: v for k, v in metadata.items() if v is not None},
                })
        else:
            failed_count += 1
            print(f"    ✗ No metadata found in CrossRef/OpenAlex")
    
    print(f"\n{'='*60}")
    print(f"Summary:")
    print(f"  Already has metadata: {already_has_metadata}")
    print(f"  Enriched from DOI: {enriched_count}")
    print(f"  No DOI found: {no_doi_count}")
    print(f"  DOI lookup failed: {failed_count}")
    print(f"  Total points to update: {len(updates)}")
    
    if not updates:
        print("\nNo updates to apply.")
        return
    
    # Apply updates
    confirm = input(f"\nApply {len(updates)} updates to Qdrant? (y/n): ")
    if confirm.lower() != 'y':
        print("Aborted.")
        return
    
    print(f"\nApplying {len(updates)} updates...")
    batch_size = 100
    for i in range(0, len(updates), batch_size):
        batch = updates[i:i+batch_size]
        
        for update in batch:
            qdrant_client.set_payload(
                collection_name=COLLECTION_NAME,
                payload=update['payload'],
                points=[update['id']],
            )
        
        print(f"  Updated {min(i+batch_size, len(updates))}/{len(updates)}")
    
    print("\n✅ Done! Metadata enriched in Qdrant.")


if __name__ == "__main__":
    asyncio.run(main())
