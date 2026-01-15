#!/usr/bin/env python3
"""Check improved extraction results."""

import json

with open('evaluation/improved_extraction_results.json') as f:
    data = json.load(f)

print("EXTRACTED OUTCOMES WITH EFFECT SIZES:")
print("="*60)

for r in data['results']:
    if 'extracted' not in r:
        continue
    
    study_id = r['study_id']
    outcomes = r['extracted'].get('outcomes', [])
    
    print(f"\n{study_id}:")
    for o in outcomes:
        d = o.get('effect_size_d')
        status = o.get('verification_status', 'unknown')
        conf = o.get('confidence', 0)
        cat = o.get('category', 'Unknown')
        name = o.get('outcome_name', '')[:40]
        
        d_str = f"{d:.3f}" if d is not None else "null"
        print(f"  {cat}: {name}")
        print(f"    d={d_str}, status={status}, conf={conf}")

# Compare to baseline
print("\n" + "="*60)
print("COMPARISON TO BASELINE")
print("="*60)

with open('evaluation/outcome_extraction_results.json') as f:
    baseline = json.load(f)

# Find same studies
for r in data['results']:
    if 'extracted' not in r:
        continue
    
    study_id = r['study_id']
    
    # Find baseline for same study
    baseline_r = next((b for b in baseline['results'] if b['study_id'] == study_id), None)
    if not baseline_r:
        continue
    
    v2_outcomes = r['extracted'].get('outcomes', [])
    v1_outcomes = baseline_r.get('extracted', {}).get('outcomes', [])
    
    v2_d_values = [o.get('effect_size_d') for o in v2_outcomes if o.get('effect_size_d')]
    v1_d_values = [o.get('effect_size_d') for o in v1_outcomes if o.get('effect_size_d')]
    
    print(f"\n{study_id}:")
    print(f"  V1 effect sizes: {v1_d_values}")
    print(f"  V2 effect sizes: {v2_d_values}")
    
    # Compare to GT
    gt_outcomes = r.get('ground_truth', {}).get('outcomes', [])
    gt_d_values = [o.get('effect_size_d') for o in gt_outcomes[:5] if o.get('effect_size_d')]
    print(f"  GT effect sizes (first 5): {[round(d, 3) for d in gt_d_values]}")
