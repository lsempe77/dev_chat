#!/usr/bin/env python3
"""Compare extraction results against ground truth."""
import json
import sys
from fuzzywuzzy import fuzz
import pandas as pd

# Get version from command line or default to v6
version = sys.argv[1] if len(sys.argv) > 1 else "v6"
results_file = f'evaluation/extraction_{version}_results.json'

# Load results
with open(results_file) as f:
    results = json.load(f)

# Load ground truth
with open('evaluation/matched_studies_r2.json') as f:
    studies = json.load(f)

gt_by_id = {s['study_id']: s['ground_truth'] for s in studies}

print("=" * 70)
print("V6 EXTRACTION RESULTS vs GROUND TRUTH")
print("=" * 70)

# Overall stats
total_extracted = sum(len(r.get('outcomes', [])) for r in v6_results if r.get('success'))
total_gt = sum(len(gt_by_id.get(r['study_id'], {}).get('outcomes', [])) for r in v6_results)
total_tables = sum(r.get('num_tables_found', 0) for r in v6_results if r.get('success'))

print(f"\nTotal studies: {len(v6_results)}")
print(f"Successful: {sum(1 for r in v6_results if r.get('success'))}")
print(f"Total outcomes extracted: {total_extracted}")
print(f"Total ground truth outcomes: {total_gt}")
print(f"Total tables found: {total_tables}")

# Outcome matching
def match_outcomes(extracted, ground_truth, threshold=70):
    """Match extracted outcomes to ground truth using fuzzy matching."""
    matches = 0
    matched_gt = set()
    
    for ext in extracted:
        ext_name = ext.get('outcome_name', '').lower()
        for i, gt in enumerate(ground_truth):
            if i in matched_gt:
                continue
            gt_name = gt.get('name', '').lower()
            score = fuzz.token_set_ratio(ext_name, gt_name)
            if score >= threshold:
                matches += 1
                matched_gt.add(i)
                break
    
    return matches, len(matched_gt)

# Calculate recall/precision per study
all_matches = 0
all_extracted = 0
all_gt = 0

print("\n" + "-" * 70)
print("PER-STUDY ANALYSIS:")
print("-" * 70)

for result in v6_results:
    if not result.get('success'):
        continue
    
    study_id = result['study_id']
    gt = gt_by_id.get(study_id, {})
    gt_outcomes = gt.get('outcomes', [])
    extracted = result.get('outcomes', [])
    
    matches, _ = match_outcomes(extracted, gt_outcomes)
    
    recall = matches / len(gt_outcomes) * 100 if gt_outcomes else 0
    precision = matches / len(extracted) * 100 if extracted else 0
    
    all_matches += matches
    all_extracted += len(extracted)
    all_gt += len(gt_outcomes)
    
    tables = result.get('num_tables_found', 0)
    author = gt.get('author', 'Unknown')
    
    # Count CIs
    cis = sum(1 for o in extracted 
              if o.get('confidence_interval_lower') is not None 
              and o.get('confidence_interval_upper') is not None)
    
    print(f"{author:25} | Tables: {tables:3} | Ext: {len(extracted):3} | GT: {len(gt_outcomes):3} | Match: {matches:3} | Recall: {recall:5.1f}% | CIs: {cis}")

# Overall metrics
print("\n" + "=" * 70)
print("OVERALL METRICS:")
print("=" * 70)
overall_recall = all_matches / all_gt * 100 if all_gt else 0
overall_precision = all_matches / all_extracted * 100 if all_extracted else 0
f1 = 2 * (overall_precision * overall_recall) / (overall_precision + overall_recall) if (overall_precision + overall_recall) > 0 else 0

print(f"Total extracted outcomes: {all_extracted}")
print(f"Total ground truth outcomes: {all_gt}")
print(f"Total matches: {all_matches}")
print(f"Overall Recall: {overall_recall:.1f}%")
print(f"Overall Precision: {overall_precision:.1f}%")
print(f"F1 Score: {f1:.1f}%")

# CI extraction
total_cis = sum(1 for r in v6_results if r.get('success')
                for o in r.get('outcomes', [])
                if o.get('confidence_interval_lower') is not None 
                and o.get('confidence_interval_upper') is not None)
print(f"Total CIs extracted: {total_cis}")

# Compare with previous versions
print("\n" + "=" * 70)
print("COMPARISON WITH PREVIOUS VERSIONS:")
print("=" * 70)
print(f"{'Version':<10} {'Outcomes':<12} {'Recall':<10} {'Precision':<12} {'Tables':<10}")
print("-" * 54)
print(f"{'V1':<10} {'190':<12} {'19.2%':<10} {'42.5%':<12} {'0':<10}")
print(f"{'V2':<10} {'179':<12} {'16.1%':<10} {'37.4%':<12} {'0':<10}")
print(f"{'V3':<10} {'513':<12} {'21.3%':<10} {'17.3%':<12} {'0':<10}")
print(f"{'V4':<10} {'535':<12} {'21.5%':<10} {'17.8%':<12} {'0':<10}")
print(f"{'V5':<10} {'518':<12} {'24.7%':<10} {'21.0%':<12} {'0':<10}")
print(f"{'V6':<10} {all_extracted:<12} {overall_recall:.1f}%{'':<5} {overall_precision:.1f}%{'':<7} {total_tables:<10}")
