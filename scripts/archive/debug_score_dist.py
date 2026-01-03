#!/usr/bin/env python
"""Debug: Check score distribution across all documents."""

from qdrant_client import QdrantClient
import cohere
import os
from dotenv import load_dotenv
load_dotenv()

co = cohere.Client(api_key=os.environ['COHERE_API_KEY'])
query = 'What is the graduation approach to poverty reduction?'
query_resp = co.embed(texts=[query], model='embed-v4.0', input_type='search_query', embedding_types=['float'])
query_vec = query_resp.embeddings.float_[0]

c = QdrantClient(url=os.environ['QDRANT_URL'], api_key=os.environ['QDRANT_API_KEY'])

# Get ALL results with score_threshold very low
results = c.query_points(
    collection_name='devchat_v2',
    query=query_vec,
    using='dense',
    limit=500,  # Get more
    score_threshold=0.1,  # Very low threshold
    with_payload=True,
)

print(f'Total results with threshold 0.1: {len(results.points)}')
if results.points:
    scores = [p.score for p in results.points]
    print(f'Score range: {min(scores):.4f} - {max(scores):.4f}')
    docs = set(p.payload.get('doc_id') for p in results.points)
    print(f'Unique docs: {len(docs)}')
