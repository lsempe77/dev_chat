"""List all studies in ground truth."""

import json

with open('../evaluation/matched_studies_r2.json') as f:
    gt = json.load(f)

print('Studies in GT:')
for study in gt:
    study_id = study.get('study_id', 'no_id')
    title = study.get('title', 'no_title')[:60]
    n_outcomes = len(study.get('ground_truth', {}).get('outcomes', []))
    print(f'  {study_id}: {title} ({n_outcomes} outcomes)')
    
    # Show outcomes
    outcomes = study.get('ground_truth', {}).get('outcomes', [])
    for o in outcomes[:3]:
        name = o.get('name', '')[:50]
        d = o.get('effect_size_d')
        print(f'    - {name}: d={d}')
    if len(outcomes) > 3:
        print(f'    ... and {len(outcomes)-3} more')
