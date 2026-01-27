"""List PDFs in a RAG project's R2 folder."""
import boto3
import os
from dotenv import load_dotenv
load_dotenv()

r2 = boto3.client(
    's3',
    endpoint_url=f"https://{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
    aws_access_key_id=os.environ['R2_ACCESS_KEY_ID'],
    aws_secret_access_key=os.environ['R2_SECRET_ACCESS_KEY'],
)

bucket = os.environ.get('R2_BUCKET', 'devchat-pdfs')
project_id = '0816e8d3-ab23-417c-bf3f-e45531411c73'

# Check for PDFs in project folder
prefix = f'rags/{project_id}/input-pdfs/'
response = r2.list_objects_v2(Bucket=bucket, Prefix=prefix, MaxKeys=100)

print(f'PDFs in project ({prefix}):')
pdfs = response.get('Contents', [])
print(f'  Found {len(pdfs)} PDFs')
for obj in pdfs[:10]:
    print(f"  - {obj['Key'].split('/')[-1]}")
if len(pdfs) > 10:
    print(f'  ... and {len(pdfs) - 10} more')
