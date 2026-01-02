"""Check document metadata in Supabase."""
import os
from supabase import create_client

url = os.environ.get('SUPABASE_URL')
key = os.environ.get('SUPABASE_ANON_KEY')
client = create_client(url, key)

result = client.table('documents').select('title, authors, year, metadata').limit(3).execute()
for doc in result.data:
    print(f"Title: {doc.get('title')}")
    print(f"  authors: {doc.get('authors')}")
    print(f"  year: {doc.get('year')}")
    print(f"  metadata: {doc.get('metadata')}")
    print()
