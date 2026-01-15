"""
Analyze V4 extraction results by comparing to ground truth.
This script just runs the comparison without re-running extraction.
"""

import json
import pandas as pd
from datetime import datetime
from typing import Dict, List


def compare_outcomes_to_gt(extractions: List[Dict], outcomes_gt: pd.DataFrame) -> Dict:
    """Compare extracted outcomes to ground truth outcomes."""
    
    # Map study_id to extractions
    ext_lookup = {str(e["study_id"]): e for e in extractions}
    
    category_stats = {
        "Income": {"gt_count": 0, "extracted_count": 0, "matched": 0},
        "Assets": {"gt_count": 0, "extracted_count": 0, "matched": 0},
        "Savings": {"gt_count": 0, "extracted_count": 0, "matched": 0},
        "Expenditure": {"gt_count": 0, "extracted_count": 0, "matched": 0},
        "Poverty": {"gt_count": 0, "extracted_count": 0, "matched": 0}
    }
    
    d_comparisons = []
    gt_matched_ids = set()
    
    # Group GT by study
    for study_id in ext_lookup.keys():
        # Convert study_id to float for matching
        study_id_float = float(study_id)
        study_gt = outcomes_gt[outcomes_gt['study_id'] == study_id_float]
        extracted = ext_lookup[study_id].get("outcomes", [])
        
        for idx, gt_row in study_gt.iterrows():
            cat = gt_row.get('outcome_category', 'Other')
            if pd.isna(cat) or cat not in category_stats:
                continue
            
            category_stats[cat]["gt_count"] += 1
            
            # Find matching extracted outcome
            gt_name = str(gt_row.get('outcome_name', '')).lower().strip()
            matched = False
            
            for ext_out in extracted:
                ext_name = str(ext_out.get('outcome_name', '')).lower().strip()
                
                # More flexible matching - check word overlap
                gt_words = set(gt_name.split())
                ext_words = set(ext_name.split())
                
                # Match if significant word overlap or substring match
                overlap = len(gt_words & ext_words)
                total = len(gt_words | ext_words) if gt_words | ext_words else 1
                
                if overlap >= 2 or overlap / total > 0.4 or gt_name in ext_name or ext_name in gt_name:
                    matched = True
                    gt_matched_ids.add(idx)
                    
                    # Compare Cohen's d
                    gt_d = gt_row.get('effect_size_d')
                    ext_d = ext_out.get('computed_d')
                    if pd.notna(gt_d) and ext_d is not None:
                        try:
                            gt_d_val = float(gt_d)
                            ext_d_val = float(ext_d)
                            d_comparisons.append({
                                "study_id": study_id,
                                "outcome": gt_name,
                                "gt_d": gt_d_val,
                                "extracted_d": ext_d_val,
                                "diff": abs(gt_d_val - ext_d_val)
                            })
                        except (ValueError, TypeError):
                            pass
                    break
            
            if matched:
                category_stats[cat]["matched"] += 1
        
        # Count extracted by category
        for ext_out in extracted:
            cat = ext_out.get('outcome_category', 'Other')
            if cat in category_stats:
                category_stats[cat]["extracted_count"] += 1
    
    # Calculate recall per category
    for cat in category_stats:
        gt_count = category_stats[cat]["gt_count"]
        matched = category_stats[cat]["matched"]
        category_stats[cat]["recall"] = matched / gt_count if gt_count > 0 else 0
    
    # Overall recall
    total_gt = sum(s["gt_count"] for s in category_stats.values())
    total_matched = sum(s["matched"] for s in category_stats.values())
    total_extracted = sum(s["extracted_count"] for s in category_stats.values())
    
    return {
        "by_category": category_stats,
        "total_gt_outcomes": total_gt,
        "total_matched": total_matched,
        "total_extracted": total_extracted,
        "overall_recall": total_matched / total_gt if total_gt > 0 else 0,
        "d_comparisons": d_comparisons,
        "d_within_0.2": sum(1 for d in d_comparisons if d["diff"] < 0.2) / len(d_comparisons) if d_comparisons else 0
    }


def main():
    print("=" * 60)
    print("V4 MULTI-PASS EXTRACTION - RESULTS ANALYSIS")
    print("=" * 60)
    
    # Load ground truth outcomes from Excel file
    print("\nLoading ground truth...")
    outcomes_gt = pd.read_excel("8WR QEX Combined.xlsx", sheet_name="Sheet1")
    
    # Rename columns to match expected names
    outcomes_gt = outcomes_gt.rename(columns={
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
    
    print(f"Ground truth: {len(outcomes_gt)} outcomes across {outcomes_gt['study_id'].nunique()} studies")
    
    # Try to load extraction results (run the extraction again to capture outputs)
    # For now, we'll re-run extraction or load from file
    
    try:
        with open("evaluation/v4_extraction_results_partial.json") as f:
            partial_data = json.load(f)
            extractions = partial_data.get("extractions", [])
            print(f"\nLoaded {len(extractions)} partial extractions")
    except FileNotFoundError:
        print("\nNo partial results found. Need to run extraction.")
        return
    
    # Count total outcomes extracted
    total_extracted = sum(len(e.get("outcomes", [])) for e in extractions)
    print(f"Total outcomes extracted: {total_extracted}")
    
    # Run comparison
    print("\n" + "=" * 60)
    print("COMPARING TO GROUND TRUTH")
    print("=" * 60)
    
    comparison = compare_outcomes_to_gt(extractions, outcomes_gt)
    
    # Print outcome results
    print("\nOutcome Recall by Category:")
    print("-" * 50)
    for cat, stats in comparison["by_category"].items():
        recall = stats.get("recall", 0) * 100
        print(f"  {cat:15} | GT: {stats['gt_count']:3} | Matched: {stats['matched']:3} | Recall: {recall:5.1f}%")
    
    print("-" * 50)
    overall_recall = comparison["overall_recall"] * 100
    print(f"\n📊 OVERALL OUTCOME RECALL: {overall_recall:.1f}%")
    print(f"   Ground truth: {comparison['total_gt_outcomes']} outcomes")
    print(f"   Extracted:    {comparison['total_extracted']} outcomes")
    print(f"   Matched:      {comparison['total_matched']} outcomes")
    print(f"   (V3 was 53.6%, target is >80%)")
    
    if comparison["d_comparisons"]:
        d_accuracy = comparison["d_within_0.2"] * 100
        print(f"\n📊 Cohen's d within 0.2: {d_accuracy:.1f}% ({len(comparison['d_comparisons'])} comparisons)")
    
    # Save results
    output = {
        "version": "v4_multipass",
        "timestamp": datetime.now().isoformat(),
        "n_studies": len(extractions),
        "comparison": {
            "outcome_recall": comparison["overall_recall"],
            "total_gt_outcomes": comparison["total_gt_outcomes"],
            "total_extracted": comparison["total_extracted"],
            "total_matched": comparison["total_matched"],
            "outcome_recall_by_category": {
                cat: stats["recall"] 
                for cat, stats in comparison["by_category"].items()
            },
            "d_accuracy": comparison["d_within_0.2"],
            "d_comparisons_count": len(comparison["d_comparisons"])
        }
    }
    
    with open("evaluation/v4_analysis_results.json", "w") as f:
        json.dump(output, f, indent=2, default=str)
    
    print(f"\nResults saved to evaluation/v4_analysis_results.json")


if __name__ == "__main__":
    main()
