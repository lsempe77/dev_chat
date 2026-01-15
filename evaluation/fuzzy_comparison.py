"""
Improved outcome comparison using fuzzy string matching

Problem: LLM extracts outcomes with different wording than human coders
- GT: "Livestock revenue (yearly, USD)"
- Extracted: "Monthly livestock revenues (USD PPP)"

Solution: Use fuzzy string matching + keyword overlap
"""

import pandas as pd
from rapidfuzz import fuzz
from typing import Dict, List, Tuple
import re


def normalize_outcome_name(name: str) -> str:
    """Normalize outcome name for better matching."""
    name = str(name).lower().strip()
    # Remove units and parentheticals
    name = re.sub(r'\([^)]*\)', '', name)
    # Remove common variations
    name = name.replace('usd', '').replace('ppp', '')
    name = name.replace('monthly', '').replace('yearly', '').replace('daily', '')
    name = name.replace('per capita', '').replace('per household', '')
    # Remove extra spaces
    name = re.sub(r'\s+', ' ', name).strip()
    return name


def extract_keywords(name: str) -> set:
    """Extract key outcome words."""
    normalized = normalize_outcome_name(name)
    # Remove common words
    stopwords = {'the', 'a', 'an', 'of', 'in', 'on', 'at', 'to', 'for', 'with', 'by', 'from'}
    words = set(normalized.split()) - stopwords
    return words


def fuzzy_match_outcomes(
    extracted_name: str,
    gt_name: str,
    threshold: float = 70.0
) -> Tuple[bool, float, str]:
    """
    Match outcome names using multiple strategies.
    
    Returns:
        (is_match, score, method)
    """
    # Strategy 1: Exact match after normalization
    norm_ext = normalize_outcome_name(extracted_name)
    norm_gt = normalize_outcome_name(gt_name)
    
    if norm_ext == norm_gt:
        return True, 100.0, "exact_normalized"
    
    # Strategy 2: Substring match
    if norm_ext in norm_gt or norm_gt in norm_ext:
        return True, 90.0, "substring"
    
    # Strategy 3: Fuzzy string similarity
    ratio = fuzz.ratio(norm_ext, norm_gt)
    if ratio >= threshold:
        return True, ratio, "fuzzy_ratio"
    
    # Strategy 4: Token set ratio (handles word order differences)
    token_ratio = fuzz.token_set_ratio(norm_ext, norm_gt)
    if token_ratio >= threshold:
        return True, token_ratio, "fuzzy_token"
    
    # Strategy 5: Keyword overlap (at least 50% of GT keywords present)
    ext_keywords = extract_keywords(extracted_name)
    gt_keywords = extract_keywords(gt_name)
    
    if gt_keywords and len(ext_keywords & gt_keywords) / len(gt_keywords) >= 0.5:
        overlap_score = len(ext_keywords & gt_keywords) / len(gt_keywords) * 100
        return True, overlap_score, "keyword_overlap"
    
    # Strategy 6: Partial ratio (handles extra text)
    partial_ratio = fuzz.partial_ratio(norm_ext, norm_gt)
    if partial_ratio >= 85:  # Higher threshold for partial
        return True, partial_ratio, "fuzzy_partial"
    
    return False, 0.0, "no_match"


def find_best_match(
    extracted_outcome: Dict,
    gt_outcomes: List[Dict],
    threshold: float = 70.0
) -> Tuple[bool, Dict, float, str]:
    """
    Find best matching GT outcome for an extracted outcome.
    
    Returns:
        (found_match, matched_gt_outcome, score, method)
    """
    extracted_name = extracted_outcome.get('outcome_name', '')
    # Handle both 'outcome_category' (V3/V4/V5) and 'category' (V1/V2)
    extracted_cat = extracted_outcome.get('outcome_category') or extracted_outcome.get('category', '')
    
    best_match = None
    best_score = 0.0
    best_method = "no_match"
    
    for gt_outcome in gt_outcomes:
        gt_name = gt_outcome.get('outcome_name', '')
        gt_cat = gt_outcome.get('outcome_category', '')
        
        # Only match within same category
        if extracted_cat != gt_cat:
            continue
        
        is_match, score, method = fuzzy_match_outcomes(extracted_name, gt_name, threshold)
        
        if is_match and score > best_score:
            best_match = gt_outcome
            best_score = score
            best_method = method
    
    return best_match is not None, best_match, best_score, best_method


