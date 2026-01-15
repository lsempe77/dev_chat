"""Explore MineRU output for Bossuroy paper to design better extraction."""

import boto3
import os
import json
from dotenv import load_dotenv

load_dotenv()

# Get R2 client
client = boto3.client(
    's3',
    endpoint_url=f"https://{os.environ['CLOUDFLARE_ACCOUNT_ID']}.r2.cloudflarestorage.com",
    aws_access_key_id=os.environ['R2_ACCESS_KEY_ID'],
    aws_secret_access_key=os.environ['R2_SECRET_ACCESS_KEY']
)

# Load Bossuroy paper - try different key patterns
possible_keys = [
    'processed/121058356/result.json',
    '121058356/result.json',
    'processed/121058356.json',
    '121058356.json',
]

# First list available keys
print("Listing available keys with prefix '121058356'...")
try:
    resp = client.list_objects_v2(Bucket='devchat-pdfs', Prefix='121058356', MaxKeys=10)
    for obj in resp.get('Contents', []):
        print(f"  Found: {obj['Key']}")
except Exception as e:
    print(f"  Error listing: {e}")

print()
print("Listing keys with 'processed' prefix...")
try:
    resp = client.list_objects_v2(Bucket='devchat-pdfs', Prefix='processed', MaxKeys=20)
    for obj in resp.get('Contents', []):
        print(f"  Found: {obj['Key']}")
except Exception as e:
    print(f"  Error listing: {e}")

# Try to load
data = None
for key in possible_keys:
    try:
        response = client.get_object(Bucket='devchat-pdfs', Key=key)
        data = json.loads(response['Body'].read().decode('utf-8'))
        print(f"Loaded from: {key}")
        break
    except Exception as e:
        print(f"Failed {key}: {type(e).__name__}")

if not data:
    print("Could not load data")
    exit(1)

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

# Show first few tables with their structure
for i, table in enumerate(tables[:5]):
    print(f"--- Table {i} ---")
    if isinstance(table, dict):
        print(f"  Keys: {list(table.keys())}")
        if 'page' in table:
            print(f"  Page: {table['page']}")
        if 'caption' in table:
            print(f"  Caption: {table['caption'][:100]}..." if len(str(table.get('caption', ''))) > 100 else f"  Caption: {table.get('caption')}")
        if 'html' in table:
            html = table['html']
            print(f"  HTML length: {len(html)} chars")
            # Show first 200 chars of HTML
            print(f"  HTML preview: {html[:200]}...")
    else:
        print(f"  Type: {type(table)}")
        print(f"  Preview: {str(table)[:200]}...")
    print()

# Check if there's prose content
content = data.get('content', data.get('markdown', data.get('text', '')))
if content:
    print(f"Content length: {len(content)} chars")
    print(f"Content preview (first 500 chars):")
    print(content[:500])
    print("...")
