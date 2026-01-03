"""Check document counts per RAG project."""
from dotenv import load_dotenv
load_dotenv()

from supabase import create_client
import os

supabase = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_SERVICE_ROLE_KEY'])

# List all RAG projects
projects = supabase.table('rag_projects').select('id, name, slug').execute()
print('RAG Projects:')
for p in projects.data:
    # Count documents per project
    docs = supabase.table('documents').select('id', count='exact').eq('rag_project_id', p['id']).execute()
    
    # Count by metadata source
    zotero_docs = supabase.table('documents').select('id', count='exact').eq('rag_project_id', p['id']).ilike('metadata->>metadata_source', 'zotero').execute()
    
    print(f"  {p['name']} ({p['slug']})")
    print(f"    Total docs: {docs.count}")
    print(f"    From Zotero: {zotero_docs.count}")
    print(f"    ID: {p['id']}")
    print()
