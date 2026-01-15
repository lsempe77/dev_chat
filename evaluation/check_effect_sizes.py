#!/usr/bin/env python3
"""Check actual effect size and sample size extraction quality."""

import json

with open('evaluation/outcome_extraction_results.json') as f:
    data = json.load(f)

# Analyze effect sizes and sample sizes
total_outcomes = 0
has_effect_size = 0
has_se = 0
has_n_treatment = 0
has_n_control = 0

effect_sizes_found = []

for r in data['results']:
    ext = r.get('extracted', {})
    outcomes = ext.get('outcomes', [])
    
    for o in outcomes:
        total_outcomes += 1
        if o.get('effect_size_d') is not None:
            has_effect_size += 1
            effect_sizes_found.append(o.get('effect_size_d'))
        if o.get('standard_error') is not None:
            has_se += 1
        if o.get('n_treatment') is not None:
            has_n_treatment += 1
        if o.get('n_control') is not None:
            has_n_control += 1

print('='*60)
print('EFFECT SIZE & SAMPLE SIZE EXTRACTION QUALITY')
print('='*60)
print(f'Total extracted outcomes: {total_outcomes}')
print()
print(f'Has effect_size_d:  {has_effect_size}/{total_outcomes} ({has_effect_size/total_outcomes*100:.1f}%)')
print(f'Has standard_error: {has_se}/{total_outcomes} ({has_se/total_outcomes*100:.1f}%)')
print(f'Has n_treatment:    {has_n_treatment}/{total_outcomes} ({has_n_treatment/total_outcomes*100:.1f}%)')
print(f'Has n_control:      {has_n_control}/{total_outcomes} ({has_n_control/total_outcomes*100:.1f}%)')

# Show some examples
print()
print('='*60)
print('SAMPLE EXTRACTED OUTCOMES')
print('='*60)
for r in data['results'][:5]:
    ext = r.get('extracted', {})
    outcomes = ext.get('outcomes', [])
    if outcomes:
        o = outcomes[0]
        print(f"{r['study_id']}: {o.get('category')} - {o.get('outcome_name')}")
        print(f"  d={o.get('effect_size_d')}, SE={o.get('standard_error')}")
        print(f"  n_t={o.get('n_treatment')}, n_c={o.get('n_control')}")
        print(f"  evidence: {o.get('evidence_quote', 'N/A')[:80]}...")
        print()

# Compare to ground truth
print('='*60)
print('GROUND TRUTH COMPARISON')
print('='*60)

gt_total = 0
gt_has_effect = 0
gt_has_se = 0
gt_has_n = 0

for r in data['results']:
    gt = r.get('ground_truth', {})
    outcomes = gt.get('outcomes', [])
    
    for o in outcomes:
        gt_total += 1
        d = o.get('effect_size_d')
        if d is not None and str(d) != 'nan':
            gt_has_effect += 1
        se = o.get('se')
        if se is not None and str(se) != 'nan':
            gt_has_se += 1
        n_t = o.get('n_treatment')
        if n_t is not None and str(n_t) != 'nan':
            gt_has_n += 1

print(f'Ground Truth outcomes: {gt_total}')
print(f'GT has effect_size_d: {gt_has_effect}/{gt_total} ({gt_has_effect/gt_total*100:.1f}%)')
print(f'GT has SE:            {gt_has_se}/{gt_total} ({gt_has_se/gt_total*100:.1f}%)')
print(f'GT has n_treatment:   {gt_has_n}/{gt_total} ({gt_has_n/gt_total*100:.1f}%)')

print()
print('='*60)
print('VERDICT')
print('='*60)
print(f'Effect size extraction rate: {has_effect_size/total_outcomes*100:.1f}% (extracted) vs {gt_has_effect/gt_total*100:.1f}% (GT available)')
print(f'Sample size extraction rate: {has_n_treatment/total_outcomes*100:.1f}% (extracted) vs {gt_has_n/gt_total*100:.1f}% (GT available)')
