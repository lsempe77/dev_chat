"""Quick R2 check script."""
import os
import re
import boto3
from dotenv import load_dotenv

load_dotenv()

# Check env vars
print("R2 Configuration:")
cf_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "NOT SET")
r2_key = os.environ.get("R2_ACCESS_KEY_ID", "NOT SET")
r2_secret = os.environ.get("R2_SECRET_ACCESS_KEY", "")

# Test connection
client = boto3.client(
    's3',
    endpoint_url=f"https://{cf_id}.r2.cloudflarestorage.com",
    aws_access_key_id=r2_key,
    aws_secret_access_key=r2_secret
)

print("\nListing all JSON outputs:")
response = client.list_objects_v2(
    Bucket='devchat-pdfs', 
    Prefix='rags/0816e8d3-ab23-417c-bf3f-e45531411c73/outputs/json/',
    MaxKeys=200
)

# Extract study IDs
study_ids = []
for obj in response.get('Contents', []):
    fname = obj['Key'].split('/')[-1]
    # Extract numeric ID if present (9 digits)
    match = re.search(r'_(\d{9})(?:_|\.)', fname)
    if match:
        study_ids.append(match.group(1))

study_ids = list(set(study_ids))  # Dedupe
print(f"Found {len(study_ids)} studies with numeric IDs")
print("Study IDs:")
for sid in sorted(study_ids):
    print(f"  {sid}")
