"""Re-analyze V5 test results with fuzzy matching"""
import json
import pandas as pd
import sys
sys.path.append('evaluation')
from fuzzy_comparison import compare_extractions_fuzzy

# Load V5 test results
with open('evaluation/v5_test_results.json') as f:
    v5_data = json.load(f)

# Load GT
df = pd.read_excel('8WR QEX Combined.xlsx', sheet_name='Sheet1')
df = df.rename(columns={
    'StudyID': 'study_id',
    'Outcome category': 'outcome_category',
    'Outcome name': 'outcome_name',
    'd': 'effect_size_d'
})

# Filter GT to test studies
test_studies = [e['study_id'] for e in v5_data['extractions']]
gt_filtered = df[df['study_id'].apply(lambda x: str(int(x)) if pd.notna(x) else "").isin(test_studies)]

print("="*60)
print("V5 TEST RESULTS - FUZZY MATCHING")
print("="*60)

# Try different thresholds
for threshold in [70, 60, 50]:
    print(f"\n--- Threshold = {threshold} ---")
    comparison = compare_extractions_fuzzy(
        v5_data['extractions'],
        gt_filtered,
        threshold=threshold,
        verbose=(threshold==70)  # Verbose output for threshold=70
    )
    
    print(f"\nOverall Recall: {comparison['overall_recall']*100:.1f}%")
    print(f"Overall Precision: {comparison['overall_precision']*100:.1f}%")
    print(f"Matched: {comparison['total_matched']}/{comparison['total_gt_outcomes']} GT outcomes")
    print(f"Extracted: {comparison['total_extracted']} total outcomes")
    
    print(f"\nBy Category:")
    for cat, stats in comparison['by_category'].items():
        print(f"  {cat}: R={stats['recall']*100:.1f}% P={stats['precision']*100:.1f}% ({stats['matched']}/{stats['gt_count']} matched)")

print("\n" + "="*60)
print("Recommended: Use threshold=70 as it balances precision/recall")
