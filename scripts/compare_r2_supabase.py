#!/usr/bin/env python3
"""Compare R2 files with Supabase documents."""
import boto3
import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

PROJECT_ID = "0816e8d3-ab23-417c-bf3f-e45531411c73"

# Get R2 files
r2 = boto3.client('s3',
    endpoint_url=f"https://{os.getenv('R2_ACCOUNT_ID')}.r2.cloudflarestorage.com",
    aws_access_key_id=os.getenv('R2_ACCESS_KEY_ID'),
    aws_secret_access_key=os.getenv('R2_SECRET_ACCESS_KEY'),
    region_name='auto'
)
bucket = os.getenv('R2_BUCKET_NAME', 'devchat-pdfs')
paginator = r2.get_paginator('list_objects_v2')

r2_files = {}
for page in paginator.paginate(Bucket=bucket, Prefix=f'rags/{PROJECT_ID}/'):
    for obj in page.get('Contents', []):
        key = obj['Key']
        parts = key.split('/')
        # rags/{project_id}/{subfolder}/filename
        if len(parts) >= 4:
            subfolder = parts[2]
            filename = parts[3]
            if subfolder not in r2_files:
                r2_files[subfolder] = set()
            r2_files[subfolder].add(filename)

print("R2 Structure:")
for subfolder, files in r2_files.items():
    print(f"  {subfolder}/: {len(files)} files")

input_pdfs = r2_files.get('input-pdfs', set())
print(f"\nR2 input-pdfs: {len(input_pdfs)} files")

# Get Supabase documents
supabase = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_SERVICE_ROLE_KEY'))
docs = supabase.table('documents').select('filename, r2_input_key, original_filename').eq('rag_project_id', PROJECT_ID).execute()

print(f"Supabase documents: {len(docs.data)}")

# Build comparison sets
db_filenames = set()
for d in docs.data:
    # The filename in db is the doc_id (hash_name), add .pdf extension
    db_filenames.add(d['filename'] + '.pdf')

# Find differences
only_r2 = input_pdfs - db_filenames
only_db = db_filenames - input_pdfs

if only_r2:
    print(f"\nIn R2 but NOT in Supabase ({len(only_r2)}):")
    for f in sorted(only_r2):
        print(f"  {f}")

if only_db:
    print(f"\nIn Supabase but NOT in R2 ({len(only_db)}):")
    for f in sorted(only_db):
        print(f"  {f}")

if not only_r2 and not only_db:
    print("\n✅ R2 and Supabase are in sync!")
