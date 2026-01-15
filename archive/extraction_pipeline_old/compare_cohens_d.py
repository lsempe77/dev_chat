"""
Compare extracted Cohen's d values with Ground Truth effect_size_d.
"""
import json
import pandas as pd
import numpy as np
from pathlib import Path

# Paths
COHENS_D_PATH = Path(__file__).parent / "v17d_cohens_d_results.json"
GT_PATH = Path(__file__).parent.parent / "evaluation" / "matched_studies_r2.json"
V16_PATH = Path(__file__).parent / "v16_results.json"

# Load data
with open(COHENS_D_PATH) as f:
    cohens_d_results = json.load(f)

with open(GT_PATH) as f:
    gt_studies = json.load(f)

with open(V16_PATH) as f:
    v16_results = json.load(f)

# Build GT lookup by study_id and outcome name
gt_lookup = {}
for study in gt_studies:
    study_id = study["study_id"]
    gt_data = study.get("ground_truth", {})
    outcomes = gt_data.get("outcomes", [])
    
    for outcome in outcomes:
        name = outcome.get("name", "").lower().strip()
        key = (study_id, name)
        gt_lookup[key] = outcome

print("=" * 70)
print("COHEN'S D vs GROUND TRUTH COMPARISON")
print("=" * 70)

all_comparisons = []

for study in cohens_d_results["studies"]:
    study_id = study["study_id"]
    author = study["author"]
    
    print(f"\n--- {author} ---")
    
    study_comparisons = []
    
    for outcome in study["enriched_outcomes"]:
        if outcome.get("cohens_d") is None:
            continue
        
        outcome_name = outcome["outcome_name"].lower().strip()
        extracted_d = outcome["cohens_d"]
        
        # Try to find in GT
        key = (study_id, outcome_name)
        gt_outcome = gt_lookup.get(key)
        
        if gt_outcome:
            gt_d = gt_outcome.get("effect_size_d")
            if gt_d is not None:
                diff = abs(extracted_d - gt_d)
                ratio = extracted_d / gt_d if gt_d != 0 else None
                
                study_comparisons.append({
                    "study": author,
                    "outcome": outcome["outcome_name"][:40],
                    "extracted_d": extracted_d,
                    "gt_d": gt_d,
                    "difference": diff,
                    "ratio": ratio,
                    "close": diff < 0.1 or (ratio and 0.8 < ratio < 1.2)
                })
    
    if study_comparisons:
        print(f"  Found {len(study_comparisons)} comparisons")
        
        n_close = sum(1 for c in study_comparisons if c["close"])
        print(f"  Close matches (diff < 0.1 or ratio 0.8-1.2): {n_close}/{len(study_comparisons)}")
        
        all_comparisons.extend(study_comparisons)

# Summary
print("\n" + "=" * 70)
print("OVERALL SUMMARY")
print("=" * 70)

if all_comparisons:
    df = pd.DataFrame(all_comparisons)
    
    print(f"\nTotal comparisons: {len(df)}")
    print(f"Close matches: {df['close'].sum()} ({100*df['close'].mean():.1f}%)")
    
    print(f"\nDifference statistics:")
    print(f"  Mean: {df['difference'].mean():.4f}")
    print(f"  Median: {df['difference'].median():.4f}")
    print(f"  Min: {df['difference'].min():.4f}")
    print(f"  Max: {df['difference'].max():.4f}")
    
    # Show sample comparisons
    print("\n" + "=" * 70)
    print("SAMPLE COMPARISONS (first 10 with close matches)")
    print("=" * 70)
    
    close_matches = df[df['close']].head(10)
    for _, row in close_matches.iterrows():
        print(f"\n  {row['outcome']}...")
        print(f"    Extracted d: {row['extracted_d']:.4f}")
        print(f"    GT d: {row['gt_d']:.4f}")
        print(f"    Diff: {row['difference']:.4f}")
    
    print("\n" + "=" * 70)
    print("SAMPLE MISMATCHES (first 10)")
    print("=" * 70)
    
    mismatches = df[~df['close']].head(10)
    for _, row in mismatches.iterrows():
        print(f"\n  {row['outcome']}...")
        print(f"    Extracted d: {row['extracted_d']:.4f}")
        print(f"    GT d: {row['gt_d']:.4f}")
        print(f"    Diff: {row['difference']:.4f}")
        if row['ratio']:
            print(f"    Ratio: {row['ratio']:.2f}x")
    
    # Save to CSV
    df.to_csv(Path(__file__).parent / "cohens_d_comparison.csv", index=False)
    print(f"\n\nResults saved to cohens_d_comparison.csv")
