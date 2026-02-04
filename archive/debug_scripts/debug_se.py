"""
Debug SE extraction issue
"""
import pandas as pd
from extraction_pipeline.pipeline import parse_cell_comprehensive

df = pd.read_csv('extraction_pipeline/outputs/full_corpus_all_studies.csv')

# Find specific examples that should have SE but don't
problems = df[(df['standard_error'].isna()) & (df['literal_cell_text'].str.contains(r'\(\d', regex=True, na=False))]

print('Found {} rows where SE is missing but cell has (number):'.format(len(problems)))
print('='*80)

for _, row in problems.head(15).iterrows():
    cell = row['literal_cell_text']
    
    # Re-parse the cell
    reparsed = parse_cell_comprehensive(cell)
    
    print()
    print('Study: {}'.format(row['study_id']))
    print('Cell: "{}"'.format(cell[:100]))
    print('In CSV -> Coef: {}, SE: {}'.format(row['coefficient'], row['standard_error']))
    print('Reparsed -> Coef: {}, SE: {}'.format(reparsed['coefficient'], reparsed['standard_error']))
    
    if reparsed['standard_error'] is not None:
        print('>>> SE COULD BE EXTRACTED! Pipeline issue.')

# Summary
reparseable = 0
for _, row in problems.iterrows():
    reparsed = parse_cell_comprehensive(row['literal_cell_text'])
    if reparsed['standard_error'] is not None:
        reparseable += 1

print()
print('='*80)
print('SUMMARY:')
print('Total rows with (number) but no SE: {}'.format(len(problems)))
print('Reparseable (parser works): {}'.format(reparseable))
print('Truly not parseable: {}'.format(len(problems) - reparseable))
