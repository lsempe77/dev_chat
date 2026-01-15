#!/usr/bin/env python3
"""
Comprehensive Effect Size Accuracy Analysis

Compare extracted coefficients, SEs, sample sizes, CIs against ground truth.
"""

import json
import pandas as pd
import numpy as np
from pathlib import Path
from fuzzywuzzy import fuzz

def load_ground_truth():
    """Load GT from Excel with effect size columns."""
    df = pd.read_excel('8WR QEX Combined.xlsx', sheet_name='Sheet1')
    
    # Standardize column names
    rename_map = {
        'StudyID': 'study_id',
        'Outcome category': 'outcome_category',
        'Outcome name': 'outcome_name',
        'Coeff reg': 'coefficient',
        'SE reg\xa0': 'standard_error',
        'CI_LB reg\xa0': 'ci_lower',
        'CI_UP reg\xa0': 'ci_upper',
        'd': 'effect_size_d',
        'N treatment': 'n_treatment',
        'N control ': 'n_control',
        'N total\xa0': 'n_total',
        'P value exact\xa0': 'p_value'
    }
    df = df.rename(columns=rename_map)
    
    # Convert study_id to string
    df['study_id'] = df['study_id'].apply(lambda x: str(int(x)) if pd.notna(x) else "")
    
    return df

def load_extraction_results(version):
    """Load extraction results for a version."""
    version_files = {
        'V1': 'evaluation/v1_extraction_results.json',
        'V2': 'evaluation/v2_extraction_results.json',
        'V3': 'evaluation/v3_extraction_results.json',
        'V4': 'evaluation/v4_extraction_results.json',
        'V5': 'evaluation/v5_extraction_results.json',
    }
    
    filepath = version_files.get(version)
    if not filepath or not Path(filepath).exists():
        return None
    
    with open(filepath) as f:
        data = json.load(f)
    
    return data.get('extractions', [])

def match_outcomes_fuzzy(gt_outcomes, extracted_outcomes, threshold=70):
    """
    Match extracted outcomes to GT outcomes using fuzzy matching.
    Returns list of (gt_outcome, extracted_outcome, match_score) tuples.
    """
    matches = []
    used_gt = set()
    
    for ext in extracted_outcomes:
        ext_name = ext.get('outcome_name', '').lower().strip()
        ext_cat = ext.get('outcome_category', '').lower().strip()
        
        best_match = None
        best_score = 0
        best_gt_idx = None
        
        for idx, gt in enumerate(gt_outcomes):
            if idx in used_gt:
                continue
                
            gt_name = str(gt.get('outcome_name', '')).lower().strip()
            gt_cat = str(gt.get('outcome_category', '')).lower().strip()
            
            # Must be same category
            if ext_cat and gt_cat and ext_cat != gt_cat:
                continue
            
            score = fuzz.ratio(ext_name, gt_name)
            if score > best_score and score >= threshold:
                best_score = score
                best_match = gt
                best_gt_idx = idx
        
        if best_match is not None:
            matches.append({
                'gt': best_match,
                'extracted': ext,
                'match_score': best_score
            })
            used_gt.add(best_gt_idx)
    
    return matches

def compare_numeric(gt_val, ext_val, tolerance_pct=10):
    """Compare numeric values with tolerance."""
    if pd.isna(gt_val) or gt_val is None:
        return {'gt': None, 'ext': ext_val, 'error': None, 'accurate': None}
    if ext_val is None:
        return {'gt': gt_val, 'ext': None, 'error': None, 'accurate': False}
    
    try:
        gt = float(gt_val)
        ext = float(ext_val)
        
        if gt == 0:
            error = abs(ext)
            accurate = abs(ext) < 0.01  # Allow small error near zero
        else:
            error = abs((ext - gt) / gt) * 100  # Percentage error
            accurate = error <= tolerance_pct
        
        return {'gt': gt, 'ext': ext, 'error': error, 'accurate': accurate}
    except (ValueError, TypeError):
        return {'gt': gt_val, 'ext': ext_val, 'error': None, 'accurate': False}

