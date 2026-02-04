"""
Extract table captions from MineRU content field and match to tables.
The captions are in the markdown content, not in table_caption field!
"""
import boto3
import os
import json
import re
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

data = r2.get_object(Bucket=bucket, Key=key)
doc = json.loads(data['Body'].read().decode('utf-8'))

content = doc.get('content', '')
tables = doc.get('tables', [])

print(f"Tables in JSON: {len(tables)}")
print(f"Content length: {len(content)} chars")
print()

# Extract all table captions from content
# Pattern: "Table X.Y: Description" or "Table X.Y. Description"
caption_pattern = r'(Table\s+[\d\.]+[a-z]?)[:\.]?\s*([^\n\|]{5,200})'
all_captions = re.findall(caption_pattern, content, re.IGNORECASE)

# Deduplicate (same caption appears in TOC and in body)
unique_captions = {}
for table_num, desc in all_captions:
    table_num = table_num.strip()
    desc = desc.strip()
    # Clean up description (remove page numbers, dots)
    desc = re.sub(r'\.{2,}\s*\d+$', '', desc).strip()
    desc = re.sub(r'\s+\d+$', '', desc).strip()
    
    if table_num not in unique_captions or len(desc) > len(unique_captions[table_num]):
        unique_captions[table_num] = desc

print(f"Unique table captions found in content: {len(unique_captions)}")
print()

# Check how many tables in the tables array have empty captions
tables_with_caption = sum(1 for t in tables if t.get('table_caption'))
tables_without_caption = len(tables) - tables_with_caption

print(f"Tables with caption in 'table_caption' field: {tables_with_caption}")
print(f"Tables WITHOUT caption: {tables_without_caption}")
print()

# Show matching
print("=" * 100)
print("SAMPLE: First 20 table captions from content")
print("=" * 100)
for i, (num, desc) in enumerate(sorted(unique_captions.items())[:20]):
    print(f"  {num}: {desc[:70]}")

print()
print("=" * 100)
print("TABLE ARRAY vs CONTENT CAPTIONS")
print("=" * 100)

# Check page_idx of tables and try to match
for i, table in enumerate(tables[:15]):
    page = table.get('page_idx', 'N/A')
    caption_field = ' '.join(table.get('table_caption', []))[:50]
    print(f"Table {i+1} (page {page}): caption_field = '{caption_field or '[EMPTY]'}'")

print()
print("=" * 100)
print("SOLUTION: Extract captions from content markdown")
print("=" * 100)
print("""
The MineRU JSON has:
1. 'tables' array with HTML bodies but EMPTY 'table_caption' fields
2. 'content' field (markdown) with ALL the table captions

We need to:
1. Parse the content field to extract table captions
2. Match them to tables by position/page number
3. Use content-based captions instead of table_caption field
""")

# Save the extracted captions
output = {
    'total_tables': len(tables),
    'tables_with_caption_field': tables_with_caption,
    'captions_found_in_content': len(unique_captions),
    'caption_map': unique_captions
}

with open('extraction_pipeline/outputs/extracted_captions.json', 'w') as f:
    json.dump(output, f, indent=2)
print("\nSaved extracted captions to: extraction_pipeline/outputs/extracted_captions.json")
