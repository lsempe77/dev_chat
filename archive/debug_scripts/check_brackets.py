"""Check what [number] pattern represents"""
import pandas as pd
df = pd.read_csv('extraction_pipeline/outputs/full_corpus_all_studies.csv')

# Find cells with [number] pattern
bracket_cells = df[df['literal_cell_text'].str.contains(r'\[\d', na=False)]
print('Cells with [number] pattern: {:,}'.format(len(bracket_cells)))

# Sample them
print()
print('Sample cells with [X] pattern:')
for cell in bracket_cells['literal_cell_text'].head(30):
    print('  "{}"'.format(cell[:70]))

# Check if these are p-values (single number in brackets) vs CI (two numbers)
import re
single_bracket = 0
double_bracket = 0

for cell in bracket_cells['literal_cell_text']:
    # Single number in brackets = p-value
    if re.search(r'\[[\d\.]+\]', cell) and not re.search(r'\[[\d\.]+\s*[,\-]\s*[\d\.]+\]', cell):
        single_bracket += 1
    # Two numbers = CI
    elif re.search(r'\[[\d\.]+\s*[,\-]\s*[\d\.]+\]', cell):
        double_bracket += 1

print()
print('Single number in brackets (likely p-value): {:,}'.format(single_bracket))
print('Two numbers in brackets (likely CI): {:,}'.format(double_bracket))
