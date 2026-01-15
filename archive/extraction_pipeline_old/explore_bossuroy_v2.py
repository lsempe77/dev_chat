"""Explore MineRU output for Bossuroy paper (121058356)."""

import boto3
import os
import json
from dotenv import load_dotenv

load_dotenv()

client = boto3.client(
    's3',
    endpoint_url=f"https://{os.environ['CLOUDFLARE_ACCOUNT_ID']}.r2.cloudflarestorage.com",
    aws_access_key_id=os.environ['R2_ACCESS_KEY_ID'],
    aws_secret_access_key=os.environ['R2_SECRET_ACCESS_KEY']
)

# Load Bossuroy JSON
r2_key = 'rags/0816e8d3-ab23-417c-bf3f-e45531411c73/outputs/json/8d23199222c8_PDFs_of_included_programs_121058356.json'
response = client.get_object(Bucket='devchat-pdfs', Key=r2_key)
data = json.loads(response['Body'].read().decode('utf-8'))

print("=" * 70)
print("MINERU OUTPUT STRUCTURE FOR BOSSUROY (121058356)")
print("=" * 70)
print()
print(f"Top-level keys: {list(data.keys())}")
print()

# Check tables
tables = data.get('tables', [])
print(f"Number of tables: {len(tables)}")
print()

# Show first few tables
for i, table in enumerate(tables[:3]):
    print(f"--- Table {i} ---")
    if isinstance(table, dict):
        print(f"  Keys: {list(table.keys())}")
        for k, v in table.items():
            if k == 'html':
                print(f"  html: {len(v)} chars")
            elif k == 'markdown':
                print(f"  markdown preview: {str(v)[:300]}...")
            else:
                print(f"  {k}: {v}")
    else:
        print(f"  Type: {type(table)}")
        print(f"  Content: {str(table)[:500]}...")
    print()

# Check for prose content
for key in ['content', 'markdown', 'text', 'pages']:
    if key in data:
        val = data[key]
        if isinstance(val, str):
            print(f"{key}: {len(val)} chars")
            print(f"Preview: {val[:500]}...")
        elif isinstance(val, list):
            print(f"{key}: list of {len(val)} items")
            if val and isinstance(val[0], dict):
                print(f"  First item keys: {list(val[0].keys())}")
        print()
