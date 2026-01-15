"""Analyze V1 baseline extraction results for metadata accuracy."""
import json
import pandas as pd

# Load V1 baseline
with open('evaluation/baseline_extraction_results.json') as f:
    v1 = json.load(f)

results = v1.get('results', [])

print('=== V1 BASELINE FULL ANALYSIS ===')
print(f"Model: {v1.get('model')}")
print(f"Studies: {v1.get('num_studies')}")
print(f"Overall accuracy: {v1.get('overall_accuracy')}")
print()

# Check all extracted fields across all results
all_fields = set()
for r in results:
    all_fields.update(r.get('extracted', {}).keys())

print('All extracted fields:', sorted(all_fields))
print()

# Check accuracy breakdown
accuracy_data = []
for r in results:
    acc = r.get('accuracy', {})
    for field, match in acc.items():
        accuracy_data.append({'study_id': r['study_id'], 'field': field, 'match': match})

if accuracy_data:
    df = pd.DataFrame(accuracy_data)
    print('Accuracy by field:')
    by_field = df.groupby('field')['match'].agg(['sum', 'count', 'mean'])
    for field, row in by_field.iterrows():
        pct = row['mean'] * 100
        print(f"  {field}: {int(row['sum'])}/{int(row['count'])} = {pct:.1f}%")
    print()
    
    # Show missed cases
    print('=== MISSED CASES ===')
    for r in results:
        acc = r.get('accuracy', {})
        missed = [f for f, v in acc.items() if not v]
        if missed:
            print(f"Study {r['study_id']}: missed {missed}")
