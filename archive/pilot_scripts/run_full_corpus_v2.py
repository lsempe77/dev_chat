"""
Run extraction on ALL R2 studies (numeric IDs + named studies).

This handles the full corpus of ~93 studies:
- 56 numeric study IDs
- 36 BRAC/named studies
"""
import os
import sys
sys.stdout.reconfigure(encoding='utf-8')

from dotenv import load_dotenv
load_dotenv()

os.environ['AWS_ACCESS_KEY_ID'] = os.environ.get('R2_ACCESS_KEY_ID', '')
os.environ['AWS_SECRET_ACCESS_KEY'] = os.environ.get('R2_SECRET_ACCESS_KEY', '')

import pandas as pd
from extraction_pipeline.r2_utils import list_all_json_files, load_json_by_key
from extraction_pipeline.pipeline import (
    extract_all_tables,
    extract_effects_from_prose,
    extract_effects_from_figures
)

# Get all JSON files from R2
print("Fetching ALL study files from R2...")
all_files = list_all_json_files()
print(f"Found {len(all_files)} JSON files in R2")
print("=" * 70)

# Process all files
results = []
all_rows = []
errors = []

for i, file_info in enumerate(all_files):
    identifier = file_info['identifier']
    key = file_info['key']
    
    try:
        # Load the JSON directly by key
        doc = load_json_by_key(key)
        if doc is None:
            results.append({
                'identifier': identifier,
                'filename': file_info['filename'],
                'rows': 0, 
                'source': 'load_error', 
                'tables': 0
            })
            errors.append({'identifier': identifier, 'error': 'Failed to load JSON'})
            continue
        
        n_tables = len(doc.get('tables', []))
        n_chars = len(doc.get('content', ''))
        
        # Stage 1: Extract from tables
        df = extract_all_tables(doc, identifier, use_llm=False)
        
        # Stage 2: If no tables, try prose extraction
        if len(df) == 0 and n_chars > 500:
            print(f"  No tables → trying prose extraction...")
            prose_rows = extract_effects_from_prose(doc, identifier)
            if prose_rows:
                df = pd.DataFrame(prose_rows)
                for col in ['study_id', 'table_title', 'treatment_name', 'outcome_name', 
                           'coefficient', 'standard_error', 'p_value', 'n_observations', 'subgroup']:
                    if col not in df.columns:
                        df[col] = None
                df['study_id'] = identifier
                df['extraction_source'] = 'prose'
        
        # Stage 3: If still nothing, try figures
        if len(df) == 0:
            print(f"  No prose → trying figure extraction...")
            figure_rows = extract_effects_from_figures(doc, identifier)
            if figure_rows:
                df = pd.DataFrame(figure_rows)
                for col in ['study_id', 'table_title', 'treatment_name', 'outcome_name', 
                           'coefficient', 'standard_error', 'p_value', 'n_observations', 'subgroup']:
                    if col not in df.columns:
                        df[col] = None
                df['study_id'] = identifier
                df['extraction_source'] = 'figures'
        
        # Record results
        source = 'tables'
        if len(df) > 0 and 'extraction_source' in df.columns:
            source = df['extraction_source'].iloc[0]
        elif len(df) == 0:
            source = 'none'
            
        results.append({
            'identifier': identifier,
            'filename': file_info['filename'],
            'study_id': file_info.get('study_id'),
            'study_name': file_info.get('study_name'),
            'rows': len(df),
            'source': source,
            'tables': n_tables,
            'chars': n_chars
        })
        
        if len(df) > 0:
            df['identifier'] = identifier
            df['filename'] = file_info['filename']
            all_rows.append(df)
        
        if (i + 1) % 10 == 0:
            print(f"  Processed {i + 1}/{len(all_files)}...")
            
    except Exception as e:
        print(f"  [ERROR] {identifier}: {e}")
        errors.append({'identifier': identifier, 'error': str(e)})
        results.append({
            'identifier': identifier,
            'filename': file_info['filename'],
            'rows': 0, 
            'source': 'error', 
            'tables': 0
        })

print("\n" + "=" * 70)
print("FULL CORPUS EXTRACTION SUMMARY")
print("=" * 70)

studies_with_data = sum(1 for r in results if r['rows'] > 0)
total_rows = sum(r['rows'] for r in results)
print(f"Studies with data: {studies_with_data}/{len(all_files)} ({100*studies_with_data/len(all_files):.0f}%)")
print(f"Total rows extracted: {total_rows}")

# Source breakdown
from collections import Counter
source_counts = Counter(r['source'] for r in results)
print("\nExtraction source breakdown:")
for source, count in source_counts.most_common():
    print(f"  {source}: {count} studies")

# Save combined results
if all_rows:
    combined = pd.concat(all_rows, ignore_index=True)
    output_path = 'extraction_pipeline/outputs/full_corpus_all_studies.csv'
    combined.to_csv(output_path, index=False)
    print(f"\nSaved: {output_path} ({len(combined)} rows)")

# Save stats
stats_df = pd.DataFrame(results)
stats_path = 'extraction_pipeline/outputs/full_corpus_all_stats.csv'
stats_df.to_csv(stats_path, index=False)
print(f"Saved: {stats_path}")

# Print errors
if errors:
    print("\n" + "=" * 70)
    print(f"ERRORS ({len(errors)} studies)")
    print("=" * 70)
    for err in errors:
        print(f"  {err['identifier']}: {err['error']}")

# Print distribution
print("\n" + "=" * 70)
print("ROWS PER STUDY DISTRIBUTION (Top 20)")
print("=" * 70)
stats_sorted = sorted(results, key=lambda x: x['rows'], reverse=True)
print(f"{'identifier':<50} {'rows':>6} {'source':<10} {'tables':>6}")
for r in stats_sorted[:20]:
    print(f"{r['identifier'][:50]:<50} {r['rows']:>6} {r['source']:<10} {r['tables']:>6}")

# Identify potential issues
print("\n" + "=" * 70)
print("POTENTIAL ISSUES TO REVIEW")
print("=" * 70)

low_rows = [r for r in results if 0 < r['rows'] < 10]
if low_rows:
    print(f"\nStudies with <10 rows ({len(low_rows)}):")
    for r in sorted(low_rows, key=lambda x: x['rows']):
        print(f"  {r['identifier'][:45]}: {r['rows']} rows ({r['source']})")

zero_rows = [r for r in results if r['rows'] == 0]
if zero_rows:
    print(f"\nStudies with 0 rows ({len(zero_rows)}):")
    for r in zero_rows[:20]:
        print(f"  {r['identifier'][:50]}: tables={r['tables']}, chars={r.get('chars', 0)}")
    if len(zero_rows) > 20:
        print(f"  ... and {len(zero_rows) - 20} more")

high_rows = [r for r in results if r['rows'] > 500]
if high_rows:
    print(f"\nStudies with >500 rows ({len(high_rows)}) - check for over-extraction:")
    for r in sorted(high_rows, key=lambda x: x['rows'], reverse=True):
        print(f"  {r['identifier'][:45]}: {r['rows']} rows")
