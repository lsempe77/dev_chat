"""Check and set RAG project to public."""
import os
from supabase import create_client

url = os.environ.get('SUPABASE_URL')
key = os.environ.get('SUPABASE_ANON_KEY')
client = create_client(url, key)

# Get all RAG projects
result = client.table('rag_projects').select('id, name, is_public, slug, qdrant_collection').execute()
print('RAG Projects:')
for r in result.data:
    print(f"  - ID: {r['id']}")
    print(f"    Name: {r['name']}")
    print(f"    is_public: {r.get('is_public')}")
    print(f"    slug: {r.get('slug')}")
    print(f"    collection: {r.get('qdrant_collection')}")
    print()
