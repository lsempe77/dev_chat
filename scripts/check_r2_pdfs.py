#!/usr/bin/env python
"""Check how many PDFs are in the R2 bucket vs. how many studies are in Qdrant."""

import boto3
import os
from dotenv import load_dotenv
from qdrant_client import QdrantClient
from pathlib import Path

load_dotenv()

# Connect to R2
s3 = boto3.client(
    "s3",
    endpoint_url=f"https://{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
    aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
    aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
    region_name="auto",
)
bucket = os.environ.get("R2_BUCKET_NAME", "devchat-pdfs")

# List all PDFs in R2
pdfs = []
continuation_token = None
while True:
    kwargs = {"Bucket": bucket, "Prefix": "input-pdfs/"}
    if continuation_token:
        kwargs["ContinuationToken"] = continuation_token
    resp = s3.list_objects_v2(**kwargs)
    if "Contents" in resp:
        pdfs.extend([o["Key"] for o in resp["Contents"] if o["Key"].lower().endswith(".pdf")])
    if resp.get("IsTruncated"):
        continuation_token = resp["NextContinuationToken"]
    else:
        break

print(f"📁 R2 Bucket: {len(pdfs)} PDFs in input-pdfs/")

# Check Qdrant for unique study_ids
qdrant = QdrantClient(
    url=os.environ["QDRANT_URL"],
    api_key=os.environ["QDRANT_API_KEY"],
)

# Get all unique study_ids by scrolling through all points
study_ids = set()
pdf_names_in_qdrant = set()
offset = None
total_chunks = 0

while True:
    result = qdrant.scroll(
        collection_name="devchat_v2",
        limit=1000,
        offset=offset,
        with_payload=True,
    )
    points, offset = result
    if not points:
        break
    total_chunks += len(points)
    for p in points:
        study_ids.add(p.payload.get("study_id", "unknown"))
        pdf_names_in_qdrant.add(p.payload.get("pdf_name", "unknown"))
    if offset is None:
        break

print(f"🔍 Qdrant: {total_chunks} chunks, {len(study_ids)} unique study_ids")
print(f"🔍 Qdrant: {len(pdf_names_in_qdrant)} unique pdf_names")

# Find which R2 PDFs are missing from Qdrant
r2_pdf_names = {Path(p).stem for p in pdfs}
missing = r2_pdf_names - pdf_names_in_qdrant
extra = pdf_names_in_qdrant - r2_pdf_names

print(f"\n⚠️ Missing from Qdrant ({len(missing)} PDFs not indexed):")
for name in sorted(missing)[:20]:
    print(f"   - {name}")
if len(missing) > 20:
    print(f"   ... and {len(missing) - 20} more")

if extra:
    print(f"\n⚠️ In Qdrant but not in R2 ({len(extra)} extra):")
    for name in sorted(extra)[:10]:
        print(f"   - {name}")
