#!/usr/bin/env python3
"""Check R2 JSON structure."""

import json
import boto3
import os
from dotenv import load_dotenv

load_dotenv()

r2 = boto3.client('s3',
    endpoint_url=f'https://{os.environ["CLOUDFLARE_ACCOUNT_ID"]}.r2.cloudflarestorage.com',
    aws_access_key_id=os.environ['R2_ACCESS_KEY_ID'],
    aws_secret_access_key=os.environ['R2_SECRET_ACCESS_KEY'],
    region_name='auto'
)

with open('evaluation/matched_studies_r2.json') as f:
    data = json.load(f)

key = data[0]['r2_key']
print(f'Key: {key}')

resp = r2.get_object(Bucket='devchat-pdfs', Key=key)
doc = json.loads(resp['Body'].read())
print(f'Keys: {list(doc.keys())}')

# Check for content
for k in doc.keys():
    if isinstance(doc[k], str):
        print(f'  {k}: {len(doc[k])} chars')
    else:
        print(f'  {k}: {type(doc[k]).__name__}')
