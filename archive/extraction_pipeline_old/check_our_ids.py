"""Check study IDs in our results."""

import json

# Check our cohens_d results
with open('v17d_cohens_d_results.json') as f:
    results = json.load(f)

print('Our studies:')
for study in results['studies']:
    sid = study.get('study_id', '?')
    author = study.get('author', '?')
    n = len(study.get('enriched_outcomes', []))
    print(f'  {sid}: {author} ({n} outcomes)')
