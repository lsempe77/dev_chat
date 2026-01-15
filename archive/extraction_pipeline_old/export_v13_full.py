"""Export V13 results (most extensive extraction - 43 studies, 2548 outcomes)."""

import json
import pandas as pd

# Load V13 results
with open('v13_results.json') as f:
    data = json.load(f)

rows = []

# V13 structure is different - check format
if 'studies' in data:
    for study in data['studies']:
        study_id = study.get('study_id', '')
        author = study.get('author', '')
        
        for outcome in study.get('extracted_outcomes', []):
            rows.append({
                'study_id': study_id,
                'author': author,
                'outcome_name': outcome.get('outcome_name', outcome.get('name', '')),
                'table_source': outcome.get('table_source', ''),
                'coefficient': outcome.get('coefficient', outcome.get('value', None)),
                'standard_error': outcome.get('standard_error', outcome.get('se', None)),
                'p_value': outcome.get('p_value', None),
                'confidence_interval': outcome.get('confidence_interval', None),
                'sample_size': outcome.get('sample_size', outcome.get('n', None)),
                'source_model': outcome.get('source_model', ''),
                'category': outcome.get('category', ''),
            })
else:
    # Try different structure
    for study_id, study_data in data.items():
        if isinstance(study_data, dict):
            extracted = study_data.get('extracted', study_data.get('extracted_outcomes', []))
            for outcome in extracted:
                rows.append({
                    'study_id': study_id,
                    'outcome_name': outcome.get('outcome_name', outcome.get('name', '')),
                    'table_source': outcome.get('table_source', ''),
                    'coefficient': outcome.get('coefficient', outcome.get('value', None)),
                    'standard_error': outcome.get('standard_error', outcome.get('se', None)),
                    'p_value': outcome.get('p_value', None),
                    'sample_size': outcome.get('sample_size', outcome.get('n', None)),
                    'source_model': outcome.get('source_model', ''),
                })

df = pd.DataFrame(rows)

print(f"Total outcomes: {len(df)}")
print(f"Unique studies: {df['study_id'].nunique()}")

if 'coefficient' in df.columns:
    print(f"With coefficient: {df['coefficient'].notna().sum()}")
if 'standard_error' in df.columns:
    print(f"With SE: {df['standard_error'].notna().sum()}")

print()
print("Sample rows:")
print(df.head(10).to_string())

# Save
df.to_csv('v13_extracted_outcomes_full.csv', index=False)
df.to_excel('v13_extracted_outcomes_full.xlsx', index=False)
print()
print("Saved to: v13_extracted_outcomes_full.csv")
print("Saved to: v13_extracted_outcomes_full.xlsx")
