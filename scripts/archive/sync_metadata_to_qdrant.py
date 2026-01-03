"""
Sync metadata from PostgreSQL to Qdrant.

This script:
1. Reads metadata from PostgreSQL documents table (authors, year, etc.)
2. Updates corresponding Qdrant vectors with the metadata
"""
import os
import asyncio
from collections import defaultdict

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from qdrant_client import QdrantClient


async def main():
    # Connect to PostgreSQL
    db_url = os.environ.get('DATABASE_URL')
    if not db_url:
        print('DATABASE_URL not set')
        return
    
    # Convert to async URL
    if db_url.startswith('postgres://'):
        db_url = db_url.replace('postgres://', 'postgresql+asyncpg://')
    elif db_url.startswith('postgresql://'):
        db_url = db_url.replace('postgresql://', 'postgresql+asyncpg://')
    
    engine = create_async_engine(db_url)
    
    # Connect to Qdrant
    qdrant_url = os.environ.get('QDRANT_URL')
    qdrant_key = os.environ.get('QDRANT_API_KEY')
    qdrant = QdrantClient(url=qdrant_url, api_key=qdrant_key)
    
    COLLECTION_NAME = 'devchat_v2_contextual'
    
    # Get all documents with metadata from PostgreSQL
    async with engine.connect() as conn:
        result = await conn.execute(text('''
            SELECT id, title, authors, year, abstract, doi, countries, sectors
            FROM documents
            WHERE authors IS NOT NULL OR year IS NOT NULL
        '''))
        rows = result.fetchall()
    
    print(f"Found {len(rows)} documents with metadata in PostgreSQL")
    
    # Create doc_id to metadata mapping
    doc_metadata = {}
    for row in rows:
        doc_id = row[0]
        authors = row[2]  # This is a list
        year = row[3]
        abstract = row[4]
        doi = row[5]
        countries = row[6]  # Plural
        sectors = row[7]    # Plural
        
        # Format authors string
        if authors and len(authors) > 0:
            if len(authors) <= 2:
                authors_str = " & ".join(authors)
            else:
                authors_str = f"{authors[0]} et al."
        else:
            authors_str = None
        
        if authors_str or year:
            doc_metadata[doc_id] = {
                "authors": authors_str,
                "year": year,
            }
            if abstract:
                doc_metadata[doc_id]["abstract"] = abstract[:500]  # Truncate
            if doi:
                doc_metadata[doc_id]["doi"] = doi
            if countries:
                doc_metadata[doc_id]["country"] = countries[0] if isinstance(countries, list) else countries
            if sectors:
                doc_metadata[doc_id]["sector"] = sectors[0] if isinstance(sectors, list) else sectors
    
    print(f"Prepared metadata for {len(doc_metadata)} documents")
    
    # Get all Qdrant points
    all_points = []
    offset = None
    batch_size = 100
    
    while True:
        result = qdrant.scroll(
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
    
    print(f"Retrieved {len(all_points)} points from Qdrant")
    
    # Match and update
    updates = []
    matched_docs = set()
    
    for point in all_points:
        doc_id = point.payload.get('doc_id', '')
        
        if doc_id in doc_metadata:
            matched_docs.add(doc_id)
            updates.append({
                'id': point.id,
                'payload': doc_metadata[doc_id],
            })
    
    print(f"Matched {len(matched_docs)} documents ({len(updates)} vectors to update)")
    
    if not updates:
        print("No updates needed.")
        return
    
    # Show sample
    print("\nSample updates:")
    for doc_id in list(matched_docs)[:5]:
        meta = doc_metadata[doc_id]
        print(f"  {doc_id[:30]}: authors={meta.get('authors')}, year={meta.get('year')}")
    
    # Apply updates
    print(f"\nApplying {len(updates)} updates...")
    batch_size = 100
    for i in range(0, len(updates), batch_size):
        batch = updates[i:i+batch_size]
        
        for update in batch:
            qdrant.set_payload(
                collection_name=COLLECTION_NAME,
                payload=update['payload'],
                points=[update['id']],
            )
        
        print(f"  Updated {min(i+batch_size, len(updates))}/{len(updates)}")
    
    print("\n✅ Done! Metadata synced from PostgreSQL to Qdrant.")


if __name__ == "__main__":
    asyncio.run(main())
