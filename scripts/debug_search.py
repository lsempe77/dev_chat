#!/usr/bin/env python
"""Debug: Test Qdrant search diversity."""

from qdrant_client import QdrantClient
from src.ingestion.embeddings import EmbeddingGenerator
import os
from dotenv import load_dotenv
load_dotenv()

eg = EmbeddingGenerator()
query_emb = eg.embed_query('graduation approach poverty')
print(f'Query embedding sample: {query_emb[:3]}')

c = QdrantClient(url=os.environ['QDRANT_URL'], api_key=os.environ['QDRANT_API_KEY'])

# Search for 100 results
results = c.query_points(
    collection_name='devchat_v2',
    query=query_emb,
    using='dense',
    limit=100,
    with_payload=True,
)

# Count unique docs
docs = {}
for p in results.points:
    doc = p.payload.get('doc_id', 'unk')
    score = p.score
    if doc not in docs:
        docs[doc] = {'count': 0, 'scores': []}
    docs[doc]['count'] += 1
    docs[doc]['scores'].append(round(score, 4))

print(f'Total results: {len(results.points)}')
print(f'Unique documents: {len(docs)}')
print()
for doc, info in list(docs.items())[:10]:
    print(f'{doc[:35]}: {info["count"]} chunks, scores={info["scores"][:3]}')
