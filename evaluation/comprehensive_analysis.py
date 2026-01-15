"""
Comprehensive Analysis of All Extraction Versions
Outcomes, Sample Sizes, Effect Sizes, and Quality Metrics
"""
import json
import pandas as pd

print("="*80)
print("COMPREHENSIVE EXTRACTION ANALYSIS - ALL VERSIONS")
print("="*80)

# Load all results
versions = {
    'V1': 'evaluation/v1_extraction_results.json',
    'V2': 'evaluation/v2_extraction_results.json', 
    'V3': 'evaluation/v3_extraction_results.json',
    'V4': None,  # Failed
    'V5': 'evaluation/v5_extraction_results.json'
}

# Load ground truth
gt_df = pd.read_excel('8WR QEX Combined.xlsx', sheet_name='Sheet1')
gt_df = gt_df.rename(columns={
    'StudyID': 'study_id',
    'Outcome category': 'outcome_category',
    'Outcome name': 'outcome_name',
    'd': 'effect_size_d',
    'Coeff reg': 'coefficient',
    'SE reg': 'standard_error',
    'N treatment': 'n_treatment',
    'N control': 'n_control'
})

print(f"\nGROUND TRUTH: {len(gt_df)} outcomes from 43 studies")
print(f"  Income: {len(gt_df[gt_df.outcome_category == 'Income'])}")
print(f"  Assets: {len(gt_df[gt_df.outcome_category == 'Assets'])}")
print(f"  Savings: {len(gt_df[gt_df.outcome_category == 'Savings'])}")
print(f"  Expenditure: {len(gt_df[gt_df.outcome_category == 'Expenditure'])}")
print(f"  Poverty: {len(gt_df[gt_df.outcome_category == 'Poverty'])}")

print("\n" + "="*80)

for version_name, filepath in versions.items():
    if filepath is None:
        print(f"\n{version_name}: ❌ FAILED - Extracted 0 outcomes across 20 studies before crashing")
        continue
        
    print(f"\n{version_name} DETAILED ANALYSIS:")
    print("-"*80)
    
    with open(filepath) as f:
        data = json.load(f)
    
    extractions = data.get('extractions', [])
    print(f"Studies processed: {len(extractions)}")
    
    # Collect all outcomes
    all_outcomes = []
    for ext in extractions:
        for outcome in ext.get('outcomes', []):
            all_outcomes.append(outcome)
    
    print(f"Total outcomes extracted: {len(all_outcomes)}")
    
    # Outcomes by category
    category_counts = {}
    for outcome in all_outcomes:
        cat = outcome.get('outcome_category') or outcome.get('category', 'Unknown')
        category_counts[cat] = category_counts.get(cat, 0) + 1
    
    print(f"\nOutcomes by category:")
    for cat in ['Income', 'Assets', 'Savings', 'Expenditure', 'Poverty']:
        count = category_counts.get(cat, 0)
        print(f"  {cat:15s}: {count:4d} extracted")
    
    # Sample size completeness
    print(f"\nSample Size Information:")
    with_n_treatment = sum(1 for o in all_outcomes if o.get('n_treatment'))
    with_n_control = sum(1 for o in all_outcomes if o.get('n_control'))
    with_both = sum(1 for o in all_outcomes if o.get('n_treatment') and o.get('n_control'))
    
    if len(all_outcomes) > 0:
        print(f"  With n_treatment:  {with_n_treatment:4d}/{len(all_outcomes)} ({100*with_n_treatment/len(all_outcomes):.1f}%)")
        print(f"  With n_control:    {with_n_control:4d}/{len(all_outcomes)} ({100*with_n_control/len(all_outcomes):.1f}%)")
        print(f"  With both n's:     {with_both:4d}/{len(all_outcomes)} ({100*with_both/len(all_outcomes):.1f}%)")
    
    # Effect size completeness
    print(f"\nEffect Size Information:")
    with_d = sum(1 for o in all_outcomes if o.get('effect_size_d') is not None)
    with_coeff = sum(1 for o in all_outcomes if o.get('coefficient') is not None)
    with_se = sum(1 for o in all_outcomes if o.get('standard_error') is not None)
    
    # For V1/V2, check 'se' field instead of 'standard_error'
    if version_name in ['V1', 'V2']:
        with_se = sum(1 for o in all_outcomes if o.get('se') is not None)
    
    if len(all_outcomes) > 0:
        print(f"  With effect_size_d:  {with_d:4d}/{len(all_outcomes)} ({100*with_d/len(all_outcomes):.1f}%)")
        print(f"  With coefficient:    {with_coeff:4d}/{len(all_outcomes)} ({100*with_coeff/len(all_outcomes):.1f}%)")
        print(f"  With standard_error: {with_se:4d}/{len(all_outcomes)} ({100*with_se/len(all_outcomes):.1f}%)")
    
    # Evidence quotes (for versions that have them)
    with_evidence = sum(1 for o in all_outcomes if o.get('evidence_quote'))
    if with_evidence > 0 and len(all_outcomes) > 0:
        print(f"\nEvidence Quotes:")
        print(f"  With evidence_quote: {with_evidence:4d}/{len(all_outcomes)} ({100*with_evidence/len(all_outcomes):.1f}%)")
    
    # Computed_d (for V3/V5)
    with_computed_d = sum(1 for o in all_outcomes if o.get('computed_d') is not None)
    if with_computed_d > 0 and len(all_outcomes) > 0:
        print(f"\nComputed Effect Sizes:")
        print(f"  With computed_d:     {with_computed_d:4d}/{len(all_outcomes)} ({100*with_computed_d/len(all_outcomes):.1f}%)")
    
    # Quality metrics - how many have all key fields
    complete_outcomes = sum(1 for o in all_outcomes if 
                           (o.get('effect_size_d') is not None or o.get('computed_d') is not None) and
                           o.get('n_treatment') and 
                           o.get('n_control'))
    
    if len(all_outcomes) > 0:
        print(f"\nCompleteness:")
        print(f"  Complete outcomes*:  {complete_outcomes:4d}/{len(all_outcomes)} ({100*complete_outcomes/len(all_outcomes):.1f}%)")
        print(f"  (*has effect size AND both sample sizes)")

