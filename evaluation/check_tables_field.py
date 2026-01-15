#!/usr/bin/env python3
"""Check if tables field exists in R2 output."""
import boto3
import os
import json
from dotenv import load_dotenv
load_dotenv()

s3 = boto3.client('s3',
    endpoint_url=f'https://{os.environ["CLOUDFLARE_ACCOUNT_ID"]}.r2.cloudflarestorage.com',
    aws_access_key_id=os.environ['R2_ACCESS_KEY_ID'],
    aws_secret_access_key=os.environ['R2_SECRET_ACCESS_KEY'])

with open('evaluation/matched_studies_r2.json') as f:
    studies = json.load(f)

# Check first 3 studies
for study in studies[:3]:
    r2_key = study['r2_key']
    print(f"="*80)
    print(f"R2 Key: {r2_key}")
    
    response = s3.get_object(Bucket='devchat-pdfs', Key=r2_key)
    data = json.loads(response['Body'].read().decode('utf-8'))
    
    print(f"Processed at: {data.get('processed_at', 'UNKNOWN')}")
    print(f"TOP-LEVEL KEYS: {list(data.keys())}")
    print()
    
    if 'tables' in data:
        print(f"TABLES COUNT: {len(data['tables'])}")
        if data['tables']:
            print("FIRST TABLE SAMPLE:")
            print(json.dumps(data['tables'][0], indent=2)[:1500])
    else:
        print("NO TABLES FIELD FOUND!")
    print()
