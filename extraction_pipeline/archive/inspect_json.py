"""Inspect MineRU JSON to understand caption extraction."""
import boto3
import os
import json
import re
from dotenv import load_dotenv

load_dotenv()

print("Connecting to R2...")

# Connect to R2
account_id = os.environ.get('CLOUDFLARE_ACCOUNT_ID')
r2 = boto3.client(
    's3',
    endpoint_url=f'https://{account_id}.r2.cloudflarestorage.com',
    aws_access_key_id=os.environ.get('R2_ACCESS_KEY_ID'),
    aws_secret_access_key=os.environ.get('R2_SECRET_ACCESS_KEY'),
    region_name='auto'
)

bucket = 'devchat-pdfs'
prefix = 'rags/0816e8d3-ab23-417c-bf3f-e45531411c73/mineru-outputs/'

print("Searching for JSON files...")

# Find the study with most missing captions
resp = r2.list_objects_v2(Bucket=bucket, Prefix=prefix, MaxKeys=200)
found = False
for obj in resp.get('Contents', []):
    if '1f44cd8c70b8' in obj['Key'] and obj['Key'].endswith('.json'):
        print(f"Found: {obj['Key']}")
        found = True
        
        # Download and inspect
        data = r2.get_object(Bucket=bucket, Key=obj['Key'])
        doc = json.loads(data['Body'].read().decode('utf-8'))
        
        print(f"\nTables in document: {len(doc.get('tables', []))}")
        
        # Check all table keys
        if doc.get('tables'):
            print(f"Table keys available: {list(doc['tables'][0].keys())}")
        
        # Check first 10 tables
        for i, table in enumerate(doc.get('tables', [])[:10]):
            caption_list = table.get('table_caption', [])
            caption = ' '.join(caption_list) if caption_list else '[EMPTY]'
            
            print(f"\n--- Table {i+1} ---")
            print(f"  caption: {caption[:120]}")
            
            # Check table_body for "Table X" patterns
            body = table.get('table_body', '')
            if body:
                table_refs = re.findall(r'Table\s+[\d\.]+[a-z]?', body, re.IGNORECASE)
                if table_refs:
                    print(f"  Table refs in body: {table_refs[:3]}")
            
            # Check for footnote
            if table.get('table_footnote'):
                fn = table['table_footnote']
                if isinstance(fn, list):
                    fn = ' '.join(fn)
                print(f"  footnote: {fn[:80]}")
        
        break

if not found:
    print("No matching JSON found!")
