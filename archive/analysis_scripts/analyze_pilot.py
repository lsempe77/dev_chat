"""Analyze pilot results for error patterns."""
import pandas as pd

# Load data
stats = pd.read_csv('extraction_pipeline/outputs/pilot_stats.csv')
combined = pd.read_csv('extraction_pipeline/outputs/full_pilot_dataset.csv')

print('='*70)
print('FULL PILOT SUMMARY')
print('='*70)

print(f"Studies processed: {len(stats)}")
print(f"Studies with data: {len(stats[stats['rows'] > 0])}")
print(f"Studies with 0 rows: {len(stats[stats['rows'] == 0])}")
print(f"Total rows extracted: {stats['rows'].sum()}")
print(f"Total unique outcomes: {combined['outcome_name'].nunique()}")

print()
print('STUDIES WITH 0 ROWS (potential issues):')
zero_studies = stats[stats['rows'] == 0]['study_id'].tolist()
for sid in zero_studies:
    print(f"  {sid}")

print()
print('TOP 10 STUDIES BY ROWS:')
top = stats.nlargest(10, 'rows')[['study_id', 'rows', 'outcomes']]
print(top.to_string(index=False))

print()
print('='*70)
print('ERROR PATTERN ANALYSIS')
print('='*70)

# 1. Large coefficients
large_coef = combined[abs(combined['coefficient']) > 10]
print(f"\n1. ROWS WITH |coefficient| > 10: {len(large_coef)} ({len(large_coef)/len(combined)*100:.1f}%)")
print("   Sample:")
print(large_coef[['study_id', 'table_number', 'outcome_name', 'coefficient']].head(5).to_string(index=False))

# 2. Treatment arm distribution
print(f"\n2. TREATMENT ARM DISTRIBUTION (top 20):")
arm_counts = combined['treatment_arm'].value_counts().head(20)
for arm, count in arm_counts.items():
    print(f"   {arm}: {count}")

# 3. Suspicious treatment arms
print(f"\n3. SUSPICIOUS TREATMENT ARMS:")
suspicious_patterns = ['Test:', 'Mean of', '= T', 'p-value', 'p value', 'N =']
suspicious_mask = combined['treatment_arm'].str.contains('|'.join(suspicious_patterns), case=False, na=False)
suspicious = combined[suspicious_mask]
print(f"   Rows with suspicious arms: {len(suspicious)} ({len(suspicious)/len(combined)*100:.1f}%)")
if len(suspicious) > 0:
    print("   Examples:")
    for arm in suspicious['treatment_arm'].unique()[:10]:
        print(f"     - {arm}")

# 4. Missing SE
missing_se = combined[combined['standard_error'].isna()]
print(f"\n4. MISSING STANDARD ERROR: {len(missing_se)} rows ({len(missing_se)/len(combined)*100:.1f}%)")

# 5. Rows per study distribution
print(f"\n5. ROWS PER STUDY DISTRIBUTION:")
print(f"   Min: {stats['rows'].min()}")
print(f"   Max: {stats['rows'].max()}")
print(f"   Mean: {stats['rows'].mean():.1f}")
print(f"   Median: {stats['rows'].median():.1f}")
print(f"   Studies with <10 rows: {len(stats[stats['rows'] < 10])}")
print(f"   Studies with >100 rows: {len(stats[stats['rows'] > 100])}")

# 6. Tables not extracted - why?
print(f"\n6. STUDIES WITH 0 ROWS - LIKELY CAUSES:")
print("   These studies have tables but extraction failed. Possible causes:")
print("   - Table structure different from expected (outcomes in rows)")
print("   - Treatment arm labels not recognized")
print("   - Tables classified as descriptive incorrectly")
