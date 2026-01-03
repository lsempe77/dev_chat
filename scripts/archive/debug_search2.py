#!/usr/bin/env python
"""Debug: Test different Qdrant search methods."""

from qdrant_client import QdrantClient
from qdrant_client.models import NamedVector
from src.ingestion.embeddings import EmbeddingGenerator
import os
from dotenv import load_dotenv
load_dotenv()

eg = EmbeddingGenerator()
query_emb = eg.embed_query('graduation approach')

c = QdrantClient(url=os.environ['QDRANT_URL'], api_key=os.environ['QDRANT_API_KEY'])

# Try using search() instead of query_points()
print('=== Test: Using search() with NamedVector ===')
results = c.search(
    collection_name='devchat_v2',
    query_vector=NamedVector(name='dense', vector=query_emb),
    limit=20,
    with_payload=True,
)
docs = set(p.payload.get('doc_id') for p in results)
scores = [round(p.score, 4) for p in results]
print(f'Results: {len(results)}, unique docs: {len(docs)}')
print(f'Scores: {scores[:5]}')
print(f'Docs: {list(docs)[:5]}')