else:
    print("\nNo comparisons found - outcome names may not match exactly between extracted and GT")
    print("This is expected because V17d extracts table row names which may differ from GT names")


# Alternative: Use V16 matched outcomes to map extracted -> GT
print("\n" + "=" * 70)
print("USING V16 MATCHED OUTCOMES FOR MAPPING")
print("=" * 70)

# V16 contains the matches between extracted and GT outcomes
mapped_comparisons = []

for study in v16_results["studies"]:
    study_id = study["study_id"]
    author = study["author"]
    
    # Get V16 extracted outcomes
    extracted_outcomes = {o["outcome_name"].lower().strip(): o for o in study.get("extracted_outcomes", [])}
    
    # Get Cohen's d results for this study
    cohens_study = next((s for s in cohens_d_results["studies"] if s["study_id"] == study_id), None)
    if not cohens_study:
        continue
    
    cohens_outcomes = {o["outcome_name"].lower().strip(): o for o in cohens_study["enriched_outcomes"]}
    
    # Get GT for this study
    gt_study = next((s for s in gt_studies if s["study_id"] == study_id), None)
    if not gt_study:
        continue
    
    gt_outcomes_list = gt_study.get("ground_truth", {}).get("outcomes", [])
    
    print(f"\n--- {author} ---")
    print(f"  Extracted with d: {len([o for o in cohens_outcomes.values() if o.get('cohens_d')])}")
    print(f"  GT outcomes: {len(gt_outcomes_list)}")
    
    # For each extracted outcome with Cohen's d, try to find matching GT
    for ext_name, ext_outcome in cohens_outcomes.items():
        if ext_outcome.get("cohens_d") is None:
            continue
        
        extracted_d = ext_outcome["cohens_d"]
        
        # Find best matching GT by name similarity
        best_match = None
        best_score = 0
        
        for gt in gt_outcomes_list:
            gt_name = gt.get("name", "").lower().strip()
            
            # Simple word overlap scoring
            ext_words = set(ext_name.replace('^', '').replace('{', '').replace('}', '').split())
            gt_words = set(gt_name.split())
            
            if ext_words and gt_words:
                overlap = len(ext_words & gt_words)
                score = overlap / min(len(ext_words), len(gt_words))
                
                if score > best_score:
                    best_score = score
                    best_match = gt
        
        if best_match and best_score >= 0.5:  # At least 50% word overlap
            gt_d = best_match.get("effect_size_d")
            if gt_d is not None:
                diff = abs(extracted_d - gt_d)
                mapped_comparisons.append({
                    "study": author,
                    "extracted_outcome": ext_outcome["outcome_name"][:40],
                    "gt_outcome": best_match.get("name", "")[:40],
                    "match_score": best_score,
                    "extracted_d": extracted_d,
                    "gt_d": gt_d,
                    "difference": diff,
                    "close": diff < 0.1
                })

if mapped_comparisons:
    df2 = pd.DataFrame(mapped_comparisons)
    
    print("\n" + "=" * 70)
    print("MAPPED COMPARISON RESULTS")
    print("=" * 70)
    
    print(f"\nTotal mapped comparisons: {len(df2)}")
    print(f"Close matches (diff < 0.1): {df2['close'].sum()} ({100*df2['close'].mean():.1f}%)")
    
    print(f"\nDifference statistics:")
    print(f"  Mean: {df2['difference'].mean():.4f}")
    print(f"  Median: {df2['difference'].median():.4f}")
    
    # Show examples
    print("\n--- Sample Close Matches ---")
    for _, row in df2[df2['close']].head(5).iterrows():
        print(f"\n  Extracted: {row['extracted_outcome']}...")
        print(f"  GT: {row['gt_outcome']}...")
        print(f"  Extracted d: {row['extracted_d']:.4f}, GT d: {row['gt_d']:.4f}, Diff: {row['difference']:.4f}")
    
    df2.to_csv(Path(__file__).parent / "cohens_d_mapped_comparison.csv", index=False)
    print(f"\n\nMapped results saved to cohens_d_mapped_comparison.csv")
