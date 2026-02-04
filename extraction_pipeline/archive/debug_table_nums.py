"""Debug script to see if table numbers appear in HTML body."""
import json
import boto3
import os
import re
from dotenv import load_dotenv
from bs4 import BeautifulSoup

load_dotenv()

account_id = os.environ.get('CLOUDFLARE_ACCOUNT_ID')
r2 = boto3.client('s3',
    endpoint_url=f'https://{account_id}.r2.cloudflarestorage.com',
    aws_access_key_id=os.environ.get('R2_ACCESS_KEY_ID'),
    aws_secret_access_key=os.environ.get('R2_SECRET_ACCESS_KEY'),
)
BUCKET = 'devchat-pdfs'

key = 'rags/0816e8d3-ab23-417c-bf3f-e45531411c73/outputs/json/1f44cd8c70b8_PDFs_of_included_programs_121058367.json'
response = r2.get_object(Bucket=BUCKET, Key=key)
doc = json.loads(response['Body'].read().decode('utf-8'))

tables = doc.get('tables', [])

# Check if table numbers are in the HTML body
print('='*80)
print('TABLES WITH/WITHOUT TABLE NUMBERS IN BODY:')
print('='*80)

for i, table in enumerate(tables[:50]):
    caption = ' '.join(table.get('table_caption', [])).strip()
    body = table.get('table_body', '')
    page = table.get('page_idx', -1)
    
    # Extract text from HTML
    soup = BeautifulSoup(body, 'html.parser')
    text = soup.get_text(separator=' ', strip=True)
    
    # Check for Table X.Y in body
    table_num_match = re.search(r'Table\s+([\d\.]+[a-z]?)', text[:300], re.IGNORECASE)
    table_num = table_num_match.group(1) if table_num_match else None
    
    status = 'HAS CAP' if caption and len(caption) > 10 else 'NO CAP'
    body_num = f'Body: Table {table_num}' if table_num else 'Body: ---'
    
    caption_preview = caption[:40] if caption else '[empty]'
    
    print(f'Table {i:2d} (page {page:3d}): {status:7s} | {body_num:20s} | {caption_preview}')
