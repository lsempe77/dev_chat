"""Export full extraction results to CSV for GT upgrade."""

import json
import pandas as pd

# Load the most complete results
with open('v17d_cohens_d_results.json') as f:
    data = json.load(f)

rows = []
for study in data['studies']:
    author = study['author']
    study_id = study['study_id']
    
    for outcome in study.get('enriched_outcomes', []):
        rows.append({
            'study_id': study_id,
            'author': author,
            'outcome_name': outcome.get('outcome_name'),
            'table_source': outcome.get('table_source'),
            'coefficient': outcome.get('coefficient'),
            'standard_error': outcome.get('standard_error'),
            'p_value': outcome.get('p_value'),
            'significance_stars': outcome.get('significance_stars'),
            'ci_lower': outcome.get('confidence_interval_lower'),
            'ci_upper': outcome.get('confidence_interval_upper'),
            'sample_size': outcome.get('sample_size'),
            'cohens_d': outcome.get('cohens_d'),
            'cohens_d_method': outcome.get('cohens_d_method'),
            'control_sd': outcome.get('control_sd'),
        })

df = pd.DataFrame(rows)

print(f"Total outcomes: {len(df)}")
print(f"With coefficient: {df['coefficient'].notna().sum()}")
print(f"With SE: {df['standard_error'].notna().sum()}")
print(f"With Cohen's d: {df['cohens_d'].notna().sum()}")
print()
print("By study:")
print(df.groupby('author').size())
print()

# Save full dataset
df.to_csv('extracted_outcomes_full.csv', index=False)
print("Saved to: extracted_outcomes_full.csv")

# Also save Excel for easier review
df.to_excel('extracted_outcomes_full.xlsx', index=False)
print("Saved to: extracted_outcomes_full.xlsx")
