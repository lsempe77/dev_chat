"""
Update Qdrant vectors with proper metadata (authors, year).

This script:
1. Reads all vectors from Qdrant
2. Extracts author/year from doc_id patterns or title
3. Updates the payload with the new metadata
"""
import os
import re
from collections import defaultdict
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, SetPayloadOperation, PointIdsList

# Connect to Qdrant
url = os.environ.get('QDRANT_URL')
key = os.environ.get('QDRANT_API_KEY')
client = QdrantClient(url=url, api_key=key)

COLLECTION_NAME = 'devchat_v2_contextual'


def extract_metadata_from_doc_id(doc_id: str) -> dict:
    """
    Extract author and year from doc_id patterns like:
    - Bandiera_(2017)
    - Ara_(2016)
    - Ahmed_(2009)
    """
    # Pattern: Author_(Year)
    match = re.search(r'([A-Za-z]+)_\((\d{4})\)', doc_id)
    if match:
        author = match.group(1)
        year = int(match.group(2))
        return {"authors": author, "year": year}
    
    # Pattern: Author_et_al_(Year)
    match = re.search(r'([A-Za-z]+)_et_al_?\((\d{4})\)', doc_id)
    if match:
        author = f"{match.group(1)} et al."
        year = int(match.group(2))
        return {"authors": author, "year": year}
    
    return {}


def extract_year_from_title(title: str) -> int | None:
    """Extract year from title if present (e.g., in parentheses at end)."""
    # Common patterns: (2023), 2023
    match = re.search(r'\((\d{4})\)', title)
    if match:
        year = int(match.group(1))
        if 1990 <= year <= 2026:
            return year
    
    match = re.search(r'\b(20\d{2}|19\d{2})\b', title)
    if match:
        year = int(match.group(1))
        if 1990 <= year <= 2026:
            return year
    
    return None


def main():
    print(f"Connecting to Qdrant collection: {COLLECTION_NAME}")
    
    # Get collection info
    info = client.get_collection(COLLECTION_NAME)
    print(f"Total vectors: {info.points_count}")
    
    # Scroll through all points
    all_points = []
    offset = None
    batch_size = 100
    
    while True:
        result = client.scroll(
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
    
    # Group by doc_id to analyze
    by_doc = defaultdict(list)
    for point in all_points:
        doc_id = point.payload.get('doc_id', 'unknown')
        by_doc[doc_id].append(point)
    
    print(f"Found {len(by_doc)} unique documents")
    
    # Track updates
    updates = []
    docs_with_metadata = 0
    docs_without_metadata = 0
    
    for doc_id, points in by_doc.items():
        title = points[0].payload.get('title', '')
        
        # Skip image-only entries
        if title.startswith('!['):
            continue
        
        # Try to extract metadata
        metadata = extract_metadata_from_doc_id(doc_id)
        
        # If no author from doc_id, check if we can get year from title
        if not metadata.get('year'):
            year = extract_year_from_title(title)
            if year:
                metadata['year'] = year
        
        if metadata:
            docs_with_metadata += 1
            print(f"  ✓ {doc_id[:30]}: authors={metadata.get('authors', 'N/A')}, year={metadata.get('year', 'N/A')}")
            
            # Queue updates for all points with this doc_id
            for point in points:
                updates.append({
                    'id': point.id,
                    'payload': metadata,
                })
        else:
            docs_without_metadata += 1
            print(f"  ✗ {doc_id[:30]}: No metadata found (title: {title[:40]}...)")
    
    print(f"\nSummary:")
    print(f"  Documents with extracted metadata: {docs_with_metadata}")
    print(f"  Documents without metadata: {docs_without_metadata}")
    print(f"  Total points to update: {len(updates)}")
    
    if not updates:
        print("\nNo updates to apply.")
        return
    
    # Apply updates in batches
    print(f"\nApplying {len(updates)} updates...")
    batch_size = 100
    for i in range(0, len(updates), batch_size):
        batch = updates[i:i+batch_size]
        
        for update in batch:
            client.set_payload(
                collection_name=COLLECTION_NAME,
                payload=update['payload'],
                points=[update['id']],
            )
        
        print(f"  Updated {min(i+batch_size, len(updates))}/{len(updates)}")
    
    print("\n✅ Done! Metadata updated in Qdrant.")


if __name__ == "__main__":
    main()
