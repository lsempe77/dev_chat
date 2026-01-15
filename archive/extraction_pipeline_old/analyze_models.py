"""
Analyze model performance and extraction stability across V11, V12, V13.
"""
import json
from pathlib import Path
from collections import defaultdict

print('=' * 80)
print('MODEL AND EXTRACTION STABILITY ANALYSIS')
print('=' * 80)

# Load V13 results
v13_path = Path('extraction_pipeline/v13_results.json')
with open(v13_path) as f:
    v13_results = json.load(f)

# Try to load V12 results if available
v12_path = Path('extraction_pipeline/v12_results.json')
v12_results = None
if v12_path.exists():
    with open(v12_path) as f:
        v12_results = json.load(f)

# Load ground truth
with open('evaluation/matched_studies_r2.json') as f:
    gt_studies = json.load(f)
gt_lookup = {s['study_id']: s for s in gt_studies}

print('\n' + '=' * 80)
print('1. EXTRACTION VARIABILITY ACROSS VERSIONS')
print('=' * 80)

# Compare V12 vs V13 extraction counts
if v12_results:
    print('\nStudy-by-study comparison:')
    print(f"{'Study':<30} {'V12 Ext':>10} {'V13 Ext':>10} {'Diff':>10} {'V12 Match':>10} {'V13 Match':>10}")
    print('-' * 80)
    
    v12_by_id = {s['study_id']: s for s in v12_results.get('studies', [])}
    
    for v13_study in v13_results['studies']:
        study_id = v13_study['study_id']
        v12_study = v12_by_id.get(study_id, {})
        
        v12_ext = v12_study.get('num_outcomes_extracted', 0)
        v13_ext = v13_study.get('n_extracted', 0)
        v12_match = v12_study.get('num_matched', 0)
        v13_match = v13_study.get('n_matched', 0)
        
        diff = v13_ext - v12_ext
        author = v13_study.get('author', study_id)[:28]
        
        print(f"{author:<30} {v12_ext:>10} {v13_ext:>10} {diff:>+10} {v12_match:>10} {v13_match:>10}")

print('\n' + '=' * 80)
print('2. MODEL CONTRIBUTION ANALYSIS')
print('=' * 80)

# V13 uses parallel extraction - let's trace what each model finds
# We need to look at the raw extraction logs or modify the code

# For now, analyze outcomes by looking at patterns
print('''
Current V13 approach:
- Claude 3.5 Sonnet: extracts outcomes in parallel
- GPT-4o-2024-11-20: extracts outcomes in parallel  
- Results are UNIONED then deduplicated

To properly compare models, we need to run them separately.
''')

# Look at a sample study's extraction pattern
print('\n' + '=' * 80)
print('3. SAMPLE EXTRACTION ANALYSIS')
print('=' * 80)

for study in v13_results['studies'][:3]:
    if not study.get('success'):
        continue
    
    print(f"\n--- {study['author']} ---")
    print(f"Tables: {study.get('n_tables', 0)}")
    print(f"GT outcomes: {study['n_gt_outcomes']}")
    print(f"Extracted: {study['n_extracted']}")
    print(f"Matched: {study['n_matched']} ({study['recall']*100:.1f}% recall)")
    
    # Show matches with details
    matches = study.get('matches', [])
    print(f"\nMatches (showing first 5):")
    for m in matches[:5]:
        print(f"  EXTRACTED: '{m.get('extracted_name', '')}'")
        print(f"  GT:        '{m.get('gt_name', '')}'")
        print(f"  Type: {m.get('match_type', '')} | Similarity: {m.get('similarity', {})}")
        print()

print('\n' + '=' * 80)
print('4. RECOMMENDATIONS')
print('=' * 80)

print('''
KEY ISSUES IDENTIFIED:

1. NO SOURCE TRACKING: Current pipeline doesn't track which model found each outcome
   SOLUTION: Add 'source_model' field to each extracted outcome

2. UNION APPROACH: We're combining all model outputs, which increases noise
   ALTERNATIVE: Only keep outcomes found by BOTH models (intersection)

3. DEDUPLICATION VARIANCE: 0.55 threshold may be too aggressive or not enough
   NEED: Test different thresholds systematically

4. GENERIC GT NAMES: Many GT outcomes are just "Assets", "Income", "Expenditure"
   SOLUTION: Use substring matching or LLM-based semantic expansion

NEXT STEPS FOR V14:
1. Track source model for each outcome
2. Add literal text extraction (the actual cell/sentence where outcome was found)
3. Test ensemble strategies: union vs intersection vs voting
4. Improve matching for generic GT names
''')

# Save analysis
analysis = {
    'v13_summary': v13_results.get('summary', {}),
    'recommendations': [
        'Add source_model tracking',
        'Add literal_text field',
        'Test union vs intersection ensemble',
        'Improve generic name matching'
    ]
}

with open('extraction_pipeline/model_analysis.json', 'w') as f:
    json.dump(analysis, f, indent=2)

print('\nAnalysis saved to extraction_pipeline/model_analysis.json')
