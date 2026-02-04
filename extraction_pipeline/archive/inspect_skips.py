"""Deep dive into questionable SKIP tables."""
import json
import os
import boto3
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()
account_id = os.environ.get('CLOUDFLARE_ACCOUNT_ID')
r2 = boto3.client('s3', endpoint_url=f'https://{account_id}.r2.cloudflarestorage.com',
    aws_access_key_id=os.environ.get('R2_ACCESS_KEY_ID'), 
    aws_secret_access_key=os.environ.get('R2_SECRET_ACCESS_KEY'))
doc = json.loads(r2.get_object(Bucket='devchat-pdfs', 
    Key='rags/0816e8d3-ab23-417c-bf3f-e45531411c73/outputs/json/1f44cd8c70b8_PDFs_of_included_programs_121058367.json')['Body'].read().decode('utf-8'))

# Tables to inspect
indices_to_check = [0, 26, 29, 31, 36, 38, 42, 52, 107, 121]

for idx in indices_to_check:
    table = doc['tables'][idx]
    body = table.get('table_body', '')
    soup = BeautifulSoup(body, 'html.parser') if body else None
    rows = soup.find_all('tr') if soup else []
    
    print(f'\n{"="*80}')
    print(f'INDEX {idx} (page {table.get("page_idx")})')
    print(f'{"="*80}')
    print(f'Caption: {table.get("table_caption", [])}')
    print(f'Total rows: {len(rows)}')
    
    # Print all rows
    for i, row in enumerate(rows[:15]):
        cells = [c.get_text(strip=True)[:50] for c in row.find_all(['td', 'th'])]
        print(f'  Row {i}: {" | ".join(cells)}')
    
    # Assessment
    text = soup.get_text() if soup else ""
    if 'ANCOVA' in text or 'abbreviation' in text.lower():
        print('\n>>> ASSESSMENT: Glossary/abbreviations table - CORRECT SKIP')
    elif len(rows) <= 2 and '(1)' in text:
        print('\n>>> ASSESSMENT: Header-only fragment (MinerU split table) - should be CONTINUATION or merged')
    elif 'Test:' in text or 'p-value' in text.lower():
        print('\n>>> ASSESSMENT: Statistical test p-values (not coefficients) - MAYBE SKIP')
    else:
        print('\n>>> ASSESSMENT: NEEDS MANUAL REVIEW')
