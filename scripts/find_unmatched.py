import json
import os
import boto3
from dotenv import load_dotenv
load_dotenv()

# Load ground truth
with open('evaluation/extraction_test_dataset.json') as f:
    gt = {item['study_id']: item['ground_truth'] for item in json.load(f)}

# Load matched
with open('evaluation/matched_studies_r2.json') as f:
    matched_ids = {item['study_id'] for item in json.load(f)}

# Find unmatched
unmatched = set(gt.keys()) - matched_ids
print(f'Unmatched studies ({len(unmatched)}):')
for sid in sorted(unmatched):
    info = gt[sid]
    author = info['author']
    year = info['year']
    country = info['country']
    print(f'  {sid}: {author} ({year}) - {country}')

# Search R2 for these authors
account_id = os.environ['CLOUDFLARE_ACCOUNT_ID']
r2 = boto3.client('s3',
    endpoint_url=f'https://{account_id}.r2.cloudflarestorage.com',
    aws_access_key_id=os.environ['R2_ACCESS_KEY_ID'],
    aws_secret_access_key=os.environ['R2_SECRET_ACCESS_KEY'],
    region_name='auto'
)
bucket = os.environ.get('R2_BUCKET_NAME', 'devchat-pdfs')

# Search for each unmatched author
for sid in unmatched:
    author = gt[sid]['author'].split()[0]  # First word of author
    year = gt[sid]['year']
    print(f'\nSearching R2 for: {author}')
    
    paginator = r2.get_paginator('list_objects_v2')
    for page in paginator.paginate(Bucket=bucket):
        for obj in page.get('Contents', []):
            key = obj['Key']
            if author in key and '.json' in key:
                fname = key.split("/")[-1]
                print(f'  FOUND: {fname}')
