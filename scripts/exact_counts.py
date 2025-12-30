"""Get exact counts across all systems with detailed breakdown."""
from qdrant_client import QdrantClient
import boto3
import os
from dotenv import load_dotenv
load_dotenv()

print('='*60)
print('EXACT COUNTS ACROSS ALL SYSTEMS')
print('='*60)

# 1. R2 Input PDFs
s3 = boto3.client('s3', endpoint_url='https://'+os.environ['R2_ACCOUNT_ID']+'.r2.cloudflarestorage.com', 
                  aws_access_key_id=os.environ['R2_ACCESS_KEY_ID'], 
                  aws_secret_access_key=os.environ['R2_SECRET_ACCESS_KEY'], region_name='auto')

r2_input = set()
r2_output = set()
ct = None
while True:
    kw = {'Bucket': 'devchat-pdfs', 'Prefix': 'input-pdfs/'}
    if ct: kw['ContinuationToken'] = ct
    r = s3.list_objects_v2(**kw)
    for o in r.get('Contents', []):
        if o['Key'].endswith('.pdf'):
            r2_input.add(o['Key'].split('/')[-1].rsplit('.', 1)[0])
    if r.get('IsTruncated'): ct = r['NextContinuationToken']
    else: break

ct = None
while True:
    kw = {'Bucket': 'devchat-pdfs', 'Prefix': 'outputs/json/'}
    if ct: kw['ContinuationToken'] = ct
    r = s3.list_objects_v2(**kw)
    for o in r.get('Contents', []):
        r2_output.add(o['Key'].split('/')[-1].rsplit('.', 1)[0])
    if r.get('IsTruncated'): ct = r['NextContinuationToken']
    else: break

print(f'[R2] Input PDFs:     {len(r2_input)}')
print(f'[R2] Output JSONs:   {len(r2_output)}')
print(f'[R2] Not processed:  {len(r2_input - r2_output)}')

# 2. Qdrant - get ALL unique identifiers
c = QdrantClient(url=os.environ['QDRANT_URL'], api_key=os.environ['QDRANT_API_KEY'])

qdrant_doc_ids = set()
qdrant_pdf_names = set()
offset = None
total_points = 0
while True:
    pts, offset = c.scroll('devchat_v2', limit=1000, offset=offset, with_payload=['doc_id', 'pdf_name'])
    total_points += len(pts)
    for p in pts:
        if p.payload.get('doc_id'):
            qdrant_doc_ids.add(p.payload['doc_id'])
        if p.payload.get('pdf_name'):
            qdrant_pdf_names.add(p.payload['pdf_name'])
    if offset is None: break

print(f'\n[Qdrant] Total points:        {total_points}')
print(f'[Qdrant] Unique doc_id:       {len(qdrant_doc_ids)}')
print(f'[Qdrant] Unique pdf_name:     {len(qdrant_pdf_names)}')

# 3. Check format differences
print('\n[Format Analysis]')
doc_ids_with_pdf = [d for d in qdrant_doc_ids if d.endswith('.pdf')]
doc_ids_without_pdf = [d for d in qdrant_doc_ids if not d.endswith('.pdf')]
print(f'  doc_id WITH .pdf:    {len(doc_ids_with_pdf)}')
print(f'  doc_id WITHOUT .pdf: {len(doc_ids_without_pdf)}')

pdf_names_with_pdf = [d for d in qdrant_pdf_names if d.endswith('.pdf')]
pdf_names_without_pdf = [d for d in qdrant_pdf_names if not d.endswith('.pdf')]
print(f'  pdf_name WITH .pdf:    {len(pdf_names_with_pdf)}')
print(f'  pdf_name WITHOUT .pdf: {len(pdf_names_without_pdf)}')

# 4. Normalize and compare
qdrant_normalized = set()
for d in qdrant_doc_ids:
    qdrant_normalized.add(d[:-4] if d.endswith('.pdf') else d)
for d in qdrant_pdf_names:
    qdrant_normalized.add(d[:-4] if d.endswith('.pdf') else d)

print(f'\n[Normalized] Unique docs in Qdrant: {len(qdrant_normalized)}')

# 5. Match with R2
in_r2_and_qdrant = r2_input & qdrant_normalized
in_r2_not_qdrant = r2_input - qdrant_normalized
in_qdrant_not_r2 = qdrant_normalized - r2_input

print(f'\n[Cross-check]')
print(f'  In R2 AND Qdrant:    {len(in_r2_and_qdrant)}')
print(f'  In R2, NOT Qdrant:   {len(in_r2_not_qdrant)} (never indexed)')
print(f'  In Qdrant, NOT R2:   {len(in_qdrant_not_r2)} (orphaned)')

if in_r2_not_qdrant:
    print('\n  PDFs never indexed:')
    for d in sorted(in_r2_not_qdrant):
        print(f'    {d}')

if in_qdrant_not_r2:
    print('\n  Orphaned in Qdrant (no R2 source):')
    for d in sorted(in_qdrant_not_r2):
        print(f'    {d}')
