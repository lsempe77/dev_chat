"""Inspect MineRU JSON to understand caption issue."""
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

print("Downloading JSON...")
data = r2.get_object(Bucket=bucket, Key=key)
doc = json.loads(data['Body'].read().decode('utf-8'))

tables = doc.get('tables', [])
print(f"Tables in document: {len(tables)}")
print(f"Keys in first table: {list(tables[0].keys())}")
print()

# Analyze caption patterns
with_caption = 0
without_caption = 0

print("=" * 100)
print("TABLES WITHOUT CAPTIONS")
print("=" * 100)

for i, table in enumerate(tables):
    caption_list = table.get('table_caption', [])
    caption = ' '.join(caption_list).strip() if caption_list else ''
    
    if not caption:
        without_caption += 1
        # Look for table reference in body
        body = table.get('table_body', '')
        
        # Try to find "Table X" pattern in HTML
        table_refs = re.findall(r'Table\s+[\d\.]+[a-z]?:?[^<]*', body, re.IGNORECASE)
        
        print(f"\nTable {i+1} (no caption):")
        if table_refs:
            print(f"  Found in body: {table_refs[0][:80]}")
        else:
            # Show first 150 chars of body
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(body, 'html.parser')
            text = soup.get_text(separator=' ', strip=True)[:150]
            print(f"  Body preview: {text}")
    else:
        with_caption += 1

print()
print("=" * 100)
print(f"SUMMARY: {with_caption} with caption, {without_caption} without ({without_caption/len(tables)*100:.0f}%)")
print("=" * 100)

# Also check if there's a table_footnote or other field
print("\nChecking other fields that might have caption info...")
sample = tables[5] if len(tables) > 5 else tables[0]
for key, value in sample.items():
    if key != 'table_body':
        val_preview = str(value)[:100] if value else '[empty]'
        print(f"  {key}: {val_preview}")
