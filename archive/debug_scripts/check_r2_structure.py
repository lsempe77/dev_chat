"""Check R2 bucket structure to understand what's available."""
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

# List all top-level prefixes
print('=' * 70)
print('TOP-LEVEL PREFIXES IN BUCKET')
print('=' * 70)
paginator = client.get_paginator('list_objects_v2')
prefixes = set()
for page in paginator.paginate(Bucket=bucket, Delimiter='/'):
    for p in page.get('CommonPrefixes', []):
        print(f"  {p['Prefix']}")
        prefixes.add(p['Prefix'])

# Check under 'rags/' prefix
print('\n' + '=' * 70)
print('PREFIXES UNDER rags/')
print('=' * 70)
for page in paginator.paginate(Bucket=bucket, Prefix='rags/', Delimiter='/'):
    for p in page.get('CommonPrefixes', []):
        print(f"  {p['Prefix']}")

# Check the specific output folder structure
base_prefix = 'rags/0816e8d3-ab23-417c-bf3f-e45531411c73/'
print(f'\n{"=" * 70}')
print(f'PREFIXES UNDER {base_prefix}')
print('=' * 70)
for page in paginator.paginate(Bucket=bucket, Prefix=base_prefix, Delimiter='/'):
    for p in page.get('CommonPrefixes', []):
        print(f"  {p['Prefix']}")

# Check outputs folder
outputs_prefix = base_prefix + 'outputs/'
print(f'\n{"=" * 70}')
print(f'PREFIXES UNDER {outputs_prefix}')
print('=' * 70)
for page in paginator.paginate(Bucket=bucket, Prefix=outputs_prefix, Delimiter='/'):
    for p in page.get('CommonPrefixes', []):
        print(f"  {p['Prefix']}")

# Count files in each subfolder
print(f'\n{"=" * 70}')
print('FILE COUNTS BY FOLDER')
print('=' * 70)

folders = ['json/', 'md/', 'images/']
for folder in folders:
    prefix = outputs_prefix + folder
    count = 0
    study_ids = set()
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get('Contents', []):
            count += 1
            # Extract study ID
            match = re.search(r'(\d{9})', obj['Key'])
            if match:
                study_ids.add(match.group(1))
    print(f"  {folder}: {count} files, {len(study_ids)} unique study IDs")

# Check input-pdfs folder
print(f'\n{"=" * 70}')
print('INPUT PDFs')
print('=' * 70)
input_prefix = 'input-pdfs/'
pdf_count = 0
pdf_study_ids = set()
for page in paginator.paginate(Bucket=bucket, Prefix=input_prefix):
    for obj in page.get('Contents', []):
        pdf_count += 1
        match = re.search(r'(\d{9})', obj['Key'])
        if match:
            pdf_study_ids.add(match.group(1))
print(f"  Total PDFs: {pdf_count}")
print(f"  Unique study IDs in PDFs: {len(pdf_study_ids)}")

# List all JSON files and their study IDs
print(f'\n{"=" * 70}')
print('ALL JSON FILES')
print('=' * 70)
json_prefix = outputs_prefix + 'json/'
json_files = []
for page in paginator.paginate(Bucket=bucket, Prefix=json_prefix):
    for obj in page.get('Contents', []):
        json_files.append(obj['Key'])

print(f"Total JSON files: {len(json_files)}")
print("\nFirst 10:")
for f in json_files[:10]:
    print(f"  {f.split('/')[-1]}")

print("\nLast 10:")
for f in json_files[-10:]:
    print(f"  {f.split('/')[-1]}")

# Extract all study IDs from JSON files
json_study_ids = set()
for f in json_files:
    match = re.search(r'(\d{9})', f)
    if match:
        json_study_ids.add(match.group(1))

print(f"\nUnique study IDs in JSON files: {len(json_study_ids)}")

# Compare with PDF study IDs
print(f'\n{"=" * 70}')
print('COMPARISON: PDFs vs JSON')
print('=' * 70)
print(f"PDFs with study IDs: {len(pdf_study_ids)}")
print(f"JSONs with study IDs: {len(json_study_ids)}")
print(f"In PDFs but not JSON: {len(pdf_study_ids - json_study_ids)}")
print(f"In JSON but not PDFs: {len(json_study_ids - pdf_study_ids)}")

if pdf_study_ids - json_study_ids:
    print("\nStudies with PDF but no JSON (need MinerU processing):")
    for sid in sorted(pdf_study_ids - json_study_ids)[:20]:
        print(f"  {sid}")
    if len(pdf_study_ids - json_study_ids) > 20:
        print(f"  ... and {len(pdf_study_ids - json_study_ids) - 20} more")
