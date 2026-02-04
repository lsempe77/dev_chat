"""Run extraction on full R2 corpus and identify errors."""
import os
import sys
sys.stdout.reconfigure(encoding='utf-8')

os.environ['AWS_ACCESS_KEY_ID'] = os.environ.get('R2_ACCESS_KEY_ID', '')
os.environ['AWS_SECRET_ACCESS_KEY'] = os.environ.get('R2_SECRET_ACCESS_KEY', '')

import pandas as pd
import re
from extraction_pipeline.pipeline import (
    get_r2_client,
    load_mineru_json,
    extract_all_tables,
    extract_effects_from_prose,
    extract_effects_from_figures
)

# Get all study IDs from R2
print("Fetching study list from R2...")
client = get_r2_client()
prefix = 'rags/0816e8d3-ab23-417c-bf3f-e45531411c73/outputs/json/'
paginator = client.get_paginator('list_objects_v2')

all_study_ids = set()
for page in paginator.paginate(Bucket='devchat-pdfs', Prefix=prefix):
    for obj in page.get('Contents', []):
        match = re.search(r'(\d{9})', obj['Key'])
        if match:
            all_study_ids.add(match.group(1))

all_study_ids = sorted(all_study_ids)
print(f"Found {len(all_study_ids)} studies in R2")
print("=" * 70)

# Process all studies
results = []
all_rows = []
errors = []

for i, sid in enumerate(all_study_ids):
    try:
        doc = load_mineru_json(sid)
        if doc is None:
            results.append({'study_id': sid, 'rows': 0, 'source': 'no_json', 'tables': 0, 'chars': 0})
            errors.append({'study_id': sid, 'error': 'Could not load JSON from R2'})
            continue
        
        n_tables = len(doc.get('tables', []))
        n_chars = len(doc.get('content', ''))
        
        # Try table extraction
        df = extract_all_tables(doc, sid, use_llm=False)
        source = 'tables' if len(df) > 0 else 'none'
        
        # Fallback: prose extraction
        if df.empty:
            prose_effects = extract_effects_from_prose(doc, sid)
            if prose_effects:
                df = pd.DataFrame(prose_effects)
                source = 'prose'
        
        # Fallback: figure extraction
        if df.empty:
            figure_effects = extract_effects_from_figures(doc, sid)
            if figure_effects:
                df = pd.DataFrame(figure_effects)
                source = 'figures'
        
        n_rows = len(df)
        results.append({
            'study_id': sid, 
            'rows': n_rows, 
            'source': source,
            'tables': n_tables,
            'chars': n_chars
        })
        
        if n_rows > 0:
            df['study_id'] = sid
            all_rows.append(df)
        else:
            errors.append({
                'study_id': sid, 
                'error': f'Zero extraction (tables={n_tables}, chars={n_chars})'
            })
        
        # Progress
        if (i + 1) % 10 == 0:
            print(f"  Processed {i+1}/{len(all_study_ids)}...")
            
    except Exception as e:
        results.append({'study_id': sid, 'rows': 0, 'source': 'error', 'tables': 0, 'chars': 0})
        errors.append({'study_id': sid, 'error': str(e)[:100]})
        print(f"  ERROR on {sid}: {str(e)[:50]}")

# Summary
print()
print("=" * 70)
print("FULL CORPUS EXTRACTION SUMMARY")
print("=" * 70)

stats = pd.DataFrame(results)
with_data = len(stats[stats['rows'] > 0])
total_rows = stats['rows'].sum()

print(f"Studies with data: {with_data}/{len(all_study_ids)} ({100*with_data/len(all_study_ids):.0f}%)")
print(f"Total rows extracted: {total_rows}")
print()

# Breakdown by source
print("Extraction source breakdown:")
for source in ['tables', 'prose', 'figures', 'none', 'error', 'no_json']:
    count = len(stats[stats['source'] == source])
    if count > 0:
        print(f"  {source}: {count} studies")

# Save combined dataset
if all_rows:
    combined = pd.concat(all_rows, ignore_index=True)
    combined.to_csv('extraction_pipeline/outputs/full_corpus_v6.csv', index=False)
    print(f"\nSaved: extraction_pipeline/outputs/full_corpus_v6.csv ({len(combined)} rows)")

# Save stats
stats.to_csv('extraction_pipeline/outputs/full_corpus_stats.csv', index=False)
print(f"Saved: extraction_pipeline/outputs/full_corpus_stats.csv")

# Show errors
if errors:
    print()
    print("=" * 70)
    print(f"ERRORS ({len(errors)} studies)")
    print("=" * 70)
    for e in errors:
        print(f"  {e['study_id']}: {e['error']}")

# Show distribution of rows per study
print()
print("=" * 70)
print("ROWS PER STUDY DISTRIBUTION")
print("=" * 70)
print(stats[['study_id', 'rows', 'source', 'tables']].sort_values('rows', ascending=False).head(20).to_string(index=False))

# Check for potential issues
print()
print("=" * 70)
print("POTENTIAL ISSUES TO REVIEW")
print("=" * 70)

# Studies with very few rows
low_rows = stats[(stats['rows'] > 0) & (stats['rows'] < 10)]
if len(low_rows) > 0:
    print(f"\nStudies with <10 rows ({len(low_rows)}):")
    for _, row in low_rows.iterrows():
        print(f"  {row['study_id']}: {row['rows']} rows ({row['source']})")

# Studies with very high rows (potential over-extraction)
high_rows = stats[stats['rows'] > 500]
if len(high_rows) > 0:
    print(f"\nStudies with >500 rows ({len(high_rows)}) - check for over-extraction:")
    for _, row in high_rows.iterrows():
        print(f"  {row['study_id']}: {row['rows']} rows")

# Studies with many tables but few rows
many_tables_few_rows = stats[(stats['tables'] > 20) & (stats['rows'] < 50)]
if len(many_tables_few_rows) > 0:
    print(f"\nStudies with many tables but few rows ({len(many_tables_few_rows)}):")
    for _, row in many_tables_few_rows.iterrows():
        print(f"  {row['study_id']}: {row['tables']} tables → {row['rows']} rows")
