#!/usr/bin/env python3
"""Sync R2 files to Supabase - add missing document records."""
import boto3
import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

PROJECT_ID = "0816e8d3-ab23-417c-bf3f-e45531411c73"

# Get R2 client
r2 = boto3.client('s3',
    endpoint_url=f"https://{os.getenv('R2_ACCOUNT_ID')}.r2.cloudflarestorage.com",
    aws_access_key_id=os.getenv('R2_ACCESS_KEY_ID'),
    aws_secret_access_key=os.getenv('R2_SECRET_ACCESS_KEY'),
    region_name='auto'
)
bucket = os.getenv('R2_BUCKET_NAME', 'devchat-pdfs')
paginator = r2.get_paginator('list_objects_v2')

# Get Supabase client
supabase = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_SERVICE_ROLE_KEY'))

# Get existing documents in Supabase
docs = supabase.table('documents').select('filename').eq('rag_project_id', PROJECT_ID).execute()
existing_filenames = set(d['filename'] for d in docs.data)
print(f"Existing documents in Supabase: {len(existing_filenames)}")

# Get R2 files with metadata
r2_files = []
for page in paginator.paginate(Bucket=bucket, Prefix=f'rags/{PROJECT_ID}/input-pdfs/'):
    for obj in page.get('Contents', []):
        key = obj['Key']
        filename = key.split('/')[-1]
        # Extract doc_id (filename without .pdf)
        doc_id = filename.rsplit('.', 1)[0] if '.' in filename else filename
        r2_files.append({
            'key': key,
            'filename': filename,
            'doc_id': doc_id,
            'size': obj.get('Size', 0),
        })

print(f"Files in R2: {len(r2_files)}")

# Find missing documents
missing = []
for f in r2_files:
    if f['doc_id'] not in existing_filenames:
        missing.append(f)

print(f"Missing from Supabase: {len(missing)}")

if not missing:
    print("✅ All R2 files are already in Supabase!")
    exit(0)

# Add missing documents
print("\nAdding missing documents to Supabase...")
added = 0
for f in missing:
    # Extract original filename from doc_id (after the hash_)
    parts = f['doc_id'].split('_', 1)
    if len(parts) > 1:
        original_name = parts[1] + '.pdf'
    else:
        original_name = f['filename']
    
    try:
        result = supabase.table('documents').insert({
            'rag_project_id': PROJECT_ID,
            'filename': f['doc_id'],
            'original_filename': original_name,
            'file_size_bytes': f['size'],
            'mime_type': 'application/pdf',
            'status': 'pending',
            'r2_input_key': f['key'],
            'metadata': {},
        }).execute()
        added += 1
        print(f"  ✅ Added: {f['doc_id'][:40]}...")
    except Exception as e:
        print(f"  ❌ Failed: {f['doc_id'][:40]}... - {e}")

print(f"\nDone! Added {added}/{len(missing)} documents to Supabase.")
