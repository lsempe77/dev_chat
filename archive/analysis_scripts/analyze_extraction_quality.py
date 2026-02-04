"""
Analyze column completeness in the full corpus extraction
"""
import pandas as pd
import numpy as np

# Load the full dataset
df = pd.read_csv('extraction_pipeline/outputs/full_corpus_all_studies.csv')

print('='*80)
print('COLUMN COMPLETENESS ANALYSIS - {:,} rows'.format(len(df)))
print('='*80)
print()

# Calculate fill rates for each column
fill_rates = []
for col in df.columns:
    non_null = df[col].notna().sum()
    # For string columns, also check for empty strings
    if df[col].dtype == 'object':
        non_empty = df[col].apply(lambda x: x != '' and pd.notna(x) and str(x).strip() != '').sum()
    else:
        non_empty = non_null
    fill_pct = (non_empty / len(df)) * 100
    fill_rates.append({
        'column': col,
        'filled': non_empty,
        'empty': len(df) - non_empty,
        'fill_pct': fill_pct
    })

fill_df = pd.DataFrame(fill_rates).sort_values('fill_pct', ascending=False)

# Print results
print("{:<25} {:>8} {:>8} {:>8}".format('Column', 'Filled', 'Empty', 'Fill %'))
print('-'*55)
for _, row in fill_df.iterrows():
    status = '✅' if row['fill_pct'] >= 80 else '⚠️' if row['fill_pct'] >= 30 else '❌'
    print("{:<25} {:>8,} {:>8,} {:>7.1f}% {}".format(
        row['column'][:24], int(row['filled']), int(row['empty']), row['fill_pct'], status))

# Categorize columns
print()
print('='*80)
print('SUMMARY BY CATEGORY')
print('='*80)
high_fill = fill_df[fill_df['fill_pct'] >= 80]['column'].tolist()
medium_fill = fill_df[(fill_df['fill_pct'] >= 30) & (fill_df['fill_pct'] < 80)]['column'].tolist()
low_fill = fill_df[fill_df['fill_pct'] < 30]['column'].tolist()

print('\n✅ HIGH (>=80%): {} columns'.format(len(high_fill)))
for c in high_fill:
    print('   - {}'.format(c))

print('\n⚠️ MEDIUM (30-80%): {} columns'.format(len(medium_fill)))
for c in medium_fill:
    print('   - {}'.format(c))

print('\n❌ LOW (<30%): {} columns'.format(len(low_fill)))
for c in low_fill:
    print('   - {}'.format(c))

# Detailed analysis of low-fill columns
print()
print('='*80)
print('DETAILED ANALYSIS OF LOW-FILL COLUMNS')
print('='*80)

for col in low_fill:
    print('\n--- {} ({:.1f}% filled) ---'.format(col, fill_df[fill_df['column']==col]['fill_pct'].values[0]))
    
    # Sample non-empty values
    non_empty = df[df[col].notna() & (df[col] != '')][col]
    if len(non_empty) > 0:
        print('Sample values:')
        for v in non_empty.head(5).values:
            print('  "{}"'.format(str(v)[:60]))
    else:
        print('  No values found')

# Check coefficient and SE coverage (critical fields)
print()
print('='*80)
print('CRITICAL FIELDS ANALYSIS')
print('='*80)

# Coefficient
coef_filled = df['coefficient'].notna().sum()
print('\ncoefficient: {:,}/{:,} ({:.1f}%)'.format(coef_filled, len(df), coef_filled/len(df)*100))

# Standard Error
se_filled = df['standard_error'].notna().sum()
print('standard_error: {:,}/{:,} ({:.1f}%)'.format(se_filled, len(df), se_filled/len(df)*100))

# Both coefficient AND SE
both = (df['coefficient'].notna() & df['standard_error'].notna()).sum()
print('Both coef + SE: {:,}/{:,} ({:.1f}%)'.format(both, len(df), both/len(df)*100))

# Rows with coefficient but no SE
coef_no_se = (df['coefficient'].notna() & df['standard_error'].isna()).sum()
print('Coef but NO SE: {:,}/{:,} ({:.1f}%)'.format(coef_no_se, len(df), coef_no_se/len(df)*100))

# Sample rows with coefficient but no SE
print('\nSample rows with coefficient but NO standard_error:')
sample = df[df['coefficient'].notna() & df['standard_error'].isna()][['study_id', 'outcome_name', 'coefficient', 'literal_cell_text']].head(10)
print(sample.to_string())
