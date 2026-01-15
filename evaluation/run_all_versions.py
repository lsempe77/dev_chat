"""
Run all extraction versions (V1-V5) on all studies and compare with fuzzy matching

This will:
1. Run each version on all 43 studies
2. Save results for each version
3. Compare all versions using fuzzy matching
4. Generate comparison report
"""

import json
import pandas as pd
from datetime import datetime
from pathlib import Path
import sys

# Add evaluation to path for imports
sys.path.append('evaluation')
from fuzzy_comparison import compare_extractions_fuzzy

def load_ground_truth():
    """Load and prepare ground truth data."""
    df = pd.read_excel('8WR QEX Combined.xlsx', sheet_name='Sheet1')
    df = df.rename(columns={
        'StudyID': 'study_id',
        'Outcome category': 'outcome_category',
        'Outcome name': 'outcome_name',
        'd': 'effect_size_d',
        'Coeff reg': 'coefficient',
        'SE reg\xa0': 'standard_error',
        'N treatment': 'n_treatment',
        'N control ': 'n_control',
        'N total\xa0': 'n_total'
    })
    return df

def filter_gt_for_studies(gt_df, study_ids):
    """Filter GT to only include specified studies."""
    return gt_df[gt_df['study_id'].apply(
        lambda x: str(int(x)) if pd.notna(x) else ""
    ).isin(study_ids)]

def compare_metadata(extractions, studies, metadata_fields):
    """Compare metadata accuracy."""
    gt_lookup = {str(s['study_id']): s.get('ground_truth', {}) for s in studies}
    
    results = {f: {"correct": 0, "total": 0} for f in metadata_fields}
    
    for ext in extractions:
        study_id = str(ext["study_id"])
        gt = gt_lookup.get(study_id, {})
        
        for field in metadata_fields:
            if field not in gt:
                continue
            
            results[field]["total"] += 1
            
            extracted = ext.get("metadata", {}).get(field, {})
            if isinstance(extracted, dict):
                extracted_val = extracted.get("value")
            else:
                extracted_val = extracted
            
            gt_val = gt[field]
            
            # Normalize for comparison
            if isinstance(gt_val, str):
                match = str(extracted_val).lower().strip() == gt_val.lower().strip()
            else:
                match = extracted_val == gt_val
            
            if match:
                results[field]["correct"] += 1
    
    # Calculate accuracies
    for field in metadata_fields:
        total = results[field]["total"]
        correct = results[field]["correct"]
        results[field]["accuracy"] = correct / total if total > 0 else 0
    
    return results

def analyze_version_results(version_name, results_file, gt_df, studies):
    """Analyze results for a single version."""
    print(f"\n{'='*60}")
    print(f"Analyzing {version_name}")
    print('='*60)
    
    if not Path(results_file).exists():
        print(f"❌ Results file not found: {results_file}")
        return None
    
    # Load results
    with open(results_file) as f:
        data = json.load(f)
    
    extractions = data.get('extractions', [])
    if not extractions:
        print(f"❌ No extractions found")
        return None
    
    print(f"✓ Loaded {len(extractions)} extractions")
    
    # Filter GT to extracted studies
    study_ids = [str(e['study_id']) for e in extractions]
    gt_filtered = filter_gt_for_studies(gt_df, study_ids)
    
    print(f"✓ GT filtered: {len(gt_filtered)} outcomes from {len(study_ids)} studies")
    
    # Fuzzy outcome comparison
    print("\n--- Outcome Extraction (Fuzzy Matching, threshold=70) ---")
    outcome_comp = compare_extractions_fuzzy(extractions, gt_filtered, threshold=70)
    
    print(f"\nOverall:")
    print(f"  Recall:    {outcome_comp['overall_recall']*100:.1f}%")
    print(f"  Precision: {outcome_comp['overall_precision']*100:.1f}%")
    print(f"  Matched:   {outcome_comp['total_matched']}/{outcome_comp['total_gt_outcomes']} GT outcomes")
    print(f"  Extracted: {outcome_comp['total_extracted']} outcomes")
    
    print(f"\nBy Category:")
    for cat in ['Income', 'Assets', 'Savings', 'Expenditure', 'Poverty']:
        stats = outcome_comp['by_category'][cat]
        print(f"  {cat:12s} R={stats['recall']*100:5.1f}% P={stats['precision']*100:5.1f}% "
              f"({stats['matched']:3d}/{stats['gt_count']:3d} matched, {stats['extracted_count']:3d} extracted)")
    
    # Metadata comparison
    print("\n--- Metadata Accuracy ---")
    metadata_fields = [
        "study_design", "country", "consumption_support", "health_comp",
        "asset_transfer", "skills_comp", "savings_comp", "coaching_comp",
        "social_comp", "targeting_women"
    ]
    metadata_comp = compare_metadata(extractions, studies, metadata_fields)
    
    for field in metadata_fields:
        stats = metadata_comp[field]
        if stats['total'] > 0:
            print(f"  {field:20s} {stats['accuracy']*100:5.1f}% ({stats['correct']}/{stats['total']})")
    
    return {
        'version': version_name,
        'n_studies': len(extractions),
        'outcome_comparison': outcome_comp,
        'metadata_comparison': metadata_comp
    }

