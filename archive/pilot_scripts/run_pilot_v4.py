"""Run pilot V4 with all orientation fixes."""
import os
import sys

# Fix Windows encoding for Unicode characters
sys.stdout.reconfigure(encoding='utf-8')

os.environ['AWS_ACCESS_KEY_ID'] = os.environ.get('R2_ACCESS_KEY_ID', '')
os.environ['AWS_SECRET_ACCESS_KEY'] = os.environ.get('R2_SECRET_ACCESS_KEY', '')

import pandas as pd
from extraction_pipeline.pipeline import extract_all_tables, load_mineru_json

# Get all study IDs from outputs
all_ids = sorted([d for d in os.listdir('extraction_pipeline/outputs') if d.isdigit()])
print(f'Testing {len(all_ids)} studies with V4 fixes (SE-split, European format, treatments-in-cols)...')
print()

results = []
all_rows = []

for i, sid in enumerate(all_ids):
    try:
        doc = load_mineru_json(sid)
        if doc is None:
            results.append({'study_id': sid, 'rows': 0, 'status': 'no_json'})
            continue
        
        df = extract_all_tables(doc, sid, use_llm=False)
        n = len(df)
        
        if n > 0:
            all_rows.append(df)
        results.append({'study_id': sid, 'rows': n, 'status': 'ok' if n > 0 else 'zero'})
        
        if (i+1) % 10 == 0:
            print(f'  Processed {i+1}/{len(all_ids)}...')
    except Exception as e:
        results.append({'study_id': sid, 'rows': 0, 'status': 'error'})
        print(f'  Error on {sid}: {str(e)[:50]}')

# Summary
stats = pd.DataFrame(results)
with_data = len(stats[stats['rows'] > 0])
total_rows = stats['rows'].sum()
zero_rows = len(stats[stats['status'] == 'zero'])
no_json = len(stats[stats['status'] == 'no_json'])

print()
print('=' * 60)
print('PILOT V4 SUMMARY (SE-split + European format + treatments-in-cols)')
print('=' * 60)
print(f'Studies with data: {with_data}/{len(all_ids)} ({100*with_data/len(all_ids):.0f}%)')
print(f'Total rows: {total_rows}')
print(f'Zero-extraction: {zero_rows}')
print(f'No JSON: {no_json}')
print()

# Compare to V3
print('V3 → V4 Comparison:')
print(f'  V3: 48/54 (89%), 3351 rows')
print(f'  V4: {with_data}/{len(all_ids)} ({100*with_data/len(all_ids):.0f}%), {total_rows} rows')
print(f'  Improvement: +{with_data - 48} studies, +{total_rows - 3351} rows')

# Save results
if all_rows:
    combined = pd.concat(all_rows, ignore_index=True)
    combined.to_csv('extraction_pipeline/outputs/pilot_v4_dataset.csv', index=False)
    print(f'\nSaved combined dataset: {len(combined)} rows')

stats.to_csv('extraction_pipeline/outputs/pilot_v4_stats.csv', index=False)

# Show zero-extraction studies
zero_studies = stats[stats['status'] == 'zero']['study_id'].tolist()
print(f'\nZero-extraction studies ({len(zero_studies)}):')
for sid in zero_studies:
    print(f'  {sid}')
