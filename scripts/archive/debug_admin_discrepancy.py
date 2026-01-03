#!/usr/bin/env python
"""Debug admin endpoints to find discrepancies."""

import os
from dotenv import load_dotenv
load_dotenv()

# Check Qdrant directly
from qdrant_client import QdrantClient

print("=" * 60)
print("CHECKING DATA SOURCES FOR DISCREPANCIES")
print("=" * 60)

# 1. Qdrant
print("\n[1] QDRANT (Vector Database)")
try:
    c = QdrantClient(url=os.environ['QDRANT_URL'], api_key=os.environ['QDRANT_API_KEY'])
    info = c.get_collection('devchat_v2')
    print(f"  Points: {info.points_count}")
    
    # Count ALL unique doc_ids (scroll through entire collection)
    doc_ids = set()
    offset = None
    while True:
        pts, offset = c.scroll('devchat_v2', limit=1000, offset=offset, with_payload=['doc_id'])
        for p in pts:
            if p.payload.get('doc_id'):
                doc_ids.add(p.payload['doc_id'])
        if offset is None:
            break
    print(f"  Unique doc_ids: {len(doc_ids)}")
except Exception as e:
    print(f"  ERROR: {e}")

# 2. R2 (Cloudflare Storage)
print("\n[2] R2 (Cloud Storage)")
try:
    import boto3
    s3 = boto3.client(
        "s3",
        endpoint_url=f"https://{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )
    bucket = os.environ.get("R2_BUCKET_NAME", "devchat-pdfs")
    
    # Count input PDFs
    input_pdfs = []
    cont_token = None
    while True:
        kwargs = {"Bucket": bucket, "Prefix": "input-pdfs/"}
        if cont_token:
            kwargs["ContinuationToken"] = cont_token
        resp = s3.list_objects_v2(**kwargs)
        if "Contents" in resp:
            input_pdfs.extend([o["Key"] for o in resp["Contents"] if o["Key"].lower().endswith(".pdf")])
        if resp.get("IsTruncated"):
            cont_token = resp["NextContinuationToken"]
        else:
            break
    print(f"  Input PDFs: {len(input_pdfs)}")
    
    # Count processed outputs
    outputs = []
    cont_token = None
    while True:
        kwargs = {"Bucket": bucket, "Prefix": "outputs/json/"}
        if cont_token:
            kwargs["ContinuationToken"] = cont_token
        resp = s3.list_objects_v2(**kwargs)
        if "Contents" in resp:
            outputs.extend([o["Key"] for o in resp["Contents"]])
        if resp.get("IsTruncated"):
            cont_token = resp["NextContinuationToken"]
        else:
            break
    print(f"  Processed outputs (JSON): {len(outputs)}")
    
except Exception as e:
    print(f"  ERROR: {e}")

# 3. Turso (SQLite Database for metadata)
print("\n[3] TURSO (Metadata Database)")
try:
    import libsql_experimental as libsql
    
    turso_url = os.environ.get("TURSO_DATABASE_URL")
    turso_token = os.environ.get("TURSO_AUTH_TOKEN")
    
    if turso_url and turso_token:
        conn = libsql.connect(turso_url, auth_token=turso_token)
        
        # Count documents
        result = conn.execute("SELECT COUNT(*) FROM documents").fetchone()
        print(f"  Documents table: {result[0] if result else 'N/A'}")
        
        # Count processing jobs
        try:
            result = conn.execute("SELECT COUNT(*) FROM processing_jobs").fetchone()
            print(f"  Processing jobs: {result[0] if result else 'N/A'}")
        except:
            print("  Processing jobs: table not found")
        
        # Count by status
        try:
            result = conn.execute("SELECT status, COUNT(*) FROM documents GROUP BY status").fetchall()
            print(f"  By status: {dict(result)}")
        except:
            pass
    else:
        print("  No Turso credentials found")
except ImportError:
    print("  libsql not installed")
except Exception as e:
    print(f"  ERROR: {e}")

print("\n" + "=" * 60)
print("SUMMARY")
print("=" * 60)
