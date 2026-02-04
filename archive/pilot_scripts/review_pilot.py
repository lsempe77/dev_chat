"""Review pilot study extractions for blunt errors."""
import pandas as pd

# Check pilot study 1 results
print('='*70)
print('PILOT 1: 121058367 (Ethiopia SPIR) - Sample of extracted data')
print('='*70)
df = pd.read_csv('extraction_pipeline/outputs/121058367/extracted_data.csv')
print(f'Total rows: {len(df)}')
print(f'Unique outcomes: {df["outcome_name"].nunique()}')
print(f'Unique tables: {df["table_caption"].nunique()}')
print()

# Show sample of key columns
cols = ['table_number', 'treatment_arm', 'outcome_name', 'coefficient', 'standard_error', 'significance']
print('Sample rows (first 15):')
print(df[cols].head(15).to_string())
print()
print('Sample rows (random 15):')
print(df[cols].sample(15).to_string())
print()

# Check for obvious errors
print('='*70)
print('QUICK ERROR CHECKS')
print('='*70)

# 1. Check coefficient ranges
print(f'Coefficient range: {df["coefficient"].min():.4f} to {df["coefficient"].max():.4f}')

# 2. Check SE ranges
se_valid = df[df['standard_error'].notna()]
if len(se_valid) > 0:
    print(f'SE range: {se_valid["standard_error"].min():.4f} to {se_valid["standard_error"].max():.4f}')

# 3. Check for suspicious patterns
print(f'Rows with SE > coefficient (abs): {len(df[df["standard_error"] > abs(df["coefficient"])])}')
print(f'Rows with very large coefficients (>100): {len(df[abs(df["coefficient"]) > 100])}')

# 4. Check treatment arms
print(f'\nTreatment arms found:')
print(df['treatment_arm'].value_counts())
