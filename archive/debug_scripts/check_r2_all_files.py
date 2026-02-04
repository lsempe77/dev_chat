"""Check R2 bucket - list ALL files and identify naming patterns."""
import os
from dotenv import load_dotenv
load_dotenv()

os.environ['AWS_ACCESS_KEY_ID'] = os.environ.get('R2_ACCESS_KEY_ID', '')
os.environ['AWS_SECRET_ACCESS_KEY'] = os.environ.get('R2_SECRET_ACCESS_KEY', '')

import boto3
import re
from collections import defaultdict

client = boto3.client(
    's3',
    endpoint_url=f"https://{os.environ['CLOUDFLARE_ACCOUNT_ID']}.r2.cloudflarestorage.com",
    aws_access_key_id=os.environ['R2_ACCESS_KEY_ID'],
    aws_secret_access_key=os.environ['R2_SECRET_ACCESS_KEY']
)

bucket = 'devchat-pdfs'
prefix = 'rags/0816e8d3-ab23-417c-bf3f-e45531411c73/outputs/json/'

# Get all files
paginator = client.get_paginator('list_objects_v2')
json_files = []
for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
    for obj in page.get('Contents', []):
        json_files.append(obj['Key'])

print(f"Total JSON files: {len(json_files)}")
print("=" * 70)

# Categorize files
numeric_ids = set()
named_studies = []

for f in json_files:
    filename = f.split('/')[-1]
    # Check for 9-digit numeric ID
    match = re.search(r'(\d{9})', filename)
    if match:
        numeric_ids.add(match.group(1))
    else:
        # Named study without numeric ID
        named_studies.append(filename)

print(f"\nFiles with 9-digit numeric IDs: {len(json_files) - len(named_studies)}")
print(f"Unique numeric IDs: {len(numeric_ids)}")
print(f"Files with named studies (no 9-digit ID): {len(named_studies)}")

print("\n" + "=" * 70)
print("NAMED STUDIES (no 9-digit ID):")
print("=" * 70)
for f in sorted(named_studies):
    print(f"  {f}")

print("\n" + "=" * 70)
print("ALL NUMERIC STUDY IDs:")
print("=" * 70)
for sid in sorted(numeric_ids):
    print(f"  {sid}")

# Also check if there are other RAG folders with data
print("\n" + "=" * 70)
print("CHECKING OTHER RAG FOLDERS")
print("=" * 70)

other_prefix = 'rags/bc8ddfa1-53c1-4119-8eb0-52ce540ef0e2/'
for page in paginator.paginate(Bucket=bucket, Prefix=other_prefix, Delimiter='/'):
    for p in page.get('CommonPrefixes', []):
        print(f"  {p['Prefix']}")

# Check outputs folder in other RAG
other_outputs = other_prefix + 'outputs/'
for page in paginator.paginate(Bucket=bucket, Prefix=other_outputs, Delimiter='/'):
    for p in page.get('CommonPrefixes', []):
        print(f"  {p['Prefix']}")

# Count files in the other RAG's outputs
other_json = other_outputs + 'json/'
other_count = 0
for page in paginator.paginate(Bucket=bucket, Prefix=other_json):
    for obj in page.get('Contents', []):
        other_count += 1
print(f"\nFiles in other RAG's json folder: {other_count}")

# Check top-level outputs folder
print("\n" + "=" * 70)
print("CHECKING TOP-LEVEL outputs/ FOLDER")
print("=" * 70)
top_outputs = 'outputs/'
for page in paginator.paginate(Bucket=bucket, Prefix=top_outputs, Delimiter='/'):
    for p in page.get('CommonPrefixes', []):
        print(f"  {p['Prefix']}")

# Count all files under top outputs
top_json = top_outputs + 'json/'
top_md = top_outputs + 'md/'
for folder, name in [(top_json, 'json'), (top_md, 'md')]:
    count = 0
    study_ids = set()
    for page in paginator.paginate(Bucket=bucket, Prefix=folder):
        for obj in page.get('Contents', []):
            count += 1
            match = re.search(r'(\d{9})', obj['Key'])
            if match:
                study_ids.add(match.group(1))
    print(f"  {name}/: {count} files, {len(study_ids)} unique numeric IDs")
