"""Analyze unmatched outcomes from V13 results."""
import json
from pathlib import Path

# Load V13 results
with open('extraction_pipeline/v13_results.json') as f:
    results = json.load(f)

# Load ground truth for outcome names
with open('evaluation/matched_studies_r2.json') as f:
    gt_studies = json.load(f)

# Create GT lookup by study_id
gt_lookup = {s['study_id']: s for s in gt_studies}

# Analyze studies without 100% recall
print('=' * 80)
print('STUDIES WITHOUT 100% RECALL')
print('=' * 80)

problem_studies = []
all_unmatched = []

for study in results['studies']:
    if study.get('recall', 0) < 1.0 and study.get('success'):
        study_id = study['study_id']
        gt_data = gt_lookup.get(study_id, {})
        gt_outcomes = gt_data.get('ground_truth', {}).get('outcomes', [])
        
        unmatched_indices = study.get('unmatched_gt_indices', [])
        unmatched_names = [gt_outcomes[i]['name'] for i in unmatched_indices if i < len(gt_outcomes)]
        
        n_gt = study['n_gt_outcomes']
        n_matched = study['n_matched']
        n_extracted = study['n_extracted']
        recall = study['recall'] * 100
        
        # Also get extracted outcome names for comparison
        extracted_names = [o.get('outcome_name', '') for o in study.get('extracted_outcomes', [])]
        
        problem_studies.append({
            'author': study['author'],
            'study_id': study_id,
            'n_gt': n_gt,
            'n_matched': n_matched,
            'n_unmatched': len(unmatched_names),
            'recall': recall,
            'n_extracted': n_extracted,
            'unmatched': unmatched_names,
            'extracted': extracted_names[:20]  # First 20
        })
        
        all_unmatched.extend(unmatched_names)

# Sort by number of unmatched
problem_studies.sort(key=lambda x: x['n_unmatched'], reverse=True)

print(f"\nTotal studies without 100% recall: {len(problem_studies)}")
print(f"Total unmatched outcomes: {len(all_unmatched)}")
print()

for ps in problem_studies:
    print(f"\n{'='*60}")
    print(f"{ps['author']}")
    print(f"  Matched: {ps['n_matched']}/{ps['n_gt']} ({ps['recall']:.1f}% recall)")
    print(f"  Extracted: {ps['n_extracted']} outcomes")
    print(f"  UNMATCHED GT ({ps['n_unmatched']}):")
    for name in ps['unmatched']:
        print(f"    ❌ {name}")
    print(f"  SAMPLE EXTRACTED:")
    for name in ps['extracted'][:5]:
        print(f"    ✓ {name}")
    if len(ps['extracted']) > 5:
        print(f"    ... and {len(ps['extracted']) - 5} more extracted")

print()
print('=' * 80)
print('CATEGORIZING UNMATCHED OUTCOMES')
print('=' * 80)

# Categorize unmatched outcomes
categories = {
    'subgroup_specific': [],
    'index_composite': [],
    'ratio_percentage': [],
    'time_specific': [],
    'monetary': [],
    'count_number': [],
    'other': []
}

for name in all_unmatched:
    name_lower = name.lower()
    if any(x in name_lower for x in ['female', 'male', 'girl', 'boy', 'women', 'men', 'child', 'adult']):
        categories['subgroup_specific'].append(name)
    elif any(x in name_lower for x in ['index', 'score', 'composite', 'pca', 'scale', 'z-score']):
        categories['index_composite'].append(name)
    elif any(x in name_lower for x in ['ratio', 'percent', 'share', 'rate', 'proportion']):
        categories['ratio_percentage'].append(name)
    elif any(x in name_lower for x in ['month', 'year', 'day', 'week', 'annual', 'daily']):
        categories['time_specific'].append(name)
    elif any(x in name_lower for x in ['usd', 'dollar', 'cost', 'price', 'value', 'expenditure', 'income', 'wage', 'earning', 'consumption']):
        categories['monetary'].append(name)
    elif any(x in name_lower for x in ['number', 'count', 'total', 'quantity']):
        categories['count_number'].append(name)
    else:
        categories['other'].append(name)

print()
for cat, items in sorted(categories.items(), key=lambda x: -len(x[1])):
    if items:
        print(f"\n{cat.upper()}: {len(items)} outcomes")
        for item in items:
            print(f"  - {item}")

# Save detailed analysis
analysis = {
    'summary': {
        'total_unmatched': len(all_unmatched),
        'studies_without_100_recall': len(problem_studies),
        'categories': {k: len(v) for k, v in categories.items()}
    },
    'problem_studies': problem_studies,
    'unmatched_by_category': categories
}

with open('extraction_pipeline/v13_unmatched_analysis.json', 'w') as f:
    json.dump(analysis, f, indent=2)

print("\nAnalysis saved to extraction_pipeline/v13_unmatched_analysis.json")
