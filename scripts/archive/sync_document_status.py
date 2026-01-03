#!/usr/bin/env python3
"""
Sync document status from R2 outputs to Supabase.

This script checks R2 for completed PDF outputs and updates the corresponding
documents in Supabase to 'completed' status.
"""
import os
import boto3
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

def main():
    project_id = '0816e8d3-ab23-417c-bf3f-e45531411c73'
    
    # Setup clients
    supabase = create_client(
        os.environ['SUPABASE_URL'], 
        os.environ['SUPABASE_SERVICE_ROLE_KEY']
    )
    
    r2_account_id = os.environ['R2_ACCOUNT_ID']
    s3 = boto3.client(
        's3',
        endpoint_url=f"https://{r2_account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ['R2_ACCESS_KEY_ID'],
        aws_secret_access_key=os.environ['R2_SECRET_ACCESS_KEY'],
        region_name='auto',
    )
    
    bucket = os.environ.get('R2_BUCKET_NAME', 'devchat-pdfs')
    
    # Get all documents from Supabase (not just processing)
    result = supabase.table('documents').select('id, filename, original_filename, status').eq('rag_project_id', project_id).execute()
    docs = result.data or []
    print(f"Found {len(docs)} total documents in project")
    
    # Count by status
    from collections import Counter
    status_counts = Counter(d['status'] for d in docs)
    print(f"Current status: {dict(status_counts)}")
    
    # Get completed outputs from R2
    output_prefix = f'rags/{project_id}/outputs/json/'
    completed_files = set()
    
    paginator_token = None
    while True:
        if paginator_token:
            r2_response = s3.list_objects_v2(Bucket=bucket, Prefix=output_prefix, ContinuationToken=paginator_token)
        else:
            r2_response = s3.list_objects_v2(Bucket=bucket, Prefix=output_prefix)
        
        if 'Contents' in r2_response:
            for obj in r2_response['Contents']:
                filename = Path(obj['Key']).stem
                completed_files.add(filename)
        
        if r2_response.get('IsTruncated'):
            paginator_token = r2_response.get('NextContinuationToken')
        else:
            break
    
    print(f"Found {len(completed_files)} completed outputs in R2")
    
    # Debug: show samples
    print("\nSample R2 outputs (first 3):")
    for f in list(completed_files)[:3]:
        print(f"  {f}")
    
    print("\nSample Supabase filenames (first 3):")
    for doc in docs[:3]:
        print(f"  filename: {doc.get('filename')}")
        print(f"  original_filename: {doc.get('original_filename')}")
    
    # Update Supabase for matching documents
    # Match using 'filename' field (not original_filename)
    updated = 0
    not_found = 0
    
    for doc in docs:
        if doc['status'] == 'completed':
            continue  # Already completed
            
        # Use 'filename' field which matches R2 naming
        filename = doc.get('filename', '')
        
        if filename in completed_files:
            try:
                supabase.table('documents').update({
                    'status': 'completed',
                    'processed_at': datetime.utcnow().isoformat(),
                    'updated_at': datetime.utcnow().isoformat(),
                }).eq('id', doc['id']).execute()
                updated += 1
                print(f"  ✓ Updated: {filename[:50]}...")
            except Exception as e:
                print(f"  ✗ Error updating {doc['id']}: {e}")
        else:
            not_found += 1
    
    print(f"\nSummary:")
    print(f"  Updated to completed: {updated}")
    print(f"  Not found in R2 outputs: {not_found}")
    
    # Check final status
    result = supabase.table('documents').select('status').eq('rag_project_id', project_id).execute()
    final_counts = Counter(d['status'] for d in result.data)
    print(f"  Final status: {dict(final_counts)}")

if __name__ == '__main__':
    main()
