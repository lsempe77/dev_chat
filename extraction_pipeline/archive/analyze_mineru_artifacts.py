"""Analyze MinerU parsing artifacts to understand patterns."""
import boto3
import os
import json
from dotenv import load_dotenv
from bs4 import BeautifulSoup

load_dotenv()

# Connect to R2
account_id = os.environ.get('CLOUDFLARE_ACCOUNT_ID')
r2 = boto3.client(
    's3',
    endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
    aws_access_key_id=os.environ.get('R2_ACCESS_KEY_ID'),
    aws_secret_access_key=os.environ.get('R2_SECRET_ACCESS_KEY'),
)

# Load the sample document with known issues
key = 'rags/0816e8d3-ab23-417c-bf3f-e45531411c73/outputs/json/076ec917aab5_PDFs_of_included_programs_121378172_Gilligan_(2024).json'
obj = r2.get_object(Bucket='devchat-pdfs', Key=key)
doc = json.loads(obj['Body'].read().decode('utf-8'))

print("=" * 80)
print("MINERU JSON STRUCTURE ANALYSIS")
print("=" * 80)

# Analyze document structure
print(f"\nTop-level keys: {doc.keys()}")

# Check for tables in different possible locations
if 'pdf_info' in doc:
    print(f"\npdf_info length: {len(doc.get('pdf_info', []))}")
    pdf_info = doc.get('pdf_info', [])
    tables = [e for e in pdf_info if e.get('type') == 'table']
elif 'tables' in doc:
    print(f"\n'tables' key found with {len(doc['tables'])} items")
    tables = doc['tables']
else:
    print("\nLooking for tables in structure...")
    tables = []

# If tables is a list of dicts with 'table_body'
if tables and isinstance(tables[0], dict):
    print(f"\nFirst table keys: {tables[0].keys()}")
print(f"\n\nTotal tables: {len(tables)}")
print(f"\nKeys in table element: {tables[0].keys() if tables else 'None'}")

# Look at the problematic tables (indices 1, 2, 3, 4 from the ground truth)
print("\n" + "=" * 80)
print("PROBLEMATIC TABLES ANALYSIS")
print("=" * 80)

problematic_indices = [1, 2, 3, 4]  # From ground truth review

for idx in problematic_indices:
    if idx < len(tables):
        t = tables[idx]
        print(f"\n--- TABLE {idx} ---")
        print(f"Page: {t.get('page_idx', '?')}")
        print(f"table_caption: {t.get('table_caption', 'NONE')[:100]}")
        
        # Parse HTML body
        html = t.get('table_body', '')
        soup = BeautifulSoup(html, 'html.parser') if html else None
        
        if soup:
            rows = soup.find_all('tr')
            print(f"Row count: {len(rows)}")
            
            # Show first few rows
            text = soup.get_text(separator=' ', strip=True)
            print(f"Text (first 200 chars): {text[:200]}")
        else:
            print("NO HTML BODY")
        
        # Show raw table_body snippet
        print(f"table_body (first 300 chars): {html[:300] if html else 'EMPTY'}")

# Analyze patterns in "bad" tables
print("\n\n" + "=" * 80)
print("PATTERN ANALYSIS FOR ARTIFACT DETECTION")
print("=" * 80)

# Count tables by characteristics
empty_body = 0
one_row = 0
caption_is_sentence = 0
caption_has_page_ref = 0
has_figure_in_caption = 0

for i, t in enumerate(tables):
    html = t.get('table_body', '')
    caption_list = t.get('table_caption', []) or []
    caption = caption_list[0] if caption_list else ''
    
    soup = BeautifulSoup(html, 'html.parser') if html else None
    rows = soup.find_all('tr') if soup else []
    
    if not html or html.strip() == '':
        empty_body += 1
    
    if len(rows) <= 1:
        one_row += 1
    
    # Caption is a sentence (has period mid-caption, not just at end)
    if '.' in caption[:-1] and len(caption) > 50:
        caption_is_sentence += 1
        if i < 30:  # Show first examples
            print(f"  Sentence caption [{i}]: {caption[:100]}...")
    
    # Caption has page reference like "...16" or ".....21"
    if '..' in caption or '...' in caption:
        caption_has_page_ref += 1
    
    # Figure mentioned
    if 'figure' in caption.lower() or 'fig.' in caption.lower():
        has_figure_in_caption += 1

print(f"\nEmpty body: {empty_body}")
print(f"≤1 row: {one_row}")
print(f"Caption is sentence (paragraph): {caption_is_sentence}")
print(f"Caption has page reference: {caption_has_page_ref}")
print(f"Figure in caption: {has_figure_in_caption}")

# Look for split tables (same table number appearing multiple times)
print("\n\n" + "=" * 80)
print("SPLIT TABLE DETECTION")
print("=" * 80)

import re

table_numbers = {}
for i, t in enumerate(tables):
    caption_list = t.get('table_caption', []) or []
    caption = caption_list[0] if caption_list else ''
    # Extract table number
    match = re.search(r'Table\s*(\d+\.?\d*[a-z]?)', caption, re.IGNORECASE)
    if match:
        num = match.group(1)
        if num not in table_numbers:
            table_numbers[num] = []
        table_numbers[num].append(i)

print("Tables appearing multiple times:")
for num, indices in sorted(table_numbers.items()):
    if len(indices) > 1:
        print(f"  Table {num}: indices {indices}")
