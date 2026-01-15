#!/usr/bin/env python3
"""
Comprehensive baseline analysis for extraction validation.
Generates detailed error reports from baseline results.
"""

import json
from pathlib import Path
from collections import Counter

def load_results():
    """Load both baseline result files."""
    eval_dir = Path(__file__).parent
    
    with open(eval_dir / "baseline_extraction_results.json") as f:
        metadata_results = json.load(f)
    
    with open(eval_dir / "outcome_extraction_results.json") as f:
        outcome_results = json.load(f)
    
    return metadata_results, outcome_results

def analyze_metadata_errors(results):
    """Detailed error analysis for metadata extraction."""
    fields = ["study_design", "country", "health_comp", "skills_comp", 
              "savings_comp", "coaching_comp", "social_comp", "targeting_women"]
    
    errors = {field: [] for field in fields}
    
    for r in results["results"]:
        gt = r["ground_truth"]
        ext = r["extracted"]
        study_id = r["study_id"]
        author = gt.get("author", "Unknown")
        country = gt.get("country", "Unknown")
        
        for field in fields:
            gt_val = gt.get(field)
            ext_val = ext.get(field)
            
            # Normalize for comparison
            if isinstance(gt_val, str) and isinstance(ext_val, str):
                match = gt_val.lower() == ext_val.lower()
            else:
                match = gt_val == ext_val
            
            if not match:
                errors[field].append({
                    "study_id": study_id,
                    "author": author,
                    "country": country,
                    "ground_truth": gt_val,
                    "extracted": ext_val
                })
    
    return errors

def analyze_outcome_extraction(results):
    """Detailed analysis of outcome extraction."""
    analysis = {
        "perfect_recall": [],
        "partial_recall": [],
        "low_recall": [],
        "extraction_ratio": []
    }
    
    for r in results["results"]:
        study_id = r["study_id"]
        gt = r["ground_truth"]
        # Check both possible field names - 'extracted' contains 'outcomes'
        ext_data = r.get("extracted", {})
        if isinstance(ext_data, dict):
            ext = ext_data.get("outcomes", [])
        else:
            ext = r.get("extraction", {}).get("outcomes", [])
        
        author = gt.get("author", "Unknown")
        country = gt.get("country", "Unknown")
        gt_outcomes = gt.get("outcomes", [])
        
        # Count outcomes
        n_gt = len(gt_outcomes)
        n_ext = len(ext) if isinstance(ext, list) else 0
        
        # Category recall
        gt_categories = set(o.get("category") for o in gt_outcomes if o.get("category"))
        ext_categories = set(o.get("category") for o in ext if o.get("category"))
        
        if gt_categories:
            recall = len(gt_categories & ext_categories) / len(gt_categories)
        else:
            recall = 1.0
        
        entry = {
            "study_id": study_id,
            "author": author,
            "country": country,
            "n_gt_outcomes": n_gt,
            "n_extracted": n_ext,
            "ratio": n_ext / n_gt if n_gt > 0 else 0,
            "category_recall": recall,
            "gt_categories": list(gt_categories),
            "ext_categories": list(ext_categories),
            "missing_categories": list(gt_categories - ext_categories)
        }
        
        analysis["extraction_ratio"].append(entry)
        
        if recall == 1.0:
            analysis["perfect_recall"].append(entry)
        elif recall >= 0.75:
            analysis["partial_recall"].append(entry)
        else:
            analysis["low_recall"].append(entry)
    
    return analysis

