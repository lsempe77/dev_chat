"""
Inventory ALL tables from MineRU JSONs to check for false negatives.
This shows what tables exist vs what we extracted.
"""
import json
import boto3
import os
import re
from pathlib import Path
from dotenv import load_dotenv
import pandas as pd

load_dotenv()

# R2 setup - use same config as storage.py
account_id = os.environ.get('CLOUDFLARE_ACCOUNT_ID')
if not account_id:
    raise ValueError("CLOUDFLARE_ACCOUNT_ID environment variable not set")

r2 = boto3.client(
    's3',
    endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
    aws_access_key_id=os.environ.get('R2_ACCESS_KEY_ID'),
    aws_secret_access_key=os.environ.get('R2_SECRET_ACCESS_KEY'),
)
BUCKET = 'devchat-pdfs'
PROJECT_ID = '0816e8d3-ab23-417c-bf3f-e45531411c73'
JSON_PREFIX = f'rags/{PROJECT_ID}/outputs/json/'


def list_all_jsons():
    """List all MineRU JSON files in R2."""
    paginator = r2.get_paginator('list_objects_v2')
    files = []
    for page in paginator.paginate(Bucket=BUCKET, Prefix=JSON_PREFIX):
        for obj in page.get('Contents', []):
            if obj['Key'].endswith('.json'):
                files.append(obj['Key'])
    return files


def load_json(key: str) -> dict:
    """Load a JSON file from R2."""
    response = r2.get_object(Bucket=BUCKET, Key=key)
    return json.loads(response['Body'].read().decode('utf-8'))


def extract_study_id(key: str) -> str:
    """Extract study ID from R2 key."""
    filename = key.split('/')[-1].replace('.json', '')
    # Remove hash prefix if present
    if '_' in filename:
        parts = filename.split('_', 1)
        if len(parts[0]) == 12 and all(c in '0123456789abcdef' for c in parts[0]):
            return filename  # Keep full name for BRAC studies
    return filename


def fix_ocr_spacing(text: str) -> str:
    """Fix OCR-induced character spacing issues."""
    if not text:
        return text
    if re.search(r'[Tt]\s*a\s+b\s+l\s+e', text):
        result = re.sub(r'\s+', '', text)
        result = re.sub(r'([a-z])([A-Z])', r'\1 \2', result)
        result = re.sub(r':(?=[A-Za-z0-9])', ': ', result)
        result = re.sub(r'(Table)(\d)', r'\1 \2', result)
        return result
    return text


def extract_caption_from_body(html: str) -> str:
    """Try to extract table caption from body HTML when caption field is empty."""
    if not html:
        return ''
    
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, 'html.parser')
    text = soup.get_text(separator=' ', strip=True)
    
    # Look for "Table X:" or "Table X." pattern at the start
    match = re.search(r'^(Table\s+[\d\.]+[a-z]?[:\.]?\s*[^0-9]{0,100})', text, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    
    return ''


def has_coefficient_pattern(html: str) -> bool:
    """Check if table body has coefficient patterns (numbers with stars and parens)."""
    if not html:
        return False
    
    # Look for patterns like "0.103***" or "-0.15 (0.05)"
    if re.search(r'-?\d+\.\d+\s*\*{1,3}', html):
        return True
    if re.search(r'\(\d+\.\d+\)', html):
        return True
    return False


def classify_caption_simple(caption: str, html: str = '') -> str:
    """Simple caption classification for inventory purposes."""
    caption_lower = caption.lower()
    
    # Results indicators
    results_keywords = [
        'impact', 'effect', 'treatment effect', 'regression', 'coefficient', 
        'estimate', 'itt', 'ate', 'did', 'difference-in-diff',
        # Spanish
        'impacto', 'efecto', 'coeficiente',
        # Portuguese
        'efeito',
    ]
    if any(kw in caption_lower for kw in results_keywords):
        return 'likely_results'
    
    # Descriptive indicators
    descriptive_keywords = ['balance', 'baseline characteristic', 'summary statistic', 
                           'sample size', 'number of', 'attrition', 'compliance',
                           'variable definition', 'description of', 'descriptive']
    if any(kw in caption_lower for kw in descriptive_keywords):
        return 'likely_descriptive'
    
    # If no caption but has coefficient patterns, likely results
    if not caption or caption == '[No caption]':
        if has_coefficient_pattern(html):
            return 'likely_results_no_caption'
    
    return 'unknown'


def main():
    print("Inventorying ALL tables from MineRU JSONs...")
    print("=" * 80)
    
    json_files = list_all_jsons()
    print(f"Found {len(json_files)} JSON files")
    
    all_tables = []
    
    for i, key in enumerate(json_files):
        study_id = extract_study_id(key)
        print(f"\r[{i+1}/{len(json_files)}] Processing {study_id[:50]}...", end='', flush=True)
        
        try:
            doc = load_json(key)
            tables = doc.get('tables', [])
            
            for j, table in enumerate(tables):
                caption_raw = ' '.join(table.get('table_caption', []))
                caption = fix_ocr_spacing(caption_raw)
                html_body = table.get('table_body', '')
                
                # If no caption, try to extract from body
                if not caption:
                    caption = extract_caption_from_body(html_body)
                
                final_caption = caption[:200] if caption else '[No caption]'
                
                all_tables.append({
                    'study_id': study_id,
                    'table_index': j,
                    'table_id': f"Table{j+1}",
                    'caption': final_caption,
                    'likely_type': classify_caption_simple(final_caption, html_body),
                    'has_html': bool(html_body),
                    'has_coefficients': has_coefficient_pattern(html_body),
                })
        except Exception as e:
            print(f"\nError processing {study_id}: {e}")
    
    print(f"\n\nTotal tables found: {len(all_tables)}")
    
    # Create DataFrame
    df = pd.DataFrame(all_tables)
    
    # Save to CSV
    output_path = Path('extraction_pipeline/outputs/all_tables_inventory.csv')
    df.to_csv(output_path, index=False)
    print(f"Saved inventory to: {output_path}")
    
    # Summary stats
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Total studies: {df['study_id'].nunique()}")
    print(f"Total tables: {len(df)}")
    print(f"\nBy likely type:")
    print(df['likely_type'].value_counts())
    
    # Show likely results tables
    likely_results = df[df['likely_type'] == 'likely_results']
    print(f"\n\nLIKELY RESULTS TABLES ({len(likely_results)}):")
    print("-" * 80)
    for _, row in likely_results.head(30).iterrows():
        print(f"  {row['study_id'][:30]:30} | {row['table_id']:8} | {row['caption'][:50]}")
    
    # Show likely descriptive tables
    likely_desc = df[df['likely_type'] == 'likely_descriptive']
    print(f"\n\nLIKELY DESCRIPTIVE TABLES ({len(likely_desc)}):")
    print("-" * 80)
    for _, row in likely_desc.head(30).iterrows():
        print(f"  {row['study_id'][:30]:30} | {row['table_id']:8} | {row['caption'][:50]}")
    
    # Show unknown tables (need LLM classification)
    unknown = df[df['likely_type'] == 'unknown']
    print(f"\n\nUNKNOWN TABLES ({len(unknown)}) - need LLM classification:")
    print("-" * 80)
    for _, row in unknown.head(30).iterrows():
        print(f"  {row['study_id'][:30]:30} | {row['table_id']:8} | {row['caption'][:50]}")
    
    return df


if __name__ == "__main__":
    main()
