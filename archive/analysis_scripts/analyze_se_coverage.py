"""
Analyze why standard_error is only 53% filled
"""
import pandas as pd

df = pd.read_csv('extraction_pipeline/outputs/full_corpus_all_studies.csv')

print('='*80)
print('STANDARD ERROR ANALYSIS - Why is it only 53%?')
print('='*80)

# Check by study which have SE vs not
study_stats = df.groupby('study_id').agg({
    'coefficient': lambda x: x.notna().sum(),
    'standard_error': lambda x: x.notna().sum()
}).reset_index()
study_stats.columns = ['study_id', 'coef_count', 'se_count']
study_stats['se_pct'] = (study_stats['se_count'] / study_stats['coef_count'] * 100).round(1)
study_stats['missing_se'] = study_stats['coef_count'] - study_stats['se_count']

# Studies with low SE coverage
low_se = study_stats[study_stats['se_pct'] < 50].sort_values('missing_se', ascending=False)
print('\nStudies with <50% SE coverage (sorted by missing SE count):')
print('{:<15} {:>10} {:>10} {:>10} {:>10}'.format('study_id', 'coef', 'se', 'missing', 'se_pct'))
print('-'*60)
for _, row in low_se.head(20).iterrows():
    print('{:<15} {:>10} {:>10} {:>10} {:>9.1f}%'.format(
        str(row['study_id'])[:14], 
        int(row['coef_count']), 
        int(row['se_count']), 
        int(row['missing_se']),
        row['se_pct']))

# Total missing
total_missing = study_stats['missing_se'].sum()
print('\nTotal rows missing SE: {:,}'.format(int(total_missing)))

# Sample rows without SE
print('\n' + '='*80)
print('SAMPLE: Rows with coefficient but NO standard_error')
print('='*80)
no_se = df[df['coefficient'].notna() & df['standard_error'].isna()]

# Group by study to see patterns
for study_id in no_se['study_id'].unique()[:5]:
    study_no_se = no_se[no_se['study_id'] == study_id]
    print('\n--- Study {} ({} rows missing SE) ---'.format(study_id, len(study_no_se)))
    
    for _, row in study_no_se.head(3).iterrows():
        caption = str(row['table_caption'])[:70] if pd.notna(row['table_caption']) else 'N/A'
        outcome = str(row['outcome_name'])[:50]
        cell = str(row['literal_cell_text'])[:80]
        print('  Table: {}'.format(caption))
        print('  Outcome: {}'.format(outcome))
        print('  Coef: {}'.format(row['coefficient']))
        print('  Cell: {}'.format(cell))
        print()

# Check if SE might be parseable from cell text
print('='*80)
print('CHECKING IF SE IS IN CELL TEXT BUT NOT EXTRACTED')
print('='*80)

import re

# Pattern for SE in parentheses
se_pattern = re.compile(r'\([\d\.]+\)')

parseable = 0
not_parseable = 0

for _, row in no_se.head(200).iterrows():
    cell = str(row['literal_cell_text'])
    if se_pattern.search(cell):
        parseable += 1
    else:
        not_parseable += 1

print('\nIn first 200 rows without SE:')
print('  Has (number) pattern: {} ({:.1f}%) - SE might be parseable'.format(parseable, parseable/200*100))
print('  No (number) pattern: {} ({:.1f}%) - SE truly not in cell'.format(not_parseable, not_parseable/200*100))

# Show examples where SE pattern exists but wasn't extracted
print('\nExamples where SE pattern exists but wasnt extracted:')
count = 0
for _, row in no_se.iterrows():
    cell = str(row['literal_cell_text'])
    if se_pattern.search(cell) and count < 10:
        print('  Cell: "{}"'.format(cell[:80]))
        count += 1
