"""
Analyze BRAC_Emran_2012 SE issues
"""
import pandas as pd
import re
from extraction_pipeline.pipeline import parse_cell_comprehensive

df = pd.read_csv('extraction_pipeline/outputs/full_corpus_all_studies.csv')

# Check BRAC_Emran_2012 specifically
emran = df[df['study_id'] == 'BRAC_Emran_2012']
print('='*80)
print('BRAC_Emran_2012 ANALYSIS')
print('='*80)
print()
print('Total rows: {}'.format(len(emran)))
print('With SE: {}'.format(emran['standard_error'].notna().sum()))
print('Without SE: {}'.format(emran['standard_error'].isna().sum()))
print()

# Sample rows without SE
no_se = emran[emran['standard_error'].isna()]
print('Rows without SE (sample):')
print('-'*80)
for _, row in no_se.head(20).iterrows():
    cell = row['literal_cell_text']
    reparsed = parse_cell_comprehensive(cell)
    
    print('Cell: "{}"'.format(cell[:70]))
    print('  In CSV: coef={}, SE={}'.format(row['coefficient'], row['standard_error']))
    print('  Reparsed: coef={}, SE={}'.format(reparsed['coefficient'], reparsed['standard_error']))
    
    # Check if cell has SE pattern
    if re.search(r'\([\d\.]+\)', cell):
        print('  >>> Has (number) but SE missing!')
    print()

# Summary by table
print()
print('='*80)
print('BY TABLE')
print('='*80)
table_stats = emran.groupby('table_caption').agg({
    'coefficient': 'count',
    'standard_error': lambda x: x.notna().sum()
}).reset_index()
table_stats.columns = ['table', 'rows', 'se_count']
table_stats['missing'] = table_stats['rows'] - table_stats['se_count']
print(table_stats[table_stats['missing'] > 0].to_string())
