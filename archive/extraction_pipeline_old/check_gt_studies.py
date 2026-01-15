"""Check ground truth for Banerjee and Alderman studies."""

import json
from pathlib import Path

gt_path = Path('..') / 'evaluation' / 'matched_studies_r2.json'
with open(gt_path) as f:
    gt = json.load(f)

# Check Banerjee 
for study in gt:
    title = study.get('title', study.get('study_id', ''))
    if 'Banerjee' in title or 'multifaceted' in title.lower():
        print(f"\n{'='*70}")
        print(f"Study: {title}")
        print('='*70)
        outcomes = study.get('ground_truth', {}).get('outcomes', [])
        for o in outcomes:
            name = o.get('name', '')
            d = o.get('effect_size_d')
            print(f"  {name}: d={d}")

# Check Alderman
for study in gt:
    title = study.get('title', study.get('study_id', ''))
    if 'Alderman' in title or 'niger' in title.lower():
        print(f"\n{'='*70}")
        print(f"Study: {title}")
        print('='*70)
        outcomes = study.get('ground_truth', {}).get('outcomes', [])
        for o in outcomes:
            name = o.get('name', '')
            d = o.get('effect_size_d')
            print(f"  {name}: d={d}")
