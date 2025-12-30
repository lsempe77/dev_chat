#!/usr/bin/env python
"""Debug: Check if vectors stored in Qdrant are diverse."""

from qdrant_client import QdrantClient
import os
from dotenv import load_dotenv
load_dotenv()

c = QdrantClient(url=os.environ['QDRANT_URL'], api_key=os.environ['QDRANT_API_KEY'])

# Get a few points from different documents
pts, _ = c.scroll('devchat_v2', limit=5, with_vectors=True, with_payload=True)

print("Checking vector diversity...\n")
for i, p in enumerate(pts):
    vec = p.vector
    if isinstance(vec, dict):
        vec = vec.get('dense', [])
    doc_id = p.payload.get('doc_id', 'unknown')[:40]
    print(f"Point {i}:")
    print(f"  doc_id: {doc_id}")
    print(f"  vec[:5]:  {[round(v, 4) for v in vec[:5]]}")
    print(f"  vec[-5:]: {[round(v, 4) for v in vec[-5:]]}")
    print()

# Check if vectors are all the same
vecs = []
for p in pts:
    vec = p.vector
    if isinstance(vec, dict):
        vec = vec.get('dense', [])
    vecs.append(tuple(round(v, 6) for v in vec[:10]))

if len(set(vecs)) == 1:
    print("⚠️ WARNING: All vectors are IDENTICAL!")
else:
    print(f"✅ Vectors are diverse ({len(set(vecs))} unique patterns in first 10 dims)")
