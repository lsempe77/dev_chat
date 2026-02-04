"""Deep inspection of MineRU JSON to find where captions actually are."""
import boto3
import os
import json
from dotenv import load_dotenv
load_dotenv()

account_id = os.environ.get('CLOUDFLARE_ACCOUNT_ID')
r2 = boto3.client('s3',
    endpoint_url=f'https://{account_id}.r2.cloudflarestorage.com',
    aws_access_key_id=os.environ.get('R2_ACCESS_KEY_ID'),
    aws_secret_access_key=os.environ.get('R2_SECRET_ACCESS_KEY'),
    region_name='auto')

bucket = 'devchat-pdfs'
key = 'rags/0816e8d3-ab23-417c-bf3f-e45531411c73/outputs/json/1f44cd8c70b8_PDFs_of_included_programs_121058367.json'

print("Downloading JSON...")
data = r2.get_object(Bucket=bucket, Key=key)
doc = json.loads(data['Body'].read().decode('utf-8'))

print("=" * 100)
print("TOP-LEVEL KEYS IN JSON:")
print("=" * 100)
for k in doc.keys():
    v = doc[k]
    if isinstance(v, list):
        print(f"  {k}: list with {len(v)} items")
    elif isinstance(v, dict):
        print(f"  {k}: dict with keys {list(v.keys())[:5]}...")
    else:
        print(f"  {k}: {type(v).__name__} = {str(v)[:50]}")

print()
print("=" * 100)
print("INSPECTING 'tables' ARRAY - FIRST TABLE")
print("=" * 100)

table = doc['tables'][0]
for k, v in table.items():
    if k == 'table_body':
        print(f"  {k}: HTML ({len(v)} chars)")
    else:
        print(f"  {k}: {v}")

print()
print("=" * 100)
print("LOOKING FOR TEXT BLOCKS NEAR TABLES")
print("=" * 100)

# Check if there's a 'pdf_info' or 'pages' or 'content_list' with text blocks
if 'pdf_info' in doc:
    print("Found 'pdf_info':")
    print(f"  Keys: {list(doc['pdf_info'].keys())}")

if 'pages' in doc:
    print(f"\nFound 'pages': {len(doc['pages'])} pages")
    if doc['pages']:
        page = doc['pages'][0]
        print(f"  Page keys: {list(page.keys())}")

if 'content_list' in doc:
    print(f"\nFound 'content_list': {len(doc['content_list'])} items")
    # Look for table references
    table_refs = []
    for item in doc['content_list'][:100]:
        if isinstance(item, dict):
            text = item.get('text', '')
            if 'Table' in text and any(c.isdigit() for c in text):
                table_refs.append(text[:100])
    print(f"  Table references found: {len(table_refs)}")
    for ref in table_refs[:10]:
        print(f"    - {ref}")

# Check for markdown output
if 'markdown' in doc:
    print(f"\nFound 'markdown': {len(doc['markdown'])} chars")
    # Search for table captions in markdown
    import re
    md = doc['markdown']
    matches = re.findall(r'Table\s+[\d\.]+[a-z]?[:\.]?[^\n]{0,100}', md, re.IGNORECASE)
    print(f"  Table references in markdown: {len(matches)}")
    for m in matches[:15]:
        print(f"    - {m[:80]}")

print()
print("=" * 100)
print("RAW JSON SAMPLE - Save for inspection")
print("=" * 100)

# Save a sample for manual inspection
with open('extraction_pipeline/outputs/sample_mineru.json', 'w') as f:
    # Just save first 3 tables and metadata
    sample = {
        'keys': list(doc.keys()),
        'tables_sample': doc['tables'][:3] if 'tables' in doc else [],
        'content_list_sample': doc.get('content_list', [])[:50],
    }
    json.dump(sample, f, indent=2)
print("Saved sample to: extraction_pipeline/outputs/sample_mineru.json")