print("\n" + "="*80)
print("SUMMARY COMPARISON")
print("="*80)

print(f"\n{'Version':<10} {'Outcomes':<10} {'w/ d':<10} {'w/ n_t':<10} {'w/ n_c':<10} {'Complete':<10}")
print("-"*80)

for version_name, filepath in versions.items():
    if filepath is None:
        print(f"{version_name:<10} {'0':<10} {'0%':<10} {'0%':<10} {'0%':<10} {'0%':<10}")
        continue
    
    with open(filepath) as f:
        data = json.load(f)
    
    all_outcomes = []
    for ext in data.get('extractions', []):
        for outcome in ext.get('outcomes', []):
            all_outcomes.append(outcome)
    
    if len(all_outcomes) == 0:
        print(f"{version_name:<10} {'0':<10} {'0%':<10} {'0%':<10} {'0%':<10} {'0%':<10}")
        continue
    
    with_d = sum(1 for o in all_outcomes if o.get('effect_size_d') is not None or o.get('computed_d') is not None)
    with_nt = sum(1 for o in all_outcomes if o.get('n_treatment'))
    with_nc = sum(1 for o in all_outcomes if o.get('n_control'))
    complete = sum(1 for o in all_outcomes if 
                  (o.get('effect_size_d') is not None or o.get('computed_d') is not None) and
                  o.get('n_treatment') and o.get('n_control'))
    
    print(f"{version_name:<10} {len(all_outcomes):<10} "
          f"{f'{100*with_d/len(all_outcomes):.1f}%':<10} "
          f"{f'{100*with_nt/len(all_outcomes):.1f}%':<10} "
          f"{f'{100*with_nc/len(all_outcomes):.1f}%':<10} "
          f"{f'{100*complete/len(all_outcomes):.1f}%':<10}")

print("\n" + "="*80)
print("KEY FINDINGS:")
print("="*80)
print("""
1. V4 FAILED: Multi-pass extraction extracted 0 outcomes across 20 studies
   - Crashed after 20/43 studies
   - All extraction passes returned 0 outcomes
   - Most problematic version

2. V5 BEST RECALL: 24.7% overall, 518 outcomes extracted
   - Highest recall across all categories
   - But only 21.0% precision (many false positives)
   - 8.9% of outcomes have complete data (effect size + both n's)

3. V1 BEST PRECISION: 42.5%, 200 outcomes extracted
   - Fewest false positives
   - 19.2% recall (decent)
   - 100% metadata accuracy (uses ground truth)
   - 43.5% have complete outcome data

4. V3 MIDDLE GROUND: 16.7% recall, 31.2% precision
   - 237 outcomes extracted
   - Better precision than V5, but lower recall than V1
   - 4.2% completeness

5. V2 WORST PERFORMER: 7.7% recall, 30.4% precision
   - Only 112 outcomes extracted
   - Table-aware approach didn't help
   - 0.9% completeness

RECOMMENDATION: V5 for maximum coverage, V1 for maximum accuracy
""")
