#!/usr/bin/env python3
"""Show sample MineRU output."""
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

r2_key = studies[0]['r2_key']
print(f'R2 Key: {r2_key}')
print()

response = s3.get_object(Bucket='devchat-pdfs', Key=r2_key)
content = response['Body'].read().decode('utf-8')

# Show structure
lines = content.split('\n')
print(f'Total lines: {len(lines)}')
print()

# Show first 5000 chars
print('='*80)
print('FIRST 5000 CHARS:')
print('='*80)
print(content[:5000])

print()
print('='*80)
print('SEARCHING FOR "Table 1" context (2000 chars):')
print('='*80)
import re
match = re.search(r'.{500}Table 1.{1500}', content, re.DOTALL)
if match:
    print(match.group())
