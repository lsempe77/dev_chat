"""Analyze SKIP tables to understand what they contain."""
import json
import boto3
import os
import pandas as pd
from dotenv import load_dotenv
from bs4 import BeautifulSoup

load_dotenv()

# Load the document
account_id = os.environ.get('CLOUDFLARE_ACCOUNT_ID')
r2 = boto3.client(
    's3',
    endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
    aws_access_key_id=os.environ.get('R2_ACCESS_KEY_ID'),
    aws_secret_access_key=os.environ.get('R2_SECRET_ACCESS_KEY'),
)
key = 'rags/0816e8d3-ab23-417c-bf3f-e45531411c73/outputs/json/1f44cd8c70b8_PDFs_of_included_programs_121058367.json'
obj = r2.get_object(Bucket='devchat-pdfs', Key=key)
doc = json.loads(obj['Body'].read().decode('utf-8'))
tables = doc.get('tables', [])

# Load classification results
df = pd.read_csv('extraction_pipeline/outputs/classification_v2_test.csv')
skip = df[df['classification'] == 'SKIP']

print("=" * 80)
print("ANALYSIS OF SKIP TABLES")
print("=" * 80)

# 1. Tables with captions that got SKIP
print("\n[1] SKIP tables WITH captions (should probably be RESULTS):")
print("-" * 60)
with_caption = skip[skip['caption'] != '[No caption]']
for _, row in with_caption.iterrows():
    idx = row['index']
    t = tables[idx]
    body = t.get('table_body', '')
    soup = BeautifulSoup(body, 'html.parser')
    text = soup.get_text(separator=' ', strip=True)[:150]
    
    # Check for results indicators
    has_stars = '*' in text
    has_se = bool(pd.notna(text) and ('(' in text and ')' in text))
    has_coef = any(x in text.lower() for x in ['coef', 'itt', 'ate', 'treatment'])
    
    print(f"\nIndex {idx}, Page {row['page']}: {row['table_number']}")
    print(f"  Caption: {row['caption'][:70]}...")
    print(f"  Body preview: {text[:100]}...")
    print(f"  Has stars: {has_stars}, Has SE pattern: {has_se}, Has coef terms: {has_coef}")

# 2. Tables WITHOUT captions - sample a few
print("\n\n[2] SKIP tables WITHOUT captions (sample):")
print("-" * 60)
no_caption = skip[skip['caption'] == '[No caption]']
for _, row in no_caption.head(10).iterrows():
    idx = row['index']
    t = tables[idx]
    body = t.get('table_body', '')
    soup = BeautifulSoup(body, 'html.parser')
    text = soup.get_text(separator=' ', strip=True)
    
    # Check for results indicators
    has_stars = '*' in text
    has_se = bool(pd.notna(text) and ('(' in text and ')' in text))
    has_numbers = bool(pd.notna(text) and any(c.isdigit() for c in text[:200]))
    
    print(f"\nIndex {idx}, Page {row['page']}: {row['table_number']}")
    print(f"  Body preview: {text[:150]}...")
    print(f"  Has stars: {has_stars}, Has SE pattern: {has_se}, Has numbers: {has_numbers}")

# 3. Summary
print("\n\n[3] SUMMARY:")
print("-" * 60)
print(f"Total SKIP: {len(skip)}")
print(f"  With caption: {len(with_caption)} (likely misclassified)")
print(f"  Without caption: {len(no_caption)} (need content analysis)")

# Check if no-caption tables have results-like content
results_indicators = 0
for _, row in no_caption.iterrows():
    idx = row['index']
    t = tables[idx]
    body = t.get('table_body', '')
    soup = BeautifulSoup(body, 'html.parser')
    text = soup.get_text(separator=' ', strip=True)
    
    if '*' in text or ('(' in text and ')' in text):
        results_indicators += 1

print(f"  No-caption tables with results indicators (*/SE): {results_indicators}")
