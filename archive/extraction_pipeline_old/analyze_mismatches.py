"""Analyze Cohen's d mismatches to find systematic errors."""

import pandas as pd
import json
import numpy as np

# Load mapped comparison
df = pd.read_csv('cohens_d_mapped_comparison.csv')

# Rename columns for clarity
df = df.rename(columns={
    'extracted_outcome': 'extracted_name',
    'gt_outcome': 'gt_name',
    'difference': 'abs_diff'
})

# Calculate ratio (handle division by zero)
df['ratio'] = np.where(df['gt_d'] != 0, df['extracted_d'] / df['gt_d'], np.nan)

# Analyze close matches
close = df[df['abs_diff'] < 0.1]
far = df[df['abs_diff'] >= 0.1]

print("=" * 70)
print("MISMATCH ANALYSIS")
print("=" * 70)

print(f"\nCLOSE MATCHES (diff < 0.1): {len(close)}")
print(f"MISMATCHES (diff >= 0.1): {len(far)}")

# Check if mismatches have a consistent ratio pattern
print("\n" + "-" * 70)
print("MISMATCH RATIO ANALYSIS")
print("-" * 70)

# Filter for reasonable ratios
far_clean = far[(far['ratio'] > 0.01) & (far['ratio'] < 10)]
print(f"\nPositive ratios (0.01-10x): {len(far_clean)}")

if len(far_clean) > 0:
    print(f"Mean ratio: {far_clean['ratio'].mean():.2f}x")
    print(f"Median ratio: {far_clean['ratio'].median():.2f}x")
    print("\nRatio distribution:")
    print(far_clean['ratio'].describe())

# Show specific mismatches by study
print("\n" + "-" * 70)
print("MISMATCHES BY STUDY")
print("-" * 70)

for study in df['study'].unique():
    study_df = far[far['study'] == study]
    if len(study_df) > 0:
        print(f"\n{study}: {len(study_df)} mismatches")
        for _, row in study_df.head(5).iterrows():
            ratio = row['extracted_d'] / row['gt_d'] if row['gt_d'] != 0 else float('inf')
            print(f"  {row['extracted_name'][:50]}...")
            print(f"    Extracted: {row['extracted_d']:.4f}, GT: {row['gt_d']:.4f}, Ratio: {ratio:.2f}x")

# Load full results to check method used
print("\n" + "-" * 70)
print("METHOD ANALYSIS FOR MISMATCHES")
print("-" * 70)

with open('v17d_cohens_d_results.json', 'r') as f:
    results = json.load(f)

# Create lookup for method used
outcome_methods = {}
for study in results['studies']:
    study_name = study['study_name']
    for outcome in study['outcomes']:
        if outcome.get('cohens_d'):
            key = (study_name, outcome['outcome_name'])
            outcome_methods[key] = outcome.get('cohens_d_method', 'unknown')

# Check method for mismatches
t_stat_mismatches = 0
sd_mismatches = 0

for _, row in far.iterrows():
    key = (row['study'], row['extracted_name'])
    method = outcome_methods.get(key, 'unknown')
    if method == 't_stat':
        t_stat_mismatches += 1
    elif method == 'sd':
        sd_mismatches += 1

print(f"\nMismatches by method:")
print(f"  t-stat method: {t_stat_mismatches}")
print(f"  SD method: {sd_mismatches}")

# Check if ratio pattern suggests sample size issue
print("\n" + "-" * 70)
print("CHECKING FOR SAMPLE SIZE ISSUES")
print("-" * 70)

# If extracted d = 2*t/sqrt(N) and GT uses different N
# Then ratio = sqrt(N_gt) / sqrt(N_extracted)
# So ratio^2 = N_gt / N_extracted

far_positive = far[(far['ratio'] > 0.1) & (far['ratio'] < 5)]
if len(far_positive) > 0:
    print(f"\nFor {len(far_positive)} mismatches with ratio 0.1-5x:")
    ratios_squared = (far_positive['ratio'] ** 2)
    print(f"  Mean ratio²: {ratios_squared.mean():.2f} (implied N ratio)")
    print(f"  Median ratio²: {ratios_squared.median():.2f}")

# Check for outcomes where we're exactly 2x off (missing factor of 2)
close_to_2x = far[(far['ratio'] > 1.8) & (far['ratio'] < 2.2)]
close_to_half = far[(far['ratio'] > 0.45) & (far['ratio'] < 0.55)]
print(f"\nOutcomes close to 2x: {len(close_to_2x)}")
print(f"Outcomes close to 0.5x: {len(close_to_half)}")

# Show exact matches
print("\n" + "=" * 70)
print("EXACT/NEAR-EXACT MATCHES (diff < 0.01)")
print("=" * 70)

exact = df[df['abs_diff'] < 0.01]
for _, row in exact.iterrows():
    print(f"\n{row['study']}: {row['extracted_name'][:50]}")
    print(f"  Extracted: {row['extracted_d']:.4f}, GT: {row['gt_d']:.4f}")
