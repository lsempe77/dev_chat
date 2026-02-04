"""
Analyze SE extraction gap - find rows where SE exists in cell but wasn't extracted
"""
import pandas as pd
import re

df = pd.read_csv('extraction_pipeline/outputs/full_corpus_all_studies.csv')

# Find rows where SE pattern exists but SE is null
no_se = df[df['coefficient'].notna() & df['standard_error'].isna()]
se_pattern = re.compile(r'\([\d\.]+\)')

# Count how many have SE in cell text
with_se_in_cell = 0
examples = []

for _, row in no_se.iterrows():
    cell = str(row['literal_cell_text'])
    match = se_pattern.search(cell)
    if match:
        with_se_in_cell += 1
        if len(examples) < 30:
            examples.append({
                'study': row['study_id'],
                'cell': cell[:70],
                'coef': row['coefficient'],
                'expected_se': match.group()
            })

print('='*80)
print('SE EXTRACTION GAP ANALYSIS')
print('='*80)
print()
print('Rows with coefficient but no SE: {:,}'.format(len(no_se)))
print('Of those, have SE pattern in cell: {:,} ({:.1f}%)'.format(with_se_in_cell, with_se_in_cell/len(no_se)*100))
print()
print('This means:')
print('  - {:,} rows CORRECTLY have no SE (cell doesnt contain it)'.format(len(no_se) - with_se_in_cell))
print('  - {:,} rows SHOULD have SE extracted (potential extraction issue)'.format(with_se_in_cell))

# Calculate impact
total_rows = len(df)
current_se = df['standard_error'].notna().sum()
potential_se = current_se + with_se_in_cell
print()
print('Impact:')
print('  Current SE coverage: {:,}/{:,} ({:.1f}%)'.format(current_se, total_rows, current_se/total_rows*100))
print('  Potential SE coverage: {:,}/{:,} ({:.1f}%)'.format(potential_se, total_rows, potential_se/total_rows*100))
print('  Improvement possible: +{:.1f} percentage points'.format((potential_se-current_se)/total_rows*100))

print()
print('='*80)
print('EXAMPLES OF MISSED SE EXTRACTION')
print('='*80)
for ex in examples[:20]:
    print()
    print('Study: {} | Coef: {} | Expected SE: {}'.format(ex['study'], ex['coef'], ex['expected_se']))
    print('  Cell: "{}"'.format(ex['cell']))

# Group by study to see which studies have the most issues
print()
print('='*80)
print('STUDIES WITH MOST MISSED SE')
print('='*80)

study_issues = {}
for _, row in no_se.iterrows():
    cell = str(row['literal_cell_text'])
    if se_pattern.search(cell):
        study = row['study_id']
        study_issues[study] = study_issues.get(study, 0) + 1

sorted_issues = sorted(study_issues.items(), key=lambda x: x[1], reverse=True)
print('\n{:<20} {:>10}'.format('Study', 'Missed SE'))
print('-'*35)
for study, count in sorted_issues[:15]:
    print('{:<20} {:>10}'.format(str(study)[:19], count))
