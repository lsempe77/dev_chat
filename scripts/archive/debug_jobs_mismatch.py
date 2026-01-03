"""Debug the mismatch between Processing tab and Documents tab counts."""
from qdrant_client import QdrantClient
import boto3
import os
from dotenv import load_dotenv
load_dotenv()

# Get R2 doc_ids (how jobs.py extracts them - WITHOUT .pdf)
s3 = boto3.client('s3', endpoint_url='https://'+os.environ['R2_ACCOUNT_ID']+'.r2.cloudflarestorage.com', 
                  aws_access_key_id=os.environ['R2_ACCESS_KEY_ID'], 
                  aws_secret_access_key=os.environ['R2_SECRET_ACCESS_KEY'], region_name='auto')

r2_doc_ids = set()
ct = None
while True:
    kw = {'Bucket': 'devchat-pdfs', 'Prefix': 'input-pdfs/'}
    if ct: kw['ContinuationToken'] = ct
    r = s3.list_objects_v2(**kw)
    for o in r.get('Contents', []):
        key = o['Key']
        if key.endswith('.pdf'):
            doc_id = key.split('/')[-1].rsplit('.', 1)[0]  # WITHOUT .pdf
            r2_doc_ids.add(doc_id)
    if r.get('IsTruncated'): ct = r['NextContinuationToken']
    else: break

print("="*60)
print("JOBS.PY (Processing Tab) - DOC_ID FORMAT MISMATCH")
print("="*60)
print(f"\nR2 doc_id format (WITHOUT .pdf): {len(r2_doc_ids)} files")
for d in list(r2_doc_ids)[:2]:
    print(f'  "{d}"')

# Get Qdrant doc_ids 
c = QdrantClient(url=os.environ['QDRANT_URL'], api_key=os.environ['QDRANT_API_KEY'])
qdrant_doc_ids = set()
offset = None
while True:
    pts, offset = c.scroll('devchat_v2', limit=1000, offset=offset, with_payload=['doc_id', 'pdf_name'])
    for p in pts:
        doc_id = p.payload.get('doc_id') or p.payload.get('pdf_name')
        if doc_id:
            qdrant_doc_ids.add(doc_id)
    if offset is None: break

print(f"\nQdrant doc_id format (WITH .pdf): {len(qdrant_doc_ids)} unique")
for d in list(qdrant_doc_ids)[:2]:
    print(f'  "{d}"')

# Check matches
matches_direct = r2_doc_ids & qdrant_doc_ids
print(f"\nDirect matches (r2 ∩ qdrant): {len(matches_direct)}")

# Check with normalization
qdrant_normalized = {d[:-4] if d.endswith('.pdf') else d for d in qdrant_doc_ids}
matches_normalized = r2_doc_ids & qdrant_normalized
print(f"Normalized matches (strip .pdf): {len(matches_normalized)}")

print(f"\n🐛 BUG: jobs.py shows {len(r2_doc_ids) - len(matches_direct)} as 'queued'")
print(f"   ACTUAL missing: {len(r2_doc_ids) - len(matches_normalized)}")
