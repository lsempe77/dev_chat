#!/usr/bin/env python3
"""Compare V1 vs V2 effect size accuracy."""

import json
import math

def load_results(path):
    with open(path) as f:
        return json.load(f)

def analyze_accuracy(results, version_name):
    """Analyze effect size accuracy for a set of results."""
    comparisons = []
    
    for r in results['results']:
        if 'error' in r or 'extracted' not in r:
            continue
        
        study_id = r['study_id']
        gt = r.get('ground_truth', {})
        ext = r.get('extracted', {})
        
        gt_outcomes = gt.get('outcomes', [])
        ext_outcomes = ext.get('outcomes', [])
        
        # Build GT lookup by category
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
                min_diff = min(abs(ext_d - g) for g in gt_values)
                comparisons.append({
                    'study': study_id,
                    'category': cat,
                    'extracted': ext_d,
                    'closest_gt': min(gt_values, key=lambda g: abs(ext_d - g)),
                    'error': min_diff
                })
    
    return comparisons

def print_analysis(comparisons, version_name):
    print(f"\n{'='*60}")
    print(f"{version_name} EFFECT SIZE ACCURACY")
    print(f"{'='*60}")
    
    if not comparisons:
        print("No comparisons available")
        return
    
    errors = [c['error'] for c in comparisons]
    
    print(f"Comparisons made: {len(comparisons)}")
    print(f"Mean absolute error: {sum(errors)/len(errors):.4f}")
    print(f"Median error: {sorted(errors)[len(errors)//2]:.4f}")
    print(f"Max error: {max(errors):.4f}")
    print()
    print(f"Errors < 0.1 (accurate): {sum(1 for e in errors if e < 0.1)} ({sum(1 for e in errors if e < 0.1)/len(errors)*100:.1f}%)")
    print(f"Errors < 0.2: {sum(1 for e in errors if e < 0.2)} ({sum(1 for e in errors if e < 0.2)/len(errors)*100:.1f}%)")
    print(f"Errors < 0.5: {sum(1 for e in errors if e < 0.5)} ({sum(1 for e in errors if e < 0.5)/len(errors)*100:.1f}%)")
    print(f"Errors >= 1.0 (very wrong): {sum(1 for e in errors if e >= 1.0)} ({sum(1 for e in errors if e >= 1.0)/len(errors)*100:.1f}%)")
    
    # Show examples
    print(f"\nSample comparisons:")
    for c in sorted(comparisons, key=lambda x: x['error'])[:5]:
        match = "✓" if c['error'] < 0.1 else "~"
        print(f"  {match} {c['study']} {c['category']}: ext={c['extracted']:.3f}, GT={c['closest_gt']:.3f}, err={c['error']:.3f}")
    
    print(f"\nWorst errors:")
    for c in sorted(comparisons, key=lambda x: -x['error'])[:5]:
        print(f"  ✗ {c['study']} {c['category']}: ext={c['extracted']:.3f}, GT={c['closest_gt']:.3f}, err={c['error']:.3f}")


# Load both result sets
v1 = load_results('evaluation/outcome_extraction_results.json')
v2 = load_results('evaluation/improved_extraction_results.json')

# Filter V1 to same studies as V2
v2_study_ids = {r['study_id'] for r in v2['results']}
v1_filtered = {
    'results': [r for r in v1['results'] if r['study_id'] in v2_study_ids]
}

print("COMPARISON: V1 BASELINE vs V2 IMPROVED (same 10 studies)")
print("="*60)

v1_comps = analyze_accuracy(v1_filtered, "V1 Baseline")
v2_comps = analyze_accuracy(v2, "V2 Improved")

print_analysis(v1_comps, "V1 BASELINE")
print_analysis(v2_comps, "V2 IMPROVED")

# Summary comparison
print("\n" + "="*60)
print("SUMMARY COMPARISON")
print("="*60)

if v1_comps and v2_comps:
    v1_errors = [c['error'] for c in v1_comps]
    v2_errors = [c['error'] for c in v2_comps]
    
    v1_accurate = sum(1 for e in v1_errors if e < 0.1) / len(v1_errors) * 100
    v2_accurate = sum(1 for e in v2_errors if e < 0.1) / len(v2_errors) * 100
    
    v1_wrong = sum(1 for e in v1_errors if e >= 1.0) / len(v1_errors) * 100
    v2_wrong = sum(1 for e in v2_errors if e >= 1.0) / len(v2_errors) * 100
    
    print(f"                    V1 Baseline    V2 Improved    Change")
    print(f"Comparisons:        {len(v1_comps):>10}    {len(v2_comps):>10}")
    print(f"Mean error:         {sum(v1_errors)/len(v1_errors):>10.3f}    {sum(v2_errors)/len(v2_errors):>10.3f}    {'↓ BETTER' if sum(v2_errors)/len(v2_errors) < sum(v1_errors)/len(v1_errors) else '↑ WORSE'}")
    print(f"Accurate (<0.1):    {v1_accurate:>9.1f}%    {v2_accurate:>9.1f}%    {'+' if v2_accurate > v1_accurate else ''}{v2_accurate - v1_accurate:.1f}%")
    print(f"Very wrong (>=1.0): {v1_wrong:>9.1f}%    {v2_wrong:>9.1f}%    {'+' if v2_wrong < v1_wrong else '-'}{abs(v2_wrong - v1_wrong):.1f}%")