def generate_report():
    """Generate comprehensive error report."""
    metadata_results, outcome_results = load_results()
    
    # Analyze
    metadata_errors = analyze_metadata_errors(metadata_results)
    outcome_analysis = analyze_outcome_extraction(outcome_results)
    
    # Print report
    print("=" * 80)
    print("BASELINE EXTRACTION ERROR ANALYSIS")
    print("=" * 80)
    
    # Metadata Section
    print("\n" + "=" * 60)
    print("METADATA EXTRACTION ERRORS")
    print("=" * 60)
    
    for field, errors in metadata_errors.items():
        n_errors = len(errors)
        n_total = metadata_results["num_studies"]
        accuracy = (n_total - n_errors) / n_total * 100
        
        print(f"\n{field}: {n_errors} errors ({accuracy:.1f}% accuracy)")
        print("-" * 40)
        
        if errors:
            for e in errors:
                print(f"  • {e['study_id']} ({e['author']}, {e['country']})")
                print(f"    GT: {e['ground_truth']} → Extracted: {e['extracted']}")
    
    # Outcome Section
    print("\n" + "=" * 60)
    print("OUTCOME EXTRACTION ANALYSIS")
    print("=" * 60)
    
    print(f"\nPerfect Category Recall (100%): {len(outcome_analysis['perfect_recall'])} studies")
    print(f"Partial Category Recall (75-99%): {len(outcome_analysis['partial_recall'])} studies")
    print(f"Low Category Recall (<75%): {len(outcome_analysis['low_recall'])} studies")
    
    # Low recall details
    if outcome_analysis["low_recall"]:
        print("\n--- LOW CATEGORY RECALL STUDIES ---")
        for e in outcome_analysis["low_recall"]:
            print(f"\n  • {e['study_id']} ({e['author']}, {e['country']})")
            print(f"    Category Recall: {e['category_recall']:.0%}")
            print(f"    Missing: {e['missing_categories']}")
    
    # Extraction ratio analysis
    print("\n--- OUTCOME COUNT COMPARISON ---")
    ratios = outcome_analysis["extraction_ratio"]
    ratios_sorted = sorted(ratios, key=lambda x: x["ratio"])
    
    print("\nLowest extraction ratios (most under-extraction):")
    for e in ratios_sorted[:10]:
        print(f"  • {e['study_id']}: {e['n_extracted']}/{e['n_gt_outcomes']} ({e['ratio']:.0%})")
    
    print("\nHighest extraction ratios:")
    for e in ratios_sorted[-5:]:
        print(f"  • {e['study_id']}: {e['n_extracted']}/{e['n_gt_outcomes']} ({e['ratio']:.0%})")
    
    # Summary stats
    avg_ratio = sum(e["ratio"] for e in ratios) / len(ratios) if ratios else 0
    print(f"\nAverage extraction ratio: {avg_ratio:.1%}")
    
    # Category distribution
    print("\n--- CATEGORY EXTRACTION COVERAGE ---")
    all_gt = Counter()
    all_ext = Counter()
    for e in ratios:
        for cat in e["gt_categories"]:
            all_gt[cat] += 1
        for cat in e["ext_categories"]:
            all_ext[cat] += 1
    
    for cat in sorted(all_gt.keys()):
        gt_count = all_gt[cat]
        ext_count = all_ext.get(cat, 0)
        coverage = ext_count / gt_count * 100 if gt_count > 0 else 0
        print(f"  {cat}: {ext_count}/{gt_count} studies ({coverage:.0f}% coverage)")
    
    # Save JSON report
    eval_dir = Path(__file__).parent
    report = {
        "metadata_errors": metadata_errors,
        "outcome_analysis": {
            "perfect_recall_count": len(outcome_analysis["perfect_recall"]),
            "partial_recall_count": len(outcome_analysis["partial_recall"]),
            "low_recall_count": len(outcome_analysis["low_recall"]),
            "low_recall_studies": outcome_analysis["low_recall"],
            "avg_extraction_ratio": avg_ratio,
            "category_coverage": {
                cat: {
                    "gt_studies": all_gt[cat],
                    "extracted_studies": all_ext.get(cat, 0),
                    "coverage": all_ext.get(cat, 0) / all_gt[cat] if all_gt[cat] > 0 else 0
                }
                for cat in all_gt
            }
        }
    }
    
    with open(eval_dir / "baseline_error_analysis.json", "w") as f:
        json.dump(report, f, indent=2)
    
    print(f"\n\nFull report saved to: evaluation/baseline_error_analysis.json")

if __name__ == "__main__":
    generate_report()