def generate_comparison_report(all_results):
    """Generate a comparison report across all versions."""
    print("\n" + "="*80)
    print("CROSS-VERSION COMPARISON")
    print("="*80)
    
    print("\n--- Outcome Recall (Fuzzy Matching) ---")
    print(f"{'Version':<15} {'Overall':<10} {'Income':<10} {'Assets':<10} {'Savings':<10} {'Expenditure':<10} {'Poverty':<10}")
    print("-"*80)
    
    for result in all_results:
        if not result:
            continue
        oc = result['outcome_comparison']
        overall = oc['overall_recall'] * 100
        cats = oc['by_category']
        print(f"{result['version']:<15} {overall:>6.1f}%    "
              f"{cats['Income']['recall']*100:>6.1f}%    "
              f"{cats['Assets']['recall']*100:>6.1f}%    "
              f"{cats['Savings']['recall']*100:>6.1f}%    "
              f"{cats['Expenditure']['recall']*100:>6.1f}%    "
              f"{cats['Poverty']['recall']*100:>6.1f}%")
    
    print("\n--- Outcome Precision ---")
    print(f"{'Version':<15} {'Overall':<10} {'Income':<10} {'Assets':<10} {'Savings':<10} {'Expenditure':<10} {'Poverty':<10}")
    print("-"*80)
    
    for result in all_results:
        if not result:
            continue
        oc = result['outcome_comparison']
        overall = oc['overall_precision'] * 100
        cats = oc['by_category']
        print(f"{result['version']:<15} {overall:>6.1f}%    "
              f"{cats['Income']['precision']*100:>6.1f}%    "
              f"{cats['Assets']['precision']*100:>6.1f}%    "
              f"{cats['Savings']['precision']*100:>6.1f}%    "
              f"{cats['Expenditure']['precision']*100:>6.1f}%    "
              f"{cats['Poverty']['precision']*100:>6.1f}%")
    
    print("\n--- Metadata Accuracy (Average) ---")
    for result in all_results:
        if not result:
            continue
        mc = result['metadata_comparison']
        accuracies = [stats['accuracy'] for stats in mc.values() if stats['total'] > 0]
        avg_acc = sum(accuracies) / len(accuracies) if accuracies else 0
        print(f"{result['version']:<15} {avg_acc*100:>6.1f}%")
    
    # Save detailed comparison
    output = {
        'timestamp': datetime.now().isoformat(),
        'versions': [r for r in all_results if r],
        'summary': {
            'outcome_recall': {r['version']: r['outcome_comparison']['overall_recall'] for r in all_results if r},
            'outcome_precision': {r['version']: r['outcome_comparison']['overall_precision'] for r in all_results if r},
        }
    }
    
    with open('evaluation/version_comparison_fuzzy.json', 'w') as f:
        json.dump(output, f, indent=2, default=str)
    
    print(f"\n✓ Detailed comparison saved to evaluation/version_comparison_fuzzy.json")

def main():
    print("="*80)
    print("RUNNING ALL EXTRACTION VERSIONS WITH FUZZY COMPARISON")
    print("="*80)
    
    # Load ground truth
    print("\nLoading ground truth...")
    gt_df = load_ground_truth()
    print(f"✓ Loaded {len(gt_df)} GT outcomes")
    
    # Load matched studies
    with open('evaluation/matched_studies_r2.json') as f:
        studies = json.load(f)
    print(f"✓ Loaded {len(studies)} studies")
    
    # Define versions to analyze (will be updated as results become available)
    versions = [
        ('V1', 'evaluation/v1_extraction_results.json'),
        ('V2', 'evaluation/v2_extraction_results.json'),
        ('V3', 'evaluation/v3_extraction_results.json'),
        ('V4', 'evaluation/v4_extraction_results.json'),
        ('V5', 'evaluation/v5_extraction_results.json'),
    ]
    
    all_results = []
    
    # Analyze existing results
    for version_name, results_file in versions:
        result = analyze_version_results(version_name, results_file, gt_df, studies)
        all_results.append(result)
    
    # Generate comparison report
    if all_results:
        generate_comparison_report(all_results)
    
    print("\n" + "="*80)
    print("NEXT STEPS:")
    print("="*80)
    print("1. Run V3 on all studies: python evaluation/extraction_v3.py")
    print("2. Run V4 on all studies: python evaluation/extraction_v4_multipass.py")
    print("3. Run V5 on all studies: Set test_mode=False in extraction_v5_fullpaper.py")
    print("4. Re-run this script to compare all versions")
    print("="*80)

if __name__ == "__main__":
    main()
