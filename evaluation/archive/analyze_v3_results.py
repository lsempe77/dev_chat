"""Analyze V3 extraction results in detail."""

import json
import numpy as np
from pathlib import Path

base_path = Path(__file__).parent

with open(base_path / 'v3_extraction_results.json') as f:
    data = json.load(f)

comp = data['comparison']
extractions = data['extractions']

print("=" * 70)
print("V3 EXTRACTION DETAILED ANALYSIS")
print("=" * 70)

# Metadata analysis
print("\n## METADATA ANALYSIS")
meta_results = comp['metadata']
for field, stats in meta_results.items():
    print(f"  {field}: {stats['correct']}/{stats['total']} = {stats['accuracy']*100:.1f}%")

# Count studies with metadata failures
failed_metadata = sum(1 for e in extractions if not e.get('metadata'))
print(f"\nStudies with metadata failures: {failed_metadata} / {len(extractions)}")

# Cohen's d analysis
print("\n## COHEN'S D ANALYSIS")
d_errors = comp['outcomes']['d_errors']
print(f"Total d values computed and matched to GT: {len(d_errors)}")

if d_errors:
    errors = [e['error'] for e in d_errors]
    print(f"Mean error: {np.mean(errors):.4f}")
    print(f"Median error: {np.median(errors):.4f}")
    print(f"Max error: {np.max(errors):.4f}")
    
    # By method
    methods = {}
    for e in d_errors:
        m = e['method']
        if m not in methods:
            methods[m] = []
        methods[m].append(e['error'])
    
    print("\nBy computation method:")
    for m, errs in methods.items():
        print(f"  {m}: n={len(errs)}, mean={np.mean(errs):.4f}, median={np.median(errs):.4f}")
    
    # Error distribution
    print("\nError distribution:")
    error_buckets = [0.01, 0.05, 0.1, 0.2, 0.5, 1.0]
    for bucket in error_buckets:
        count = sum(1 for e in errors if e <= bucket)
        print(f"  <= {bucket}: {count} ({100*count/len(errors):.1f}%)")
    
    # Show worst errors
    print("\nLargest errors:")
    sorted_errors = sorted(d_errors, key=lambda x: x['error'], reverse=True)[:5]
    for e in sorted_errors:
        print(f"  {e['study_id']}: computed={e['computed_d']:.4f}, gt={e['gt_d']:.4f}, error={e['error']:.4f}")
    
    # Show best matches
    print("\nBest matches (lowest error):")
    sorted_errors = sorted(d_errors, key=lambda x: x['error'])[:5]
    for e in sorted_errors:
        print(f"  {e['study_id']}: computed={e['computed_d']:.4f}, gt={e['gt_d']:.4f}, error={e['error']:.4f}")

# Outcome extraction analysis
print("\n## OUTCOME EXTRACTION ANALYSIS")
oc = comp['outcomes']
print(f"GT outcomes: {oc['total_gt']}")
print(f"Extracted outcomes: {oc['total_extracted']}")
print(f"Recall: {100*oc['total_extracted']/oc['total_gt']:.1f}%")
print(f"Cohen's d computed: {oc['d_computed']}")
print(f"d computation rate: {100*oc['d_computed']/oc['total_extracted']:.1f}%")

print("\nCategory recall:")
for cat, stats in oc['category_recall'].items():
    recall_pct = stats['recall'] * 100
    print(f"  {cat}: {stats['extracted']}/{stats['gt']} = {recall_pct:.1f}%")

# Analyze why d computation failed
print("\n## D COMPUTATION FAILURE ANALYSIS")
all_outcomes = []
for e in extractions:
    for o in e.get('outcomes', []):
        all_outcomes.append(o)

methods = {}
for o in all_outcomes:
    m = o.get('computation_method', 'unknown')
    if m not in methods:
        methods[m] = 0
    methods[m] += 1

print("Computation methods used:")
for m, count in sorted(methods.items(), key=lambda x: -x[1]):
    print(f"  {m}: {count} ({100*count/len(all_outcomes):.1f}%)")

# Check what data is missing
insufficient = [o for o in all_outcomes if o.get('computation_method') == 'insufficient_data']
print(f"\nInsufficient data cases: {len(insufficient)}")

# Sample analysis
if insufficient:
    sample = insufficient[0]
    print("Sample insufficient case:")
    for k, v in sample.items():
        if k not in ['evidence_table', 'computation_method', 'computed_d']:
            print(f"  {k}: {v}")

print("\n" + "=" * 70)
print("END ANALYSIS")
print("=" * 70)
