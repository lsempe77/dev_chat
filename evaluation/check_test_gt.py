import pandas as pd

df = pd.read_excel('8WR QEX Combined.xlsx', sheet_name='Sheet1')
studies = ['121058356', '121058359', '121058364']

for s in studies:
    print(f'\n{s}:')
    outcomes = df[df['StudyID'] == int(s)]
    print(f'GT outcomes: {len(outcomes)}')
    if len(outcomes) > 0:
        print(outcomes[['Outcome name', 'Outcome category']].head(5).to_string(index=False))
