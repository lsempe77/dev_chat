#!/usr/bin/env python3
"""Check if extracted effect sizes match ground truth."""

import json
import math

with open('evaluation/outcome_extraction_results.json') as f:
    data = json.load(f)

print('='*70)
print('EFFECT SIZE ACCURACY CHECK')
print('='*70)

# For each study, compare extracted vs GT effect sizes
comparisons = []
large_errors = []

for r in data['results']:
    study_id = r['study_id']
    gt = r.get('ground_truth', {})
    ext = r.get('extracted', {})
    
    gt_outcomes = gt.get('outcomes', [])
    ext_outcomes = ext.get('outcomes', [])
    
    # Build GT lookup by category + rough name match
    gt_by_cat = {}
    for o in gt_outcomes:
        cat = o.get('category')
        d = o.get('effect_size_d')
        if cat and d is not None and str(d) != 'nan':
            if cat not in gt_by_cat:
                gt_by_cat[cat] = []
            gt_by_cat[cat].append(d)
    
    # Check extracted values
    for o in ext_outcomes:
        cat = o.get('category')
        ext_d = o.get('effect_size_d')
        
        if ext_d is not None and cat in gt_by_cat:
            gt_values = gt_by_cat[cat]
            # Find closest GT value
            min_diff = min(abs(ext_d - g) for g in gt_values)
            comparisons.append({
                'study': study_id,
                'category': cat,
                'extracted': ext_d,
                'closest_gt': min(gt_values, key=lambda g: abs(ext_d - g)),
                'error': min_diff
            })
            
            if min_diff > 0.5:  # Large error
                large_errors.append(comparisons[-1])

print(f'Comparisons made: {len(comparisons)}')
print()

if comparisons:
    errors = [c['error'] for c in comparisons]
    print(f'Mean absolute error: {sum(errors)/len(errors):.3f}')
    print(f'Median error: {sorted(errors)[len(errors)//2]:.3f}')
    print(f'Max error: {max(errors):.3f}')
    print(f'Errors < 0.1: {sum(1 for e in errors if e < 0.1)} ({sum(1 for e in errors if e < 0.1)/len(errors)*100:.1f}%)')
    print(f'Errors < 0.5: {sum(1 for e in errors if e < 0.5)} ({sum(1 for e in errors if e < 0.5)/len(errors)*100:.1f}%)')

print()
print('='*70)
print('EXAMPLES OF EXTRACTED VALUES')
print('='*70)

# Show some comparisons
for c in comparisons[:10]:
    match = "✓" if c['error'] < 0.1 else "✗"
    print(f"{match} {c['study']} {c['category']}: extracted={c['extracted']:.3f}, GT closest={c['closest_gt']:.3f}, error={c['error']:.3f}")

print()
print('='*70)
print('LARGE ERRORS (>0.5)')
print('='*70)
for c in large_errors[:10]:
    print(f"  {c['study']} {c['category']}: ext={c['extracted']:.3f}, GT={c['closest_gt']:.3f}")

# Check what format the LLM is extracting
print()
print('='*70)
print('EFFECT SIZE FORMAT ISSUE')
print('='*70)

# Are they extracting percentages instead of Cohen's d?
print('Sample extracted values vs GT:')
for c in comparisons[:15]:
    ratio = c['extracted'] / c['closest_gt'] if c['closest_gt'] != 0 else None
    if ratio:
        print(f"  ext={c['extracted']:.3f}, GT={c['closest_gt']:.3f}, ratio={ratio:.2f}")
