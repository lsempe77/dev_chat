"""Analyze SKIP tables from v3 classifier to verify they're truly skippable."""
import json
import os
import boto3
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

# Load document
account_id = os.environ.get('CLOUDFLARE_ACCOUNT_ID')
r2 = boto3.client('s3',
    endpoint_url=f'https://{account_id}.r2.cloudflarestorage.com',
    aws_access_key_id=os.environ.get('R2_ACCESS_KEY_ID'),
    aws_secret_access_key=os.environ.get('R2_SECRET_ACCESS_KEY'),
)
BUCKET = 'devchat-pdfs'
key = 'rags/0816e8d3-ab23-417c-bf3f-e45531411c73/outputs/json/1f44cd8c70b8_PDFs_of_included_programs_121058367.json'
obj = r2.get_object(Bucket=BUCKET, Key=key)
doc = json.loads(obj['Body'].read().decode('utf-8'))

# All SKIP indices from our results
skip_indices = [0, 1, 2, 3, 9, 11, 18, 21, 26, 29, 31, 36, 38, 42, 44, 46, 52, 54, 
                64, 66, 68, 70, 72, 74, 76, 78, 82, 84, 86, 89, 91, 94, 96, 107, 
                109, 121, 124, 133, 138, 142, 146, 150, 156, 163, 165]

print(f"Analyzing {len(skip_indices)} SKIP tables\n")
print("=" * 80)

categories = {
    'truly_empty': [],
    'response_codes': [],
    'glossary': [],
    'has_numbers_no_stars': [],
    'has_stars_MISCLASSIFIED': [],
    'has_se_MISCLASSIFIED': [],
    'other': []
}

for idx in skip_indices:
    table = doc['tables'][idx]
    body = table.get('table_body', '')
    caption = table.get('table_caption', [])
    page = table.get('page_idx', -1)
    
    # Parse HTML
    soup = BeautifulSoup(body, 'html.parser') if body else None
    text = soup.get_text(separator=' ', strip=True) if soup else ""
    rows = soup.find_all('tr') if soup else []
    
    # Check characteristics
    has_stars = bool('*' in text and any(c.isdigit() for c in text))
    has_se = bool(any(x in text for x in ['(0.', '(.0', '[0.']))
    has_numbers = bool(any(c.isdigit() for c in text))
    is_empty = len(text) < 10
    has_response_codes = any(x in text.lower() for x in ['-99', '-98', '-97', 'not applicable', 'don\'t know', 'refused'])
    has_glossary = any(x in text.lower() for x in ['glossary', 'definition', 'abbreviation', 'acronym'])
    
    print(f"\n=== INDEX {idx} (page {page}) ===")
    print(f"Caption: {' '.join(caption)[:80] if caption else '[None]'}")
    print(f"Rows: {len(rows)}, Text length: {len(text)}")
    print(f"Has stars: {has_stars}, Has SE: {has_se}, Has numbers: {has_numbers}")
    print(f"Body sample: {text[:300]}")
    
    # Categorize
    if is_empty:
        categories['truly_empty'].append(idx)
        print(">>> CATEGORY: Truly empty")
    elif has_stars and has_se:
        categories['has_se_MISCLASSIFIED'].append(idx)
        print(">>> CATEGORY: ⚠️ HAS STARS + SE - LIKELY MISCLASSIFIED!")
    elif has_stars:
        categories['has_stars_MISCLASSIFIED'].append(idx)
        print(">>> CATEGORY: ⚠️ HAS STARS - MIGHT BE MISCLASSIFIED")
    elif has_response_codes:
        categories['response_codes'].append(idx)
        print(">>> CATEGORY: Response codes (correct SKIP)")
    elif has_glossary:
        categories['glossary'].append(idx)
        print(">>> CATEGORY: Glossary/definitions (correct SKIP)")
    elif has_numbers:
        categories['has_numbers_no_stars'].append(idx)
        print(">>> CATEGORY: Has numbers but no stars - needs review")
    else:
        categories['other'].append(idx)
        print(">>> CATEGORY: Other")

print("\n" + "=" * 80)
print("SUMMARY")
print("=" * 80)
for cat, indices in categories.items():
    print(f"\n{cat}: {len(indices)}")
    if indices:
        print(f"  Indices: {indices}")
