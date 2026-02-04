"""Run pilot V3 with P1+P2 fixes."""
import os
import pandas as pd
from extraction_pipeline.pipeline import extract_all_tables, load_mineru_json

# Get all study IDs from outputs
all_ids = sorted([d for d in os.listdir('extraction_pipeline/outputs') if d.isdigit()])
print(f'Testing {len(all_ids)} studies with P1+P2 fixes...')

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
print('PILOT V3 SUMMARY (P1+P2 fixes)')
print('=' * 60)
print(f'Studies with data: {with_data}/{len(all_ids)} ({100*with_data/len(all_ids):.0f}%)')
print(f'Total rows: {total_rows}')
print(f'Zero-extraction: {zero_rows}')
print(f'No JSON: {no_json}')

# Save results
if all_rows:
    combined = pd.concat(all_rows, ignore_index=True)
    combined.to_csv('extraction_pipeline/outputs/pilot_v3_dataset.csv', index=False)
    print(f'\nSaved combined dataset: {len(combined)} rows')

stats.to_csv('extraction_pipeline/outputs/pilot_v3_stats.csv', index=False)
