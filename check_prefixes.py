from qdrant_client import QdrantClient
from dotenv import load_dotenv
import os
load_dotenv()

client = QdrantClient(url=os.environ.get('QDRANT_URL'), api_key=os.environ.get('QDRANT_API_KEY'))
points = client.scroll('rag_0816e8d3-ab23-417c-bf3f-e45531411c73', limit=8, with_payload=True)
for i, p in enumerate(points[0][:5]):
    pl = p.payload
    print(f"=== Sample {i+1} (pages {pl.get('page_start')}-{pl.get('page_end')}) ===")
    prefix = pl.get('contextual_prefix', 'None')
    print(f"PREFIX: {prefix}")
    print(f"TEXT: {pl.get('text', '')[:200]}...")
    print()
