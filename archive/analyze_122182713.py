"""Analyze table captions from 122182713 JSON."""
from dotenv import load_dotenv
load_dotenv('.env')
import boto3
import json
import os
import re

account_id = os.environ.get('R2_ACCOUNT_ID')
endpoint_url = f'https://{account_id}.r2.cloudflarestorage.com'

s3 = boto3.client('s3',
    endpoint_url=endpoint_url,
    aws_access_key_id=os.environ['R2_ACCESS_KEY_ID'],
    aws_secret_access_key=os.environ['R2_SECRET_ACCESS_KEY'],
    region_name='auto'
)

# Get the JSON file
obj = s3.get_object(
    Bucket='devchat-pdfs',
    Key='rags/0816e8d3-ab23-417c-bf3f-e45531411c73/outputs/json/0cb609fbf433_PDFs_of_included_programs_122182713.json'
)
data = json.loads(obj['Body'].read())

# Print full structure
print("JSON keys:", list(data.keys()))
tables = data.get('tables', [])

print(f"Total tables: {len(tables)}")
print()

# Look at table structure
print("=" * 80)
print("TABLE ANALYSIS")
print("=" * 80)

for i, t in enumerate(tables):
    rows = t.get('rows', [])
    first_row = rows[0] if rows else []
    page = t.get('page', '?')
    
    # Convert first row to string for display
    first_row_str = ' | '.join([str(cell)[:30] for cell in first_row[:5]])
    
    print(f"\nTable {i+1} (page {page}):")
    print(f"  Rows: {len(rows)}")
    print(f"  First row: {first_row_str[:100]}")

# Also get the markdown to look for List of Tables
print("\n" + "=" * 80)
print("CHECKING MARKDOWN FOR 'LIST OF TABLES'")
print("=" * 80)

obj_md = s3.get_object(
    Bucket='devchat-pdfs',
    Key='rags/0816e8d3-ab23-417c-bf3f-e45531411c73/outputs/md/0cb609fbf433_PDFs_of_included_programs_122182713.md'
)
md_content = obj_md['Body'].read().decode('utf-8')

# Search for list of tables
if 'List of Tables' in md_content or 'LIST OF TABLES' in md_content:
    print("\nFound 'List of Tables' section!")
    # Find and extract it
    match = re.search(r'(List of Tables|LIST OF TABLES)(.*?)(List of Figures|LIST OF FIGURES|#|\n\n\n)', md_content, re.IGNORECASE | re.DOTALL)
    if match:
        list_of_tables = match.group(2)
        print(list_of_tables[:2000])
else:
    # Try to find table references
    table_refs = re.findall(r'Table\s+\d+[:\.]?\s*[^\n]+', md_content[:10000])
    print(f"\nNo 'List of Tables' section, but found {len(table_refs)} table references in first 10k chars")
    for ref in table_refs[:20]:
        print(f"  {ref[:80]}")
