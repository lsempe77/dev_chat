#!/usr/bin/env python3
"""Check storage status across R2, Qdrant, and Supabase."""
import boto3
import os
from dotenv import load_dotenv
from qdrant_client import QdrantClient
from supabase import create_client

load_dotenv()

def check_r2():
    """Check R2 bucket contents."""
    print("=" * 60)
    print("R2 STORAGE (Cloudflare)")
    print("=" * 60)
    
    r2 = boto3.client('s3',
        endpoint_url=f"https://{os.getenv('R2_ACCOUNT_ID')}.r2.cloudflarestorage.com",
        aws_access_key_id=os.getenv('R2_ACCESS_KEY_ID'),
        aws_secret_access_key=os.getenv('R2_SECRET_ACCESS_KEY'),
        region_name='auto'
    )
    
    bucket = os.getenv('R2_BUCKET_NAME', 'devchat-pdfs')
    paginator = r2.get_paginator('list_objects_v2')
    
    # Count by top-level prefix
    by_prefix = {}
    total_size = 0
    for page in paginator.paginate(Bucket=bucket):
        for obj in page.get('Contents', []):
            key = obj['Key']
            prefix = key.split('/')[0]
            by_prefix[prefix] = by_prefix.get(prefix, {'count': 0, 'size': 0})
            by_prefix[prefix]['count'] += 1
            by_prefix[prefix]['size'] += obj.get('Size', 0)
            total_size += obj.get('Size', 0)
    
    total_count = sum(p['count'] for p in by_prefix.values())
    print(f"Bucket: {bucket}")
    print(f"Total objects: {total_count}")
    print(f"Total size: {total_size / 1024 / 1024:.1f} MB")
    print("\nBy prefix:")
    for prefix, data in sorted(by_prefix.items()):
        print(f"  {prefix}/: {data['count']} objects ({data['size'] / 1024 / 1024:.1f} MB)")
    
    # Show rags/ structure
    if 'rags' in by_prefix:
        print("\nRAG Projects in R2:")
        projects = {}
        for page in paginator.paginate(Bucket=bucket, Prefix='rags/'):
            for obj in page.get('Contents', []):
                parts = obj['Key'].split('/')
                if len(parts) >= 2:
                    pid = parts[1]
                    projects[pid] = projects.get(pid, 0) + 1
        for pid, count in sorted(projects.items()):
            print(f"  {pid}: {count} files")


def check_qdrant():
    """Check Qdrant collections."""
    print("\n" + "=" * 60)
    print("QDRANT (Vector Database)")
    print("=" * 60)
    
    client = QdrantClient(url=os.getenv('QDRANT_URL'), api_key=os.getenv('QDRANT_API_KEY'))
    collections = client.get_collections().collections
    
    print(f"Total collections: {len(collections)}")
    print("\nCollections:")
    for c in collections:
        info = client.get_collection(c.name)
        print(f"  {c.name}: {info.points_count:,} vectors")


def check_supabase():
    """Check Supabase tables."""
    print("\n" + "=" * 60)
    print("SUPABASE (PostgreSQL)")
    print("=" * 60)
    
    supabase = create_client(
        os.getenv('SUPABASE_URL'),
        os.getenv('SUPABASE_SERVICE_ROLE_KEY')
    )
    
    # RAG Projects
    projects = supabase.table('rag_projects').select('id, name, qdrant_collection, document_count, chunk_count').execute()
    print(f"\nRAG Projects: {len(projects.data)}")
    for p in projects.data:
        print(f"  {p['id'][:8]}... - {p['name']}")
        print(f"    Collection: {p['qdrant_collection']}")
        print(f"    Documents: {p['document_count']}, Chunks: {p['chunk_count']}")
    
    # Documents
    docs = supabase.table('documents').select('id, rag_project_id, filename, status, r2_input_key').execute()
    print(f"\nDocuments: {len(docs.data)}")
    by_status = {}
    by_project = {}
    for d in docs.data:
        status = d['status']
        pid = d['rag_project_id']
        by_status[status] = by_status.get(status, 0) + 1
        by_project[pid] = by_project.get(pid, 0) + 1
    
    print("  By status:")
    for status, count in sorted(by_status.items()):
        print(f"    {status}: {count}")
    
    print("  By project:")
    for pid, count in sorted(by_project.items()):
        print(f"    {pid[:8]}...: {count} documents")


if __name__ == "__main__":
    check_r2()
    check_qdrant()
    check_supabase()