def analyze_version(version, gt_df):
    """Analyze effect size accuracy for one version."""
    extractions = load_extraction_results(version)
    if not extractions:
        return None
    
    results = {
        'version': version,
        'coefficient': {'matches': 0, 'accurate': 0, 'errors': []},
        'standard_error': {'matches': 0, 'accurate': 0, 'errors': []},
        'effect_size_d': {'matches': 0, 'accurate': 0, 'errors': []},
        'n_total': {'matches': 0, 'accurate': 0, 'errors': []},
        'n_treatment': {'matches': 0, 'accurate': 0, 'errors': []},
        'n_control': {'matches': 0, 'accurate': 0, 'errors': []},
        'ci_coverage': {'has_ci': 0, 'total': 0},
        'total_matched_outcomes': 0,
    }
    
    all_matches = []
    
    for ext in extractions:
        study_id = str(ext['study_id'])
        gt_study = gt_df[gt_df['study_id'] == study_id]
        
        if gt_study.empty:
            continue
        
        # Get outcomes
        ext_outcomes = ext.get('outcomes', [])
        gt_outcomes = gt_study.to_dict('records')
        
        # Match outcomes
        matches = match_outcomes_fuzzy(gt_outcomes, ext_outcomes, threshold=70)
        all_matches.extend(matches)
    
    results['total_matched_outcomes'] = len(all_matches)
    
    # Analyze each matched pair
    for m in all_matches:
        gt = m['gt']
        ext = m['extracted']
        
        # Coefficient comparison
        coeff_cmp = compare_numeric(gt.get('coefficient'), ext.get('coefficient'), tolerance_pct=10)
        if coeff_cmp['gt'] is not None and coeff_cmp['ext'] is not None:
            results['coefficient']['matches'] += 1
            if coeff_cmp['accurate']:
                results['coefficient']['accurate'] += 1
            results['coefficient']['errors'].append(coeff_cmp['error'])
        
        # Standard error comparison
        se_cmp = compare_numeric(gt.get('standard_error'), ext.get('standard_error'), tolerance_pct=15)
        if se_cmp['gt'] is not None and se_cmp['ext'] is not None:
            results['standard_error']['matches'] += 1
            if se_cmp['accurate']:
                results['standard_error']['accurate'] += 1
            results['standard_error']['errors'].append(se_cmp['error'])
        
        # Effect size d comparison (computed_d in extractions)
        ext_d = ext.get('computed_d') or ext.get('effect_size_d')
        d_cmp = compare_numeric(gt.get('effect_size_d'), ext_d, tolerance_pct=20)
        if d_cmp['gt'] is not None and d_cmp['ext'] is not None:
            results['effect_size_d']['matches'] += 1
            if d_cmp['accurate']:
                results['effect_size_d']['accurate'] += 1
            results['effect_size_d']['errors'].append(d_cmp['error'])
        
        # Sample sizes
        for field in ['n_total', 'n_treatment', 'n_control']:
            n_cmp = compare_numeric(gt.get(field), ext.get(field), tolerance_pct=5)
            if n_cmp['gt'] is not None and n_cmp['ext'] is not None:
                results[field]['matches'] += 1
                if n_cmp['accurate']:
                    results[field]['accurate'] += 1
                results[field]['errors'].append(n_cmp['error'])
        
        # CI coverage
        results['ci_coverage']['total'] += 1
        if ext.get('ci_lower') is not None and ext.get('ci_upper') is not None:
            results['ci_coverage']['has_ci'] += 1
    
    return results

