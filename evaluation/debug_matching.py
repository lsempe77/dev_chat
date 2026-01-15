import json
import pandas as pd

# Load V5 results
with open('evaluation/v5_test_results.json') as f:
    v5_data = json.load(f)

# Load GT
df = pd.read_excel('8WR QEX Combined.xlsx', sheet_name='Sheet1')

# Check study 121058356
study_id = '121058356'
extraction = [e for e in v5_data['extractions'] if e['study_id'] == study_id][0]
gt = df[df['StudyID'] == int(study_id)]

print(f"Study {study_id}:")
print(f"\nExtracted outcomes ({len(extraction['outcomes'])}):")
for i, o in enumerate(extraction['outcomes'][:5], 1):
    print(f"{i}. {o['outcome_name']} ({o['outcome_category']})")

print(f"\nGT outcomes ({len(gt)} rows, unique names):")
for i, name in enumerate(gt['Outcome name'].drop_duplicates().head(), 1):
    print(f"{i}. {name}")

print("\n--- Name matching test ---")
print("Testing if extracted names match GT...")
ext_names = [o['outcome_name'].lower() for o in extraction['outcomes']]
gt_names = [str(n).lower() for n in gt['Outcome name'].drop_duplicates()]

for gt_name in gt_names[:5]:
    matches = [e for e in ext_names if gt_name in e or e in gt_name or (len(gt_name) > 3 and len(e) > 3 and gt_name[:4] == e[:4])]
    if matches:
        print(f"✓ GT: '{gt_name}' matches: {matches[:2]}")
    else:
        print(f"✗ GT: '{gt_name}' - no match")
