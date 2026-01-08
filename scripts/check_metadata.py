"""Quick check of document metadata for classification analysis."""
import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

client = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_SERVICE_ROLE_KEY'])
result = client.table('documents').select('id, metadata').eq(
    'rag_project_id', '0816e8d3-ab23-417c-bf3f-e45531411c73'
).execute()

# Count documents with/without abstract
with_abstract = 0
without_abstract = 0
unknown_design = 0

for doc in result.data:
    meta = doc.get('metadata') or {}
    has_abstract = bool(meta.get('abstract'))
    design = meta.get('study_design', 'missing')
    
    if has_abstract:
        with_abstract += 1
    else:
        without_abstract += 1
    
    if design == 'unknown':
        unknown_design += 1

print(f"Total documents: {len(result.data)}")
print(f"With abstract: {with_abstract}")
print(f"Without abstract: {without_abstract}")
print(f"Unknown study design: {unknown_design}")
print()

# Show a few examples of unknown designs
print("Sample documents with 'unknown' study design:")
count = 0
for doc in result.data:
    meta = doc.get('metadata') or {}
    if meta.get('study_design') == 'unknown':
        title = meta.get('title', 'NO TITLE')[:60]
        abstract_len = len(meta.get('abstract', ''))
        print(f"  - {title}... (abstract: {abstract_len} chars)")
        count += 1
        if count >= 5:
            break
