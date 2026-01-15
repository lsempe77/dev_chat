"""Check R2 document sizes"""
import boto3
import os
from dotenv import load_dotenv

load_dotenv()

s3 = boto3.client(
    's3',
    endpoint_url=f'https://{os.environ["CLOUDFLARE_ACCOUNT_ID"]}.r2.cloudflarestorage.com',
    aws_access_key_id=os.environ['R2_ACCESS_KEY_ID'],
    aws_secret_access_key=os.environ['R2_SECRET_ACCESS_KEY']
)

response = s3.list_objects_v2(Bucket='devchat-pdfs', Prefix='markdown/')
if 'Contents' not in response:
    print("No markdown files found in R2")
    exit()

objs = response['Contents']
sizes = [o['Size'] for o in objs if o['Key'].endswith('.md')]

if not sizes:
    print("No .md files found")
    exit()

print(f'Files: {len(sizes)}')
print(f'Avg: {sum(sizes)/len(sizes)/1000:.0f}K chars')
print(f'Max: {max(sizes)/1000:.0f}K chars')
print(f'Min: {min(sizes)/1000:.0f}K chars')
print(f'Median: {sorted(sizes)[len(sizes)//2]/1000:.0f}K chars')
print(f'\n25K limit loses {(sum(sizes) - 25000*len(sizes))/sum(sizes)*100:.1f}% of content on average')
