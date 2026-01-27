"""Get sample values from QEX file."""
import pandas as pd

qex = pd.read_excel('data/8WR QEX Combined.xlsx', sheet_name='Sheet1')

print('=== SAMPLE VALUES FROM QEX ===')
sample = qex[['StudyID', 'Coeff reg', 'd']].head(5)
print(sample.to_string())

print('\n=== ALL COLUMN NAMES ===')
for i, col in enumerate(qex.columns):
    print(f'{i:3d}: {col}')