def compare_extractions_fuzzy(
    extractions: List[Dict],
    outcomes_gt: pd.DataFrame,
    threshold: float = 70.0,
    verbose: bool = False
) -> Dict:
    """
    Compare extractions to ground truth using fuzzy matching.
    
    Args:
        extractions: List of extraction results
        outcomes_gt: Ground truth DataFrame (already filtered to extracted studies)
        threshold: Fuzzy matching threshold (0-100)
        verbose: Print matching details
    
    Returns:
        Comparison statistics including matched outcomes
    """
    # Convert GT to list of dicts per study
    gt_by_study = {}
    for _, row in outcomes_gt.iterrows():
        study_id = str(int(row['study_id'])) if pd.notna(row['study_id']) else None
        if not study_id:
            continue
        
        if study_id not in gt_by_study:
            gt_by_study[study_id] = []
        
        gt_by_study[study_id].append({
            'outcome_name': row['outcome_name'],
            'outcome_category': row['outcome_category'],
            'effect_size_d': row.get('effect_size_d'),
            'row_index': row.name
        })
    
    # Track matches
    category_stats = {
        "Income": {"gt_count": 0, "extracted_count": 0, "matched": 0, "match_details": []},
        "Assets": {"gt_count": 0, "extracted_count": 0, "matched": 0, "match_details": []},
        "Savings": {"gt_count": 0, "extracted_count": 0, "matched": 0, "match_details": []},
        "Expenditure": {"gt_count": 0, "extracted_count": 0, "matched": 0, "match_details": []},
        "Poverty": {"gt_count": 0, "extracted_count": 0, "matched": 0, "match_details": []}
    }
    
    matched_gt_indices = set()  # Track which GT outcomes have been matched
    
    # Count GT outcomes by category
    for study_outcomes in gt_by_study.values():
        for outcome in study_outcomes:
            cat = outcome['outcome_category']
            if cat in category_stats:
                category_stats[cat]['gt_count'] += 1
    
    # Process extractions
    for extraction in extractions:
        study_id = str(extraction['study_id'])
        gt_outcomes = gt_by_study.get(study_id, [])
        extracted_outcomes = extraction.get('outcomes', [])
        
        # Count extracted by category
        for outcome in extracted_outcomes:
            # Handle both 'outcome_category' (V3/V4/V5) and 'category' (V1/V2)
            cat = outcome.get('outcome_category') or outcome.get('category', '')
            if cat in category_stats:
                category_stats[cat]['extracted_count'] += 1
        
        # Match extracted to GT
        for ext_outcome in extracted_outcomes:
            found_match, matched_gt, score, method = find_best_match(
                ext_outcome, gt_outcomes, threshold
            )
            
            if found_match:
                # Handle both 'outcome_category' (V3/V4/V5) and 'category' (V1/V2)
                cat = ext_outcome.get('outcome_category') or ext_outcome.get('category', '')
                if cat in category_stats and matched_gt['row_index'] not in matched_gt_indices:
                    category_stats[cat]['matched'] += 1
                    matched_gt_indices.add(matched_gt['row_index'])
                    
                    match_detail = {
                        'study_id': study_id,
                        'extracted_name': ext_outcome.get('outcome_name'),
                        'gt_name': matched_gt['outcome_name'],
                        'score': score,
                        'method': method,
                        'extracted_d': ext_outcome.get('computed_d'),
                        'gt_d': matched_gt['effect_size_d']
                    }
                    category_stats[cat]['match_details'].append(match_detail)
                    
                    if verbose:
                        print(f"✓ {cat}: '{ext_outcome.get('outcome_name')}' → '{matched_gt['outcome_name']}' ({method}, {score:.1f})")
    
    # Calculate recall by category
    for cat in category_stats:
        gt_count = category_stats[cat]['gt_count']
        matched = category_stats[cat]['matched']
        category_stats[cat]['recall'] = matched / gt_count if gt_count > 0 else 0
        category_stats[cat]['precision'] = (
            matched / category_stats[cat]['extracted_count']
            if category_stats[cat]['extracted_count'] > 0 else 0
        )
    
    # Overall metrics
    total_gt = sum(cat['gt_count'] for cat in category_stats.values())
    total_matched = sum(cat['matched'] for cat in category_stats.values())
    total_extracted = sum(cat['extracted_count'] for cat in category_stats.values())
    
    overall_recall = total_matched / total_gt if total_gt > 0 else 0
    overall_precision = total_matched / total_extracted if total_extracted > 0 else 0
    
    # Cohen's d comparison for matched outcomes
    d_comparisons = []
    for cat_stats in category_stats.values():
        for match_detail in cat_stats['match_details']:
            if match_detail['extracted_d'] is not None and match_detail['gt_d'] is not None:
                if pd.notna(match_detail['gt_d']):
                    d_comparisons.append({
                        'extracted': match_detail['extracted_d'],
                        'gt': match_detail['gt_d'],
                        'diff': abs(match_detail['extracted_d'] - match_detail['gt_d'])
                    })
    
    d_within_02 = sum(1 for d in d_comparisons if d['diff'] <= 0.2)
    d_accuracy = d_within_02 / len(d_comparisons) if d_comparisons else 0
    
    return {
        'by_category': category_stats,
        'overall_recall': overall_recall,
        'overall_precision': overall_precision,
        'total_gt_outcomes': total_gt,
        'total_matched': total_matched,
        'total_extracted': total_extracted,
        'd_within_0.2': d_accuracy,
        'd_comparison_count': len(d_comparisons),
        'matching_threshold': threshold
    }


if __name__ == "__main__":
    # Test the matching
    test_cases = [
        ("Livestock revenue (yearly, USD)", "Monthly livestock revenues (USD PPP)"),
        ("Agricultural asset value (USD)", "Agricultural asset value (USD PPP)"),
        ("Harvest value (yearly, USD)", "Monthly business revenues (USD PPP)"),
        ("Tontine/AVEC savings (3 months, USD)", "Savings deposits (last 3 months, USD PPP)"),
    ]
    
    print("Testing fuzzy outcome matching:\n")
    for gt_name, ext_name in test_cases:
        is_match, score, method = fuzzy_match_outcomes(ext_name, gt_name)
        status = "✓ MATCH" if is_match else "✗ NO MATCH"
        print(f"{status} ({method}, {score:.1f})")
        print(f"  GT:  {gt_name}")
        print(f"  Ext: {ext_name}\n")
