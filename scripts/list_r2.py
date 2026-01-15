"""List R2 files."""
import os
import boto3
from dotenv import load_dotenv
load_dotenv()

account_id = os.environ['CLOUDFLARE_ACCOUNT_ID']
r2 = boto3.client('s3',
    endpoint_url=f'https://{account_id}.r2.cloudflarestorage.com',
    aws_access_key_id=os.environ['R2_ACCESS_KEY_ID'],
    aws_secret_access_key=os.environ['R2_SECRET_ACCESS_KEY'],
    region_name='auto'
)
bucket = os.environ.get('R2_BUCKET_NAME', 'devchat-pdfs')
print(f'Listing R2 bucket: {bucket}')

# Count files by type
paginator = r2.get_paginator('list_objects_v2')
json_files = []
md_files = []
pdf_files = []

for page in paginator.paginate(Bucket=bucket):
    for obj in page.get('Contents', []):
        key = obj['Key']
        if key.endswith('.json'):
            json_files.append(key)
        elif key.endswith('.md'):
            md_files.append(key)
        elif key.endswith('.pdf'):
            pdf_files.append(key)

print(f'PDFs: {len(pdf_files)}')
print(f'JSON outputs: {len(json_files)}')
print(f'Markdown outputs: {len(md_files)}')

# Show sample JSON files
print('\nSample JSON files:')
for f in json_files[:5]:
    fname = f.split("/")[-1]
    print(f'  {fname}')
