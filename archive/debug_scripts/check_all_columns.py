"""
Comprehensive column analysis - check if empty columns are bugs or expected
"""
import pandas as pd
import re

df = pd.read_csv('extraction_pipeline/outputs/full_corpus_all_studies.csv')

print('='*80)
print('COMPREHENSIVE COLUMN ANALYSIS - {:,} rows'.format(len(df)))
print('='*80)

# Analyze each column
for col in df.columns:
    filled = df[col].notna().sum()
    # For string columns, also check for empty strings
    if df[col].dtype == 'object':
        non_empty = df[col].apply(lambda x: pd.notna(x) and str(x).strip() not in ['', 'nan', 'None']).sum()
    else:
        non_empty = filled
    
    pct = non_empty / len(df) * 100
    
    # Determine if this is expected or a potential bug
    if pct >= 80:
        status = 'OK'
    elif pct >= 30:
        status = 'MEDIUM'
    elif pct > 0:
        status = 'LOW'
    else:
        status = 'EMPTY'
    
    print('{:<25} {:>6,}/{:>6,} ({:>5.1f}%) - {}'.format(col, non_empty, len(df), pct, status))

# Detailed analysis of LOW/EMPTY columns
print()
print('='*80)
print('DETAILED ANALYSIS OF LOW-FILL COLUMNS')
print('='*80)

low_cols = [
    'p_value', 'p_value_text', 'significance',
    'sample_size', 'control_mean', 'control_sd',
    'n_treatment', 'n_control', 'n_clusters', 'n_observations',
    'ci_lower', 'ci_upper', 't_statistic',
    'section', 'extraction_source', 'effect_direction',
    'table_title', 'treatment_name', 'subgroup'
]

for col in low_cols:
    if col not in df.columns:
        continue
    
    filled = df[col].notna().sum()
    if df[col].dtype == 'object':
        non_empty = df[col].apply(lambda x: pd.notna(x) and str(x).strip() not in ['', 'nan', 'None']).sum()
    else:
        non_empty = filled
    
    print()
    print('--- {} ({:,} filled, {:.1f}%) ---'.format(col, non_empty, non_empty/len(df)*100))
    
    # Sample values
    if non_empty > 0:
        sample = df[df[col].notna()][col].head(5).tolist()
        print('  Sample values: {}'.format(sample[:3]))
    
    # Check if data exists in literal_cell_text but wasn't extracted
    if col == 'sample_size':
        # Check for "Observations" or "N=" patterns
        has_obs = df['literal_cell_text'].str.contains(r'observation|N\s*=|sample', case=False, na=False).sum()
        print('  Cells mentioning observations/N/sample: {:,}'.format(has_obs))
    
    elif col == 'control_mean':
        # Check for "Control mean" patterns
        has_cm = df['literal_cell_text'].str.contains(r'control.*mean|mean.*control', case=False, na=False).sum()
        print('  Cells mentioning control mean: {:,}'.format(has_cm))
    
    elif col in ['ci_lower', 'ci_upper']:
        # Check for CI patterns [x, y] or 95% CI
        has_ci = df['literal_cell_text'].str.contains(r'\[.*,.*\]|95%|CI', case=False, na=False).sum()
        print('  Cells with CI pattern: {:,}'.format(has_ci))
    
    elif col == 'significance':
        # Check for star patterns
        has_stars = df['literal_cell_text'].str.contains(r'\*', na=False).sum()
        print('  Cells with * pattern: {:,}'.format(has_stars))

# Check specific extraction issues
print()
print('='*80)
print('EXTRACTION ISSUE CHECK')
print('='*80)

# 1. Significance stars - should match cells with *
has_stars = df['literal_cell_text'].str.contains(r'\*', na=False)
has_sig = df['significance'].notna() & (df['significance'] != '')
print()
print('1. SIGNIFICANCE STARS:')
print('   Cells with *: {:,}'.format(has_stars.sum()))
print('   Significance filled: {:,}'.format(has_sig.sum()))
if has_stars.sum() > has_sig.sum():
    print('   >>> POTENTIAL ISSUE: {:,} cells have * but no significance extracted'.format(
        has_stars.sum() - has_sig.sum()))
    # Sample
    missing_sig = df[has_stars & ~has_sig]['literal_cell_text'].head(5)
    for cell in missing_sig:
        print('      "{}"'.format(cell[:60]))

# 2. P-value - check if significance exists but no p_value
print()
print('2. P-VALUE:')
has_p = df['p_value'].notna()
print('   P-value filled: {:,}'.format(has_p.sum()))
print('   Significance filled: {:,}'.format(has_sig.sum()))
# Check if p_value should be derivable from significance
sig_no_p = (has_sig & ~has_p).sum()
print('   Has significance but no p_value: {:,}'.format(sig_no_p))

# 3. Sample size - check table footers
print()
print('3. SAMPLE SIZE / OBSERVATIONS:')
# Check if tables have Observations rows
obs_pattern = df['literal_cell_text'].str.lower().str.contains('observation', na=False)
print('   Cells mentioning "observation": {:,}'.format(obs_pattern.sum()))
print('   sample_size filled: {:,}'.format(df['sample_size'].notna().sum()))

# 4. Control mean/SD
print()
print('4. CONTROL MEAN / SD:')
cm_pattern = df['literal_cell_text'].str.lower().str.contains('control', na=False)
print('   Cells mentioning "control": {:,}'.format(cm_pattern.sum()))
print('   control_mean filled: {:,}'.format(df['control_mean'].notna().sum()))
print('   control_sd filled: {:,}'.format(df['control_sd'].notna().sum()))

# 5. Table number
print()
print('5. TABLE NUMBER:')
print('   table_number filled: {:,}'.format(df['table_number'].notna().sum()))
print('   table_caption filled: {:,}'.format(df['table_caption'].notna().sum()))
# Check if table_number can be extracted from caption
has_caption_no_num = (df['table_caption'].notna() & df['table_number'].isna())
print('   Has caption but no table_number: {:,}'.format(has_caption_no_num.sum()))
if has_caption_no_num.sum() > 0:
    sample = df[has_caption_no_num]['table_caption'].head(3)
    for cap in sample:
        print('      "{}"'.format(str(cap)[:60]))
