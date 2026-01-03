"""Quick script to verify enriched metadata in Qdrant."""
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue
import os
from dotenv import load_dotenv

load_dotenv()

c = QdrantClient(
    url=os.getenv('QDRANT_URL'),
    api_key=os.getenv('QDRANT_API_KEY')
)

# Get collection info
info = c.get_collection('devchat_v2')
print(f"Collection has {info.points_count} points total")

# Get Gilligan document 
results = c.scroll(
    collection_name='devchat_v2',
    scroll_filter=Filter(must=[FieldCondition(key='doc_id', match=MatchValue(value='121378172_Gilligan_2024'))]),
    limit=1,
    with_payload=True
)

if results[0]:
    p = results[0][0].payload
    print('\n=== ENRICHED METADATA FOR GILLIGAN 2024 ===')
    print(f"doc_id: {p.get('doc_id')}")
    print(f"title: {p.get('title', '')[:80]}...")
    print(f"authors: {p.get('authors')}")
    print(f"year: {p.get('year')}")
    print(f"doi: {p.get('doi')}")
    print(f"countries: {p.get('countries')}")
    print(f"sectors: {p.get('sectors')}")
    print(f"study_type: {p.get('study_type')}")
    print(f"intervention: {p.get('intervention')}")
    print(f"metadata_source: {p.get('metadata_source')}")
    print(f"metadata_confidence: {p.get('metadata_confidence')}")
    print(f"needs_review: {p.get('needs_review')}")
else:
    print('Gilligan document not found!')

# Show all unique doc_ids
print("\n=== ALL DOC IDS ===")
all_results = c.scroll(collection_name='devchat_v2', limit=200, with_payload=["doc_id"])
doc_ids = set(r.payload.get('doc_id') for r in all_results[0] if r.payload.get('doc_id'))
for d in sorted(doc_ids):
    print(f"  - {d}")
