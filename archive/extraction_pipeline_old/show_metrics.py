"""Show metrics from all version results."""

import json
from pathlib import Path

files = ['v10_results.json', 'v11_results.json', 'v12_results.json', 'v13_results.json', 'v16_results.json']

print("="*70)
print("VERSION METRICS SUMMARY")
print("="*70)

for f in files:
    try:
        with open(f) as file:
            data = json.load(file)
            
            if 'metrics' in data:
                m = data['metrics']
                recall = m.get('recall', '?')
                precision = m.get('precision', '?')
                matched = m.get('matched', m.get('n_matched', '?'))
                total_gt = m.get('total_gt', m.get('n_gt', '?'))
                extracted = m.get('extracted', m.get('n_extracted', '?'))
                print(f"{f}:")
                print(f"  Recall: {recall}")
                print(f"  Precision: {precision}")
                print(f"  Matched: {matched}/{total_gt} | Extracted: {extracted}")
                print()
            elif 'summary' in data:
                s = data['summary']
                print(f"{f}: {s}")
                print()
            else:
                # Check for per-study results
                keys = list(data.keys())[:10]
                print(f"{f}: keys = {keys}")
                
                # Try to aggregate
                if isinstance(data, dict):
                    total_matched = 0
                    total_gt = 0
                    total_extracted = 0
                    for study_id, study_data in data.items():
                        if isinstance(study_data, dict):
                            if 'matched' in study_data:
                                total_matched += len(study_data.get('matched', []))
                            if 'gt_outcomes' in study_data:
                                total_gt += len(study_data.get('gt_outcomes', []))
                            if 'extracted' in study_data:
                                total_extracted += len(study_data.get('extracted', []))
                    if total_gt > 0:
                        print(f"  Aggregated: {total_matched}/{total_gt} matched, {total_extracted} extracted")
                print()
    except Exception as e:
        print(f"{f}: error - {type(e).__name__}: {e}")
        print()
