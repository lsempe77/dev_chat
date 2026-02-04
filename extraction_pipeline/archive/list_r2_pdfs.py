"""List all processed PDFs in R2 storage."""
import boto3
import os
from dotenv import load_dotenv

load_dotenv()

r2 = boto3.client(
    's3',
    endpoint_url=os.getenv('R2_ENDPOINT_URL'),
    aws_access_key_id=os.getenv('R2_ACCESS_KEY_ID'),
    aws_secret_access_key=os.getenv('R2_SECRET_ACCESS_KEY')
)

# List all RAG folders
result = r2.list_objects_v2(Bucket='devchat-pdfs', Prefix='rags/', Delimiter='/')
print('RAG folders:')
for p in result.get('CommonPrefixes', []):
    print(f"  {p['Prefix']}")

# List all JSON output files
print('\n\nJSON output files:')
paginator = r2.get_paginator('list_objects_v2')
json_files = []
for page in paginator.paginate(Bucket='devchat-pdfs', Prefix='rags/'):
    for obj in page.get('Contents', []):
        if obj['Key'].endswith('.json') and '/json/' in obj['Key']:
            json_files.append(obj['Key'])
            print(f"  {obj['Key']}")

print(f"\n\nTotal JSON files: {len(json_files)}")
