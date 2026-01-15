"""
Evaluate Stage 2 extraction against ground truth.
Measures how accurately we extracted coefficients and SEs for matched outcomes.
"""
import json
import pandas as pd
from pathlib import Path
import numpy as np

# Load ground truth from matched_studies_r2.json
GT_PATH = Path(__file__).parent.parent / "evaluation" / "matched_studies_r2.json"
STAGE2_PATH = Path(__file__).parent / "v17d_stage2_results.json"
V16_PATH = Path(__file__).parent / "v16_results.json"

with open(GT_PATH) as f:
    matched_studies = json.load(f)

# Extract ground truth structure
ground_truth = []
for study in matched_studies:
    gt_data = study.get("ground_truth", {})
    ground_truth.append({
        "study_id": study["study_id"],
        "author": gt_data.get("author", "Unknown"),
        "outcomes": gt_data.get("outcomes", [])
    })

with open(STAGE2_PATH) as f:
    stage2_results = json.load(f)

with open(V16_PATH) as f:
    v16_results = json.load(f)

print("=" * 70)
print("STAGE 2 EVALUATION: Parameter Extraction Accuracy")
print("=" * 70)

all_matches = []

for study in stage2_results["studies"]:
    study_id = study["study_id"]
    author = study["author"]
    
    # Find GT for this study
    gt_study = next((s for s in ground_truth if s["study_id"] == study_id), None)
    if not gt_study:
        continue
    
    # Find V16 results for this study (contains match info)
    v16_study = next((s for s in v16_results["studies"] if s["study_id"] == study_id), None)
    if not v16_study:
        continue
    
    # Get matched outcomes from V16
    matched_outcomes = v16_study.get("matched_outcomes", [])
    
    print(f"\n--- {author} ---")
    print(f"Ground truth outcomes: {len(gt_study['outcomes'])}")
    print(f"Matched outcomes (from V16): {len(matched_outcomes)}")
    
    # Build lookup for stage2 outcomes by name
    stage2_lookup = {}
    for outcome in study["enriched_outcomes"]:
        name = outcome["outcome_name"].lower().strip()
        stage2_lookup[name] = outcome
    
    # Build GT lookup
    gt_lookup = {}
    for outcome in gt_study["outcomes"]:
        name = outcome["name"].lower().strip()
        gt_lookup[name] = outcome
    
    study_matches = []
    
    for match in matched_outcomes:
        gt_name = match["gt_outcome"].lower().strip()
        extracted_name = match["extracted_outcome"].lower().strip()
        
        # Get GT values
        gt_outcome = gt_lookup.get(gt_name, {})
        gt_coef = gt_outcome.get("effect_size_d")
        gt_se = gt_outcome.get("se")
        
        # Get extracted values from stage2
        stage2_outcome = stage2_lookup.get(extracted_name, {})
        extracted_coef = stage2_outcome.get("coefficient")
        extracted_se = stage2_outcome.get("standard_error")
        
        study_matches.append({
            "study": author,
            "gt_outcome": match["gt_outcome"],
            "extracted_outcome": match["extracted_outcome"],
            "gt_coef": gt_coef,
            "extracted_coef": extracted_coef,
            "gt_se": gt_se,
            "extracted_se": extracted_se,
            "coef_match": None,
            "se_match": None
        })
    
    all_matches.extend(study_matches)

# Convert to DataFrame for analysis
df = pd.DataFrame(all_matches)

# Calculate matches
def check_coef_match(row):
    if pd.isna(row["gt_coef"]) or row["gt_coef"] is None:
        return "no_gt"
    if row["extracted_coef"] is None:
        return "not_extracted"
    try:
        gt = float(row["gt_coef"])
        ext = float(row["extracted_coef"])
        # Check if exact match or within 10% tolerance
        if gt == ext:
            return "exact"
        elif abs(gt - ext) / (abs(gt) + 1e-10) < 0.1:
            return "close"
        else:
            return "mismatch"
    except:
        return "error"

def check_se_match(row):
    if pd.isna(row["gt_se"]) or row["gt_se"] is None:
        return "no_gt"
    if row["extracted_se"] is None:
        return "not_extracted"
    try:
        gt = float(row["gt_se"])
        ext = float(row["extracted_se"])
        if gt == ext:
            return "exact"
        elif abs(gt - ext) / (abs(gt) + 1e-10) < 0.1:
            return "close"
        else:
            return "mismatch"
    except:
        return "error"

df["coef_match"] = df.apply(check_coef_match, axis=1)
df["se_match"] = df.apply(check_se_match, axis=1)

print("\n" + "=" * 70)
print("COEFFICIENT EXTRACTION RESULTS")
print("=" * 70)
coef_counts = df["coef_match"].value_counts()
print(coef_counts)

# Calculate meaningful metrics
n_with_gt_coef = len(df[~df["gt_coef"].isna()])
n_extracted = len(df[df["extracted_coef"].notna()])
n_exact = len(df[df["coef_match"] == "exact"])
n_close = len(df[df["coef_match"] == "close"])
n_match = n_exact + n_close

print(f"\nGT outcomes with coefficient: {n_with_gt_coef}")
print(f"Extracted coefficients: {n_extracted}")
print(f"Exact matches: {n_exact}")
print(f"Close matches (±10%): {n_close}")
print(f"Total matches: {n_match} ({100*n_match/n_with_gt_coef:.1f}% of GT)")

print("\n" + "=" * 70)
print("STANDARD ERROR EXTRACTION RESULTS")
print("=" * 70)
se_counts = df["se_match"].value_counts()
print(se_counts)

n_with_gt_se = len(df[~df["gt_se"].isna()])
n_extracted_se = len(df[df["extracted_se"].notna()])
n_exact_se = len(df[df["se_match"] == "exact"])
n_close_se = len(df[df["se_match"] == "close"])
n_match_se = n_exact_se + n_close_se

print(f"\nGT outcomes with SE: {n_with_gt_se}")
print(f"Extracted SEs: {n_extracted_se}")
print(f"Exact matches: {n_exact_se}")
print(f"Close matches (±10%): {n_close_se}")
print(f"Total matches: {n_match_se} ({100*n_match_se/max(n_with_gt_se,1):.1f}% of GT)")

# Show some examples of mismatches
print("\n" + "=" * 70)
print("SAMPLE MISMATCHES (for debugging)")
print("=" * 70)
mismatches = df[df["coef_match"] == "mismatch"].head(10)
for _, row in mismatches.iterrows():
    print(f"\n{row['study']}: {row['gt_outcome'][:50]}...")
    print(f"  GT coef: {row['gt_coef']}, Extracted: {row['extracted_coef']}")

# By-study breakdown
print("\n" + "=" * 70)
print("BY-STUDY BREAKDOWN")
print("=" * 70)
for study in df["study"].unique():
    study_df = df[df["study"] == study]
    n_total = len(study_df)
    n_exact = len(study_df[study_df["coef_match"] == "exact"])
    n_close = len(study_df[study_df["coef_match"] == "close"])
    n_extracted = len(study_df[study_df["extracted_coef"].notna()])
    print(f"\n{study}:")
    print(f"  Total matched: {n_total}")
    print(f"  Coef extracted: {n_extracted}")
    print(f"  Exact: {n_exact}, Close: {n_close}")
    print(f"  Match rate: {100*(n_exact+n_close)/max(n_total,1):.1f}%")

# Save detailed results
df.to_csv(Path(__file__).parent / "stage2_evaluation_details.csv", index=False)
print(f"\n\nDetailed results saved to stage2_evaluation_details.csv")
