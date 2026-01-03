"""
Sync metadata from Qdrant to Supabase documents table.

This ensures the dashboard shows the correct authors/year.
"""
import os
import re
from collections import defaultdict

from qdrant_client import QdrantClient
from supabase import create_client

# Load environment
from dotenv import load_dotenv
load_dotenv()

# Connect to services
qdrant_url = os.environ.get('QDRANT_URL')
qdrant_key = os.environ.get('QDRANT_API_KEY')
qdrant = QdrantClient(url=qdrant_url, api_key=qdrant_key)

supabase_url = os.environ.get('SUPABASE_URL')
supabase_key = os.environ.get('SUPABASE_ANON_KEY')
supabase = create_client(supabase_url, supabase_key)

COLLECTION_NAME = 'devchat_v2_contextual'


def main():
    print("Fetching metadata from Qdrant...")
    
    # Get all points from Qdrant
    all_points = []
    offset = None
    
    while True:
        result = qdrant.scroll(
            collection_name=COLLECTION_NAME,
            limit=100,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        points, next_offset = result
        all_points.extend(points)
        if next_offset is None:
            break
        offset = next_offset
    
    print(f"Retrieved {len(all_points)} vectors")
    
    # Group by doc_id and get metadata
    by_doc = defaultdict(list)
    for point in all_points:
        doc_id = point.payload.get('doc_id', 'unknown')
        by_doc[doc_id].append(point)
    
    print(f"Found {len(by_doc)} unique documents")
    
    # Build metadata map
    metadata_map = {}
    for doc_id, points in by_doc.items():
        payload = points[0].payload
        title = payload.get('title', '')
        authors = payload.get('authors', '')
        year = payload.get('year')
        
        if title and not title.startswith('!['):
            metadata_map[doc_id] = {
                'title': title,
                'authors': authors,
                'year': year,
            }
    
    print(f"Documents with metadata: {len([m for m in metadata_map.values() if m.get('authors') or m.get('year')])}")
    
    # Get documents from Supabase
    print("\nFetching documents from Supabase...")
    result = supabase.table('documents').select('id, filename, metadata').execute()
    docs = result.data
    print(f"Found {len(docs)} documents in Supabase")
    
    # Match and update
    updated = 0
    for doc in docs:
        filename = doc.get('filename', '')
        existing_meta = doc.get('metadata', {}) or {}
        
        # Try to find matching Qdrant doc by filename pattern
        matched_meta = None
        for doc_id, meta in metadata_map.items():
            # Check if filename contains the doc_id prefix
            if doc_id.split('_')[0] in filename:
                matched_meta = meta
                break
        
        if not matched_meta:
            # Try matching by filename pattern
            for doc_id, meta in metadata_map.items():
                if filename.replace('.pdf', '') in doc_id or doc_id in filename:
                    matched_meta = meta
                    break
        
        if matched_meta and (matched_meta.get('authors') or matched_meta.get('year')):
            # Check if update needed (metadata stored in JSONB)
            needs_update = (
                (matched_meta.get('title') and not existing_meta.get('title')) or
                (matched_meta.get('authors') and not existing_meta.get('authors')) or
                (matched_meta.get('year') and not existing_meta.get('year'))
            )
            
            if needs_update:
                # Merge with existing metadata
                new_meta = {**existing_meta}
                if matched_meta.get('title') and not existing_meta.get('title'):
                    new_meta['title'] = matched_meta['title']
                if matched_meta.get('authors') and not existing_meta.get('authors'):
                    new_meta['authors'] = matched_meta['authors']
                if matched_meta.get('year') and not existing_meta.get('year'):
                    new_meta['year'] = matched_meta['year']
                
                print(f"  Updating {filename}: title={new_meta.get('title', 'N/A')[:30]}..., authors={new_meta.get('authors', 'N/A')}, year={new_meta.get('year', 'N/A')}")
                try:
                    supabase.table('documents').update({'metadata': new_meta}).eq('id', doc['id']).execute()
                    updated += 1
                except Exception as e:
                    print(f"    Error: {e}")
    
    print(f"\n✅ Updated {updated} documents in Supabase")


if __name__ == "__main__":
    main()
