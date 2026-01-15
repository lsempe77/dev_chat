"""List objects in R2 bucket."""

import boto3
import os
from dotenv import load_dotenv
load_dotenv()

client = boto3.client(
    's3',
    endpoint_url=f"https://{os.environ['CLOUDFLARE_ACCOUNT_ID']}.r2.cloudflarestorage.com",
    aws_access_key_id=os.environ['R2_ACCESS_KEY_ID'],
    aws_secret_access_key=os.environ['R2_SECRET_ACCESS_KEY']
)

# List all objects
resp = client.list_objects_v2(Bucket='devchat-pdfs', MaxKeys=100)
print('Objects in bucket:')
for obj in resp.get('Contents', []):
    print(f"  {obj['Key']}")

# Check if there's a different pattern
print()
print("Looking for study IDs...")
seen_prefixes = set()
for obj in resp.get('Contents', []):
    key = obj['Key']
    prefix = key.split('/')[0]
    if prefix not in seen_prefixes:
        seen_prefixes.add(prefix)
        print(f"  Prefix: {prefix}")
