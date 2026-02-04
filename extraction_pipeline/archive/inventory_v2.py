"""
FIXED inventory - Extract table captions from content field when table_caption is empty.
"""
import json
import boto3
import os
import re
from pathlib import Path
from dotenv import load_dotenv
import pandas as pd
from bs4 import BeautifulSoup

load_dotenv()

# R2 setup
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
    return filename


def extract_captions_from_content(content: str) -> dict:
    """Extract all table captions from markdown content."""
    if not content:
        return {}
    
    # Pattern: "Table X.Y: Description" or "Table X.Y. Description"  
    # Also handle "Table X:" and variations
    patterns = [
        r'(Table\s+[\d\.]+[a-z]?)[:\.\s]+([A-Z][^\n\|]{5,200})',  # Table X.Y: Description starting with capital
        r'(Table\s+[\d\.]+[a-z]?)\s*:\s*([^\n\|]{5,200})',  # Table X: anything after colon
    ]
    
    captions = {}
    for pattern in patterns:
        matches = re.findall(pattern, content, re.IGNORECASE)
        for table_num, desc in matches:
            # Normalize table number
            table_num = re.sub(r'\s+', ' ', table_num.strip())
            desc = desc.strip()
            
            # Clean up description (remove page numbers, trailing dots)
            desc = re.sub(r'\.{2,}\s*\d+$', '', desc).strip()
            desc = re.sub(r'\s+\d+$', '', desc).strip()
            
            # Skip if too short or looks like a reference
            if len(desc) < 5:
                continue
            if desc.startswith('and ') or desc.startswith('shows '):
                continue
                
            # Keep longest description for each table
            if table_num not in captions or len(desc) > len(captions[table_num]):
                captions[table_num] = desc
    
    return captions


def match_table_to_caption(table_idx: int, tables: list, content_captions: dict) -> str:
    """Try to match a table to its caption from content."""
    table = tables[table_idx]
    
    # First check if table_caption field has content
    caption_list = table.get('table_caption', [])
    if caption_list:
        caption = ' '.join(caption_list).strip()
        if caption and len(caption) > 10:
            return caption
    
    # Try to find caption by looking at nearby text in the body
    body = table.get('table_body', '')
    if body:
        soup = BeautifulSoup(body, 'html.parser')
        text = soup.get_text(separator=' ', strip=True)[:300]
        
        # Look for "Table X.Y" in the body text
        match = re.search(r'Table\s+([\d\.]+[a-z]?)', text, re.IGNORECASE)
        if match:
            table_ref = f"Table {match.group(1)}"
            # Look up in content captions
            for cap_key, cap_val in content_captions.items():
                if table_ref.lower() in cap_key.lower():
                    return f"{cap_key}: {cap_val}"
    
    # Try sequential matching by index - risky but sometimes works
    # Count how many tables with captions we've seen before this one
    
    return '[No caption]'


def has_coefficient_pattern(html: str) -> bool:
    """Check if table body has REGRESSION coefficient patterns.
    
    Key distinguisher from descriptive stats:
    - Regression: 0.287*** with significance stars
    - Descriptive: 0.576 (mean) and (0.494) (SD) - NO STARS
    
    Only asterisks reliably distinguish regression from descriptive!
    """
    if not html:
        return False
    
    # RELIABLE: Coefficient with significance stars (*, **, ***)
    # Matches: 0.15*, -0.23**, 0.287***, 0.05 *
    if re.search(r'-?\d+\.\d+\s*\*{1,3}(?!\*)', html):
        return True
    
    # UNRELIABLE (commented out) - also matches descriptive SD!
    # if re.search(r'\(\d+\.\d+\)', html):  # (0.05) could be SE or SD
    #     return True
    
    return False