def print_report(all_results):
    """Print comprehensive report."""
    print("="*80)
    print("EFFECT SIZE & PARAMETER ACCURACY REPORT")
    print("="*80)
    print()
    
    # Summary table
    print("="*80)
    print("SUMMARY: ACCURACY BY PARAMETER (within 10% tolerance)")
    print("="*80)
    print()
    print(f"{'Version':<8} {'Matched':<10} {'Coeff':<12} {'SE':<12} {'d':<12} {'N_total':<12}")
    print("-"*66)
    
    for r in all_results:
        if r is None:
            continue
        
        coeff_acc = r['coefficient']['accurate'] / r['coefficient']['matches'] * 100 if r['coefficient']['matches'] > 0 else 0
        se_acc = r['standard_error']['accurate'] / r['standard_error']['matches'] * 100 if r['standard_error']['matches'] > 0 else 0
        d_acc = r['effect_size_d']['accurate'] / r['effect_size_d']['matches'] * 100 if r['effect_size_d']['matches'] > 0 else 0
        n_acc = r['n_total']['accurate'] / r['n_total']['matches'] * 100 if r['n_total']['matches'] > 0 else 0
        
        print(f"{r['version']:<8} {r['total_matched_outcomes']:<10} "
              f"{coeff_acc:5.1f}% ({r['coefficient']['matches']:3d})  "
              f"{se_acc:5.1f}% ({r['standard_error']['matches']:3d})  "
              f"{d_acc:5.1f}% ({r['effect_size_d']['matches']:3d})  "
              f"{n_acc:5.1f}% ({r['n_total']['matches']:3d})")
    
    print()
    print("="*80)
    print("DETAILED BREAKDOWN BY VERSION")
    print("="*80)
    
    for r in all_results:
        if r is None:
            continue
        
        print(f"\n--- {r['version']} ---")
        print(f"  Total matched outcomes: {r['total_matched_outcomes']}")
        print()
        
        for field, label in [
            ('coefficient', 'Coefficient'),
            ('standard_error', 'Standard Error'),
            ('effect_size_d', "Cohen's d"),
            ('n_total', 'N Total'),
            ('n_treatment', 'N Treatment'),
            ('n_control', 'N Control'),
        ]:
            stats = r[field]
            if stats['matches'] > 0:
                acc = stats['accurate'] / stats['matches'] * 100
                errors = [e for e in stats['errors'] if e is not None]
                mean_err = np.mean(errors) if errors else 0
                median_err = np.median(errors) if errors else 0
                print(f"  {label:15s}: {acc:5.1f}% accurate ({stats['accurate']}/{stats['matches']}), "
                      f"mean error: {mean_err:.1f}%, median: {median_err:.1f}%")
            else:
                print(f"  {label:15s}: No comparisons available")
        
        # CI coverage
        ci = r['ci_coverage']
        if ci['total'] > 0:
            ci_pct = ci['has_ci'] / ci['total'] * 100
            print(f"  CI Coverage   : {ci_pct:.1f}% have CI ({ci['has_ci']}/{ci['total']})")
    
    print()
    print("="*80)
    print("PARAMETER EXTRACTION COMPLETENESS")
    print("="*80)
    print()
    print(f"{'Version':<8} {'Has Coeff':<12} {'Has SE':<12} {'Has d':<12} {'Has N':<12} {'Has CI':<12}")
    print("-"*68)
    
    for r in all_results:
        if r is None:
            continue
        
        total = r['total_matched_outcomes']
        if total == 0:
            continue
        
        coeff_pct = r['coefficient']['matches'] / total * 100
        se_pct = r['standard_error']['matches'] / total * 100
        d_pct = r['effect_size_d']['matches'] / total * 100
        n_pct = r['n_total']['matches'] / total * 100
        ci_pct = r['ci_coverage']['has_ci'] / total * 100 if total > 0 else 0
        
        print(f"{r['version']:<8} {coeff_pct:5.1f}% ({r['coefficient']['matches']:3d})  "
              f"{se_pct:5.1f}% ({r['standard_error']['matches']:3d})  "
              f"{d_pct:5.1f}% ({r['effect_size_d']['matches']:3d})  "
              f"{n_pct:5.1f}% ({r['n_total']['matches']:3d})  "
              f"{ci_pct:5.1f}% ({r['ci_coverage']['has_ci']:3d})")
    
    return all_results

def main():
    print("Loading ground truth...")
    gt_df = load_ground_truth()
    print(f"✓ Loaded {len(gt_df)} GT outcomes")
    
    # Filter to study IDs in our evaluation set
    with open('evaluation/v1_extraction_results.json') as f:
        v1_data = json.load(f)
    study_ids = [str(e['study_id']) for e in v1_data['extractions']]
    gt_df = gt_df[gt_df['study_id'].isin(study_ids)]
    print(f"✓ Filtered to {len(gt_df)} GT outcomes from {len(study_ids)} studies")
    print()
    
    # Analyze each version
    all_results = []
    for version in ['V1', 'V2', 'V3', 'V4', 'V5']:
        print(f"Analyzing {version}...")
        result = analyze_version(version, gt_df)
        all_results.append(result)
    
    print()
    
    # Generate report
    print_report(all_results)
    
    # Save detailed results
    output_data = []
    for r in all_results:
        if r is None:
            continue
        
        # Convert numpy types
        cleaned = {
            'version': r['version'],
            'total_matched': r['total_matched_outcomes'],
            'coefficient': {
                'matches': r['coefficient']['matches'],
                'accurate': r['coefficient']['accurate'],
                'accuracy_pct': r['coefficient']['accurate'] / r['coefficient']['matches'] * 100 if r['coefficient']['matches'] > 0 else 0,
            },
            'standard_error': {
                'matches': r['standard_error']['matches'],
                'accurate': r['standard_error']['accurate'],
                'accuracy_pct': r['standard_error']['accurate'] / r['standard_error']['matches'] * 100 if r['standard_error']['matches'] > 0 else 0,
            },
            'effect_size_d': {
                'matches': r['effect_size_d']['matches'],
                'accurate': r['effect_size_d']['accurate'],
                'accuracy_pct': r['effect_size_d']['accurate'] / r['effect_size_d']['matches'] * 100 if r['effect_size_d']['matches'] > 0 else 0,
            },
            'n_total': {
                'matches': r['n_total']['matches'],
                'accurate': r['n_total']['accurate'],
                'accuracy_pct': r['n_total']['accurate'] / r['n_total']['matches'] * 100 if r['n_total']['matches'] > 0 else 0,
            },
            'ci_coverage': r['ci_coverage'],
        }
        output_data.append(cleaned)
    
    with open('evaluation/effect_size_accuracy.json', 'w') as f:
        json.dump(output_data, f, indent=2)
    
    print()
    print("✓ Saved detailed results to evaluation/effect_size_accuracy.json")

if __name__ == '__main__':
    main()
