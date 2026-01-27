#!/usr/bin/env python3
"""Analyze specific mismatches between extracted and ground truth outcomes."""
import json
from fuzzywuzzy import fuzz


def main():
    """Run mismatch analysis."""
    with open('evaluation/extraction_v6_results.json') as f:
        results = json.load(f)

    with open('evaluation/matched_studies_r2.json') as f:
        studies = json.load(f)

    gt_by_id = {s['study_id']: s['ground_truth'] for s in studies}

    # Show detailed mismatches for first 5 studies
    for result in results[:5]:
        if not result.get('success'):
            continue
        study_id = result['study_id']
        gt = gt_by_id.get(study_id, {})
        gt_outcomes = gt.get('outcomes', [])
        extracted = result.get('outcomes', [])
        
        print('='*70)
        print(f"Study: {gt.get('author', 'Unknown')} ({study_id})")
        print('='*70)
        
        print(f"\nGROUND TRUTH OUTCOMES ({len(gt_outcomes)}):")
        for i, o in enumerate(gt_outcomes[:8]):
            name = o.get('name', 'N/A')
            print(f"  {i+1}. {name[:60]}")
        if len(gt_outcomes) > 8:
            print(f"  ... and {len(gt_outcomes)-8} more")
        
        print(f"\nEXTRACTED OUTCOMES ({len(extracted)}):")
        for i, o in enumerate(extracted[:8]):
            name = o.get('outcome_name', 'N/A')
            print(f"  {i+1}. {name[:60] if name else 'N/A'}")
        if len(extracted) > 8:
            print(f"  ... and {len(extracted)-8} more")
        
        # Show match scores
        print(f"\nMATCH ANALYSIS:")
        for ext in extracted[:5]:
            ext_name = (ext.get('outcome_name') or '').lower()
            best_match = None
            best_score = 0
            for gt_o in gt_outcomes:
                gt_name = gt_o.get('name', '').lower()
                score = fuzz.token_set_ratio(ext_name, gt_name)
                if score > best_score:
                    best_score = score
                    best_match = gt_o.get('name', '')
            status = 'MATCH' if best_score >= 70 else 'NO MATCH'
            ext_short = ext_name[:35] if ext_name else 'N/A'
            match_short = best_match[:35] if best_match else 'N/A'
            print(f"  '{ext_short}' -> '{match_short}' (score: {best_score}) [{status}]")
        print()


if __name__ == "__main__":
    main()