def classify_caption(caption: str, html: str = '') -> str:
    """Classify table based on caption and content."""
    caption_lower = caption.lower()
    has_caption = caption and caption != '[No caption]'
    has_coeffs = has_coefficient_pattern(html)
    
    # Results keywords (multilingual)
    results_keywords = [
        'impact', 'effect', 'treatment effect', 'regression', 'coefficient', 
        'estimate', 'itt', 'ate', 'did', 'difference-in-diff',
        'impacto', 'efecto', 'coeficiente', 'efeito',
    ]
    
    # Descriptive keywords
    descriptive_keywords = [
        'balance', 'baseline characteristic', 'summary statistic', 
        'sample size', 'number of', 'attrition', 'compliance',
        'variable definition', 'descriptive'
    ]
    
    # Classification logic
    if has_caption:
        if any(kw in caption_lower for kw in results_keywords):
            return 'RESULTS_BY_CAPTION'
        if any(kw in caption_lower for kw in descriptive_keywords):
            return 'DESCRIPTIVE_BY_CAPTION'
        # Has caption but unclear keywords
        if has_coeffs:
            return 'RESULTS_BY_COEFFICIENTS'
        return 'UNKNOWN_WITH_CAPTION'
    else:
        # No caption
        if has_coeffs:
            return 'RESULTS_BY_COEFFICIENTS'
        return 'UNKNOWN_NO_CAPTION'


def main():
    print("=" * 100)
    print("IMPROVED TABLE INVENTORY - Extracting captions from content field")
    print("=" * 100)
    
    json_files = list_all_jsons()
    print(f"Found {len(json_files)} JSON files")
    
    all_tables = []
    total_captions_from_field = 0
    total_captions_from_content = 0
    total_no_caption = 0
    
    for i, key in enumerate(json_files):
        study_id = extract_study_id(key)
        print(f"\r[{i+1}/{len(json_files)}] {study_id[:50]}...", end='', flush=True)
        
        try:
            doc = load_json(key)
            tables = doc.get('tables', [])
            content = doc.get('content', '')
            
            # Extract captions from content
            content_captions = extract_captions_from_content(content)
            
            for j, table in enumerate(tables):
                # Get caption from table_caption field first
                caption_list = table.get('table_caption', [])
                caption_from_field = ' '.join(caption_list).strip() if caption_list else ''
                
                html_body = table.get('table_body', '')
                
                # Determine final caption
                if caption_from_field and len(caption_from_field) > 10:
                    final_caption = caption_from_field
                    caption_source = 'table_caption_field'
                    total_captions_from_field += 1
                else:
                    # Try to find from content
                    final_caption = match_table_to_caption(j, tables, content_captions)
                    if final_caption != '[No caption]':
                        caption_source = 'content_field'
                        total_captions_from_content += 1
                    else:
                        caption_source = 'none'
                        total_no_caption += 1
                
                all_tables.append({
                    'study_id': study_id,
                    'table_index': j,
                    'table_id': f"Table{j+1}",
                    'caption': final_caption[:250],
                    'caption_source': caption_source,
                    'likely_type': classify_caption(final_caption, html_body),
                    'has_coefficients': has_coefficient_pattern(html_body),
                    'page_idx': table.get('page_idx', -1),
                })
                
        except Exception as e:
            print(f"\nError processing {study_id}: {e}")
    
    print(f"\n\nTotal tables: {len(all_tables)}")
    print(f"  - Captions from table_caption field: {total_captions_from_field}")
    print(f"  - Captions from content field: {total_captions_from_content}")
    print(f"  - No caption found: {total_no_caption}")
    
    # Create DataFrame
    df = pd.DataFrame(all_tables)
    
    # Save
    output_path = Path('extraction_pipeline/outputs/all_tables_inventory_v2.csv')
    df.to_csv(output_path, index=False)
    print(f"\nSaved to: {output_path}")
    
    # Summary
    print("\n" + "=" * 100)
    print("CLASSIFICATION SUMMARY")
    print("=" * 100)
    print(df['likely_type'].value_counts())
    print()
    print(f"Tables with coefficient patterns: {df['has_coefficients'].sum()}")
    
    # Show improvement
    print("\n" + "=" * 100)
    print("CAPTION COVERAGE IMPROVEMENT")
    print("=" * 100)
    old_no_caption = df[df['caption'] == '[No caption]']
    print(f"Tables still without caption: {len(old_no_caption)} ({len(old_no_caption)/len(df)*100:.1f}%)")


if __name__ == '__main__':
    main()
