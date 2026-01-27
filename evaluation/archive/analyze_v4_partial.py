"""Analyze V4 partial results"""
import json
import pandas as pd
from fuzzy_comparison import compare_extractions_fuzzy

# Load V4 partial results
with open('evaluation/v4_extraction_results_partial.json') as f:
    v4_extractions = json.load(f)

print("="*70)
print("V4 PARTIAL RESULTS ANALYSIS (Multi-pass extraction)")
print("="*70)

# Convert to standard format
v4_data = {
    'version': 'v4_multipass',
    'n_studies': len(v4_extractions),
    'extractions': v4_extractions
}

print(f"\n✓ Loaded {len(v4_extractions)} partial extractions")

# Count outcomes
total_outcomes = sum(len(e.get('outcomes', [])) for e in v4_extractions)
print(f"✓ Total outcomes extracted: {total_outcomes}")

# Outcomes by study
print(f"\nOutcomes per study:")
for ext in v4_extractions[:10]:
    study_id = ext['study_id']
    n_outcomes = len(ext.get('outcomes', []))
    print(f"  Study {study_id}: {n_outcomes} outcomes")
if len(v4_extractions) > 10:
    print(f"  ... and {len(v4_extractions)-10} more studies")

# Outcomes by category
category_counts = {}
for ext in v4_extractions:
    for outcome in ext.get('outcomes', []):
        cat = outcome.get('outcome_category', 'Unknown')
        category_counts[cat] = category_counts.get(cat, 0) + 1

print(f"\nOutcomes by category:")
for cat in ['Income', 'Assets', 'Savings', 'Expenditure', 'Poverty']:
    count = category_counts.get(cat, 0)
    print(f"  {cat:15s}: {count:3d} outcomes")

# Sample sizes
print(f"\nSample size information:")
samples_with_n = 0
total_outcomes_checked = 0
for ext in v4_extractions:
    for outcome in ext.get('outcomes', []):
        total_outcomes_checked += 1
        if outcome.get('n_treatment') or outcome.get('n_control'):
            samples_with_n += 1

print(f"  Outcomes with sample sizes: {samples_with_n}/{total_outcomes_checked} ({100*samples_with_n/total_outcomes_checked:.1f}%)")

# Effect sizes
print(f"\nEffect size information:")
with_d = 0
with_coeff = 0
with_se = 0
for ext in v4_extractions:
    for outcome in ext.get('outcomes', []):
        if outcome.get('effect_size_d'):
            with_d += 1
        if outcome.get('coefficient'):
            with_coeff += 1
        if outcome.get('standard_error'):
            with_se += 1

print(f"  Outcomes with effect_size_d: {with_d}/{total_outcomes_checked} ({100*with_d/total_outcomes_checked:.1f}%)")
print(f"  Outcomes with coefficient: {with_coeff}/{total_outcomes_checked} ({100*with_coeff/total_outcomes_checked:.1f}%)")
print(f"  Outcomes with standard_error: {with_se}/{total_outcomes_checked} ({100*with_se/total_outcomes_checked:.1f}%)")

# Load ground truth and compare
print(f"\n{'='*70}")
print("COMPARISON TO GROUND TRUTH (20 studies only)")
print('='*70)

# Load GT
gt_df = pd.read_excel('data/metadata.csv', sheet_name='Sheet1')
gt_df.columns = ['study_id', 'outcome_category', 'outcome_name', 'effect_size_d', 
                 'coefficient', 'standard_error', 'n_treatment', 'n_control']

# Filter GT to V4's studies
study_ids = [str(e['study_id']) for e in v4_extractions]
gt_df['study_id'] = gt_df['study_id'].apply(lambda x: str(int(x)) if pd.notna(x) else "")
gt_filtered = gt_df[gt_df['study_id'].isin(study_ids)]

print(f"✓ GT filtered: {len(gt_filtered)} outcomes from {len(study_ids)} studies")

# Run fuzzy comparison
comparison = compare_extractions_fuzzy(v4_extractions, gt_filtered, threshold=70)

print(f"\n--- Outcome Extraction (Fuzzy Matching, threshold=70) ---")
print(f"\nOverall:")
print(f"  Recall:    {comparison['overall_recall']*100:.1f}%")
print(f"  Precision: {comparison['overall_precision']*100:.1f}%")
print(f"  Matched:   {comparison['total_matched']}/{comparison['total_gt_outcomes']} GT outcomes")
print(f"  Extracted: {comparison['total_extracted']} outcomes")

print(f"\nBy Category:")
for cat in ['Income', 'Assets', 'Savings', 'Expenditure', 'Poverty']:
    stats = comparison['by_category'][cat]
    print(f"  {cat:12s} R={stats['recall']*100:5.1f}% P={stats['precision']*100:5.1f}% "
          f"({stats['matched']:3d}/{stats['gt_count']:3d} matched, {stats['extracted_count']:3d} extracted)")

print(f"\n{'='*70}")
print("NOTE: V4 crashed after 20/43 studies, so these results are incomplete")
print("="*70)
