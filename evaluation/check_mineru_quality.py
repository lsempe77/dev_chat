#!/usr/bin/env python3
"""
Check MineRU Output Quality

Sample the actual markdown output to see if tables/data are being extracted properly.
"""

import os
import boto3
import json
import re
from dotenv import load_dotenv

load_dotenv()

CLOUDFLARE_ACCOUNT_ID = os.environ.get('CLOUDFLARE_ACCOUNT_ID')
R2_ACCESS_KEY = os.environ.get('R2_ACCESS_KEY_ID')
R2_SECRET_KEY = os.environ.get('R2_SECRET_ACCESS_KEY')

def get_s3_client():
    return boto3.client(
        's3',
        endpoint_url=f'https://{CLOUDFLARE_ACCOUNT_ID}.r2.cloudflarestorage.com',
        aws_access_key_id=R2_ACCESS_KEY,
        aws_secret_access_key=R2_SECRET_KEY
    )

def load_document(r2_key):
    """Load document from R2."""
    s3 = get_s3_client()
    response = s3.get_object(Bucket='devchat-pdfs', Key=r2_key)
    content = response['Body'].read()
    try:
        return content.decode('utf-8')
    except UnicodeDecodeError:
        return content.decode('latin-1')

def analyze_markdown(content, study_id):
    """Analyze markdown structure and quality."""
    print(f"\n{'='*80}")
    print(f"STUDY: {study_id}")
    print('='*80)
    
    # Basic stats
    print(f"\n📊 BASIC STATS:")
    print(f"  Total chars: {len(content):,}")
    print(f"  Total lines: {content.count(chr(10)):,}")
    
    # Check for tables
    table_patterns = [
        (r'\|.*\|', 'Markdown tables (|...|)'),
        (r'<table', 'HTML tables'),
        (r'Table \d+', 'Table references'),
        (r'TABLE \d+', 'TABLE references (caps)'),
    ]
    
    print(f"\n📋 TABLE DETECTION:")
    for pattern, name in table_patterns:
        matches = re.findall(pattern, content, re.IGNORECASE)
        print(f"  {name}: {len(matches)} matches")
    
    # Check for numeric data
    print(f"\n🔢 NUMERIC DATA:")
    
    # Coefficients (numbers with decimals)
    coeff_pattern = r'-?\d+\.\d{2,}'
    coefficients = re.findall(coeff_pattern, content)
    print(f"  Decimal numbers (potential coefficients): {len(coefficients)}")
    
    # Standard errors in parentheses
    se_pattern = r'\([\d.]+\)'
    se_matches = re.findall(se_pattern, content)
    print(f"  Numbers in parentheses (potential SEs): {len(se_matches)}")
    
    # Sample size patterns
    n_pattern = r'[Nn]\s*=\s*\d+'
    n_matches = re.findall(n_pattern, content)
    print(f"  N = patterns (sample sizes): {len(n_matches)}")
    
    # P-values
    p_pattern = r'p\s*[<>=]\s*[\d.]+'
    p_matches = re.findall(p_pattern, content, re.IGNORECASE)
    print(f"  P-value patterns: {len(p_matches)}")
    
    # Confidence intervals
    ci_pattern = r'\[[\d.\-,\s]+\]|\([\d.\-,\s]+\)'
    ci_matches = re.findall(ci_pattern, content)
    ci_likely = [m for m in ci_matches if ',' in m or '-' in m]
    print(f"  Bracketed ranges (potential CIs): {len(ci_likely)}")
    
    # Check for key sections
    print(f"\n📝 SECTION DETECTION:")
    sections = ['Abstract', 'Introduction', 'Method', 'Results', 'Discussion', 'Conclusion', 'Table', 'Figure']
    for section in sections:
        count = len(re.findall(rf'\b{section}\b', content, re.IGNORECASE))
        if count > 0:
            print(f"  {section}: {count} mentions")
    
    # Check for specific outcome keywords
    print(f"\n🎯 OUTCOME KEYWORDS:")
    outcome_keywords = ['income', 'assets', 'savings', 'consumption', 'expenditure', 'poverty', 'livestock', 'revenue']
    for kw in outcome_keywords:
        count = len(re.findall(rf'\b{kw}\b', content, re.IGNORECASE))
        if count > 0:
            print(f"  {kw}: {count} mentions")
    
    # Sample actual table content
    print(f"\n📖 SAMPLE TABLE CONTENT (first 3 markdown tables):")
    table_rows = [line for line in content.split('\n') if '|' in line and line.count('|') >= 3]
    for i, row in enumerate(table_rows[:15]):
        print(f"  {row[:100]}...")
    
    if not table_rows:
        print("  ⚠️ NO MARKDOWN TABLES FOUND!")
        # Show what's around "Table" mentions
        for match in re.finditer(r'Table\s+\d+', content, re.IGNORECASE):
            start = max(0, match.start() - 50)
            end = min(len(content), match.end() + 200)
            print(f"\n  Context around '{match.group()}':")
            print(f"  {content[start:end][:300]}...")
            break
    
    return {
        'chars': len(content),
        'tables': len(table_rows),
        'coefficients': len(coefficients),
        'se_patterns': len(se_matches),
        'n_patterns': len(n_matches),
        'ci_patterns': len(ci_likely)
    }

def main():
    # Load matched studies with r2 keys
    with open('evaluation/matched_studies_r2.json') as f:
        studies = json.load(f)
    
    print("="*80)
    print("MINERU OUTPUT QUALITY CHECK")
    print("="*80)
    print(f"Found {len(studies)} studies with R2 keys")
    print(f"Checking first 5 studies...")
    
    # Sample studies
    studies_to_check = studies[:5]
    
    all_stats = []
    for study in studies_to_check:
        study_id = study.get('study_id')
        r2_key = study.get('r2_key')
        
        if not r2_key:
            print(f"\n⚠️ Study {study_id}: No r2_key found")
            continue
        
        try:
            content = load_document(r2_key)
            stats = analyze_markdown(content, study_id)
            stats['study_id'] = study_id
            all_stats.append(stats)
        except Exception as e:
            print(f"\n❌ Study {study_id}: Error loading: {e}")
    
    # Summary
    print("\n" + "="*80)
    print("SUMMARY ACROSS CHECKED STUDIES")
    print("="*80)
    
    if all_stats:
        print(f"\n{'Study':<12} {'Chars':>10} {'Tables':>8} {'Coeffs':>8} {'SEs':>8} {'Ns':>6} {'CIs':>6}")
        print("-"*70)
        for s in all_stats:
            print(f"{s['study_id']:<12} {s['chars']:>10,} {s['tables']:>8} {s['coefficients']:>8} {s['se_patterns']:>8} {s['n_patterns']:>6} {s['ci_patterns']:>6}")
    
    # Check if tables exist
    avg_tables = sum(s['tables'] for s in all_stats) / len(all_stats) if all_stats else 0
    
    print(f"\n🔍 KEY FINDING:")
    if avg_tables < 5:
        print("  ⚠️ LOW TABLE COUNT - MineRU may not be extracting tables properly!")
    else:
        print(f"  ✓ Average {avg_tables:.0f} table rows per document")
    
    avg_coeffs = sum(s['coefficients'] for s in all_stats) / len(all_stats) if all_stats else 0
    if avg_coeffs < 50:
        print("  ⚠️ LOW COEFFICIENT COUNT - Numeric data may be missing!")
    else:
        print(f"  ✓ Average {avg_coeffs:.0f} potential coefficients per document")

if __name__ == '__main__':
    main()
