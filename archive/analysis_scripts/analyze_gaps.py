"""
Deep dive into extraction gaps - find what's truly fixable
"""
import pandas as pd
import re
from extraction_pipeline.pipeline import parse_cell_comprehensive

df = pd.read_csv('extraction_pipeline/outputs/full_corpus_all_studies.csv')

print('='*80)
print('EXTRACTION GAP ANALYSIS')
print('='*80)

# 1. SIGNIFICANCE - 3,248 filled but 3,240 cells have *
print()
print('1. SIGNIFICANCE STARS')
print('-'*60)
# Find cells with * but no significance
has_stars = df['literal_cell_text'].str.contains(r'\*+', na=False)
has_sig = df['significance'].notna() & (df['significance'].astype(str).str.strip() != '')

stars_no_sig = df[has_stars & ~has_sig]
print('Cells with * but no significance: {:,}'.format(len(stars_no_sig)))

if len(stars_no_sig) > 0:
    print('Sample cells:')
    for cell in stars_no_sig['literal_cell_text'].head(10):
        # Re-parse
        parsed = parse_cell_comprehensive(cell)
        print('  Cell: "{}"'.format(cell[:50]))
        print('    Parsed sig: "{}"'.format(parsed['significance']))

# 2. P-VALUE - should we derive from significance?
print()
print('2. P-VALUE DERIVATION FROM SIGNIFICANCE')
print('-'*60)
# Cells with * but no p_value
has_p = df['p_value'].notna()
stars_no_p = df[has_stars & ~has_p]
print('Cells with * but no p_value: {:,}'.format(len(stars_no_p)))
# These could potentially have p_value derived from stars
print('  -> Could derive p_value from stars (* = p<0.05, ** = p<0.01, *** = p<0.001)')

# 3. TABLE NUMBER extraction from caption
print()
print('3. TABLE NUMBER FROM CAPTION')
print('-'*60)
has_caption = df['table_caption'].notna()
has_num = df['table_number'].notna()
cap_no_num = df[has_caption & ~has_num]
print('Has caption but no table_number: {:,}'.format(len(cap_no_num)))

# Check if table number is in caption
table_in_cap = 0
for cap in cap_no_num['table_caption'].head(100):
    if re.search(r'table\s*\d+|appendix\s*\d+', str(cap), re.IGNORECASE):
        table_in_cap += 1

print('  Captions with "Table X" pattern (in first 100): {}'.format(table_in_cap))
print('  Sample captions:')
for cap in cap_no_num['table_caption'].head(5):
    print('    "{}"'.format(str(cap)[:60]))

# 4. CI - check what CI patterns exist
print()
print('4. CONFIDENCE INTERVALS')
print('-'*60)
# Find cells with CI patterns
ci_patterns = df['literal_cell_text'].str.contains(r'\[[\d\.\-,\s]+\]|95%|CI:', case=False, na=False)
has_ci = df['ci_lower'].notna()
print('Cells with CI pattern: {:,}'.format(ci_patterns.sum()))
print('CI actually extracted: {:,}'.format(has_ci.sum()))

ci_not_extracted = df[ci_patterns & ~has_ci]
print('Potential CI not extracted: {:,}'.format(len(ci_not_extracted)))
if len(ci_not_extracted) > 0:
    print('Sample:')
    for cell in ci_not_extracted['literal_cell_text'].head(10):
        parsed = parse_cell_comprehensive(cell)
        print('  Cell: "{}"'.format(cell[:60]))
        print('    Parsed ci_lower: {}, ci_upper: {}'.format(parsed['ci_lower'], parsed['ci_upper']))

# 5. SAMPLE SIZE - check where it could come from
print()
print('5. SAMPLE SIZE / N OBSERVATIONS')
print('-'*60)
# Sample size often comes from table footer, not cell text
# Check table_caption for N= patterns
cap_has_n = df['table_caption'].str.contains(r'N\s*=|observation|sample', case=False, na=False).sum()
print('Captions mentioning N/observations: {:,}'.format(cap_has_n))

# Check if any cell mentions sample size
cell_has_n = df['literal_cell_text'].str.contains(r'N\s*=\s*\d+|observation', case=False, na=False).sum()
print('Cells mentioning N=/observations: {:,}'.format(cell_has_n))
print('sample_size filled: {:,}'.format(df['sample_size'].notna().sum()))

# 6. Truly empty columns - are they expected?
print()
print('6. TRULY EMPTY COLUMNS')
print('-'*60)
empty_cols = ['t_statistic', 'n_treatment', 'table_title', 'treatment_name', 'n_observations', 'subgroup']
for col in empty_cols:
    print('  {}: {} filled'.format(col, df[col].notna().sum()))
print()
print('  These are EXPECTED to be mostly empty:')
print('  - t_statistic: Rarely reported directly')
print('  - n_treatment/n_observations: Usually in table footer, not per-cell')
print('  - table_title: Redundant with table_caption')
print('  - treatment_name: Redundant with treatment_arm')
print('  - subgroup: Only for heterogeneity analyses')
