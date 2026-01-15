"""
Evaluate Stage 2 extraction against ground truth.
Measures how accurately we extracted coefficients and SEs for matched outcomes.

Approach:
1. For each Stage 2 enriched outcome, find the best matching GT outcome
2. Compare extracted coefficient/SE against GT effect_size_d/se
"""
import json
import pandas as pd
from pathlib import Path
import numpy as np
from openai import OpenAI
import os

client = OpenAI()

# Load data
GT_PATH = Path(__file__).parent.parent / "evaluation" / "matched_studies_r2.json"
STAGE2_PATH = Path(__file__).parent / "v17d_stage2_results.json"

with open(GT_PATH) as f:
    matched_studies = json.load(f)

with open(STAGE2_PATH) as f:
    stage2_results = json.load(f)

# Build lookup for GT by study_id
gt_lookup = {}
for study in matched_studies:
    study_id = study["study_id"]
    gt_data = study.get("ground_truth", {})
    gt_lookup[study_id] = {
        "author": gt_data.get("author", "Unknown"),
        "outcomes": gt_data.get("outcomes", [])
    }

def get_embedding(text: str) -> list:
    """Get embedding for text."""
    response = client.embeddings.create(
        model="text-embedding-3-small",
        input=text
    )
    return response.data[0].embedding

def cosine_similarity(a: list, b: list) -> float:
    """Calculate cosine similarity."""
    a = np.array(a)
    b = np.array(b)
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

def find_best_gt_match(extracted_name: str, gt_outcomes: list) -> tuple:
    """Find best matching GT outcome by embedding similarity."""
    if not gt_outcomes:
        return None, 0.0
    
    ext_emb = get_embedding(extracted_name)
    best_match = None
    best_sim = 0.0
    
    for gt in gt_outcomes:
        gt_name = gt.get("name", "")
        gt_emb = get_embedding(gt_name)
        sim = cosine_similarity(ext_emb, gt_emb)
        if sim > best_sim:
            best_sim = sim
            best_match = gt
    
    return best_match, best_sim

print("=" * 70)
print("STAGE 2 EVALUATION: Parameter Extraction Accuracy")
print("=" * 70)

all_results = []

# Process each study - but only compare outcomes that have coefficients extracted
for study in stage2_results["studies"]:
    study_id = study["study_id"]
    author = study["author"]
    
    gt_data = gt_lookup.get(study_id)
    if not gt_data:
        print(f"No GT found for {author}")
        continue
    
    gt_outcomes = gt_data["outcomes"]
    
    print(f"\n--- {author} ---")
    print(f"GT outcomes: {len(gt_outcomes)}")
    print(f"Enriched outcomes: {len(study['enriched_outcomes'])}")
    
    # Filter to outcomes with coefficients
    enriched_with_coef = [o for o in study["enriched_outcomes"] if o.get("coefficient") is not None]
    print(f"With coefficients: {len(enriched_with_coef)}")
    
    # For each enriched outcome with coefficient, find best GT match
    for outcome in enriched_with_coef[:3]:  # Limit for demo - embedding calls are expensive
        extracted_name = outcome["outcome_name"]
        extracted_coef = outcome.get("coefficient")
        extracted_se = outcome.get("standard_error")
        
        best_gt, similarity = find_best_gt_match(extracted_name, gt_outcomes)
        
        if best_gt and similarity > 0.6:  # Only consider good matches
            gt_coef = best_gt.get("effect_size_d")
            gt_se = best_gt.get("se")
            
            all_results.append({
                "study": author,
                "extracted_name": extracted_name,
                "gt_name": best_gt.get("name"),
                "similarity": similarity,
                "extracted_coef": extracted_coef,
                "gt_coef": gt_coef,
                "extracted_se": extracted_se,
                "gt_se": gt_se
            })
            
            print(f"  Matched: '{extracted_name[:40]}...' -> '{best_gt.get('name', '')[:40]}...' (sim={similarity:.2f})")
            print(f"    Coef: extracted={extracted_coef}, gt={gt_coef}")

print("\n" + "=" * 70)
print("SAMPLE RESULTS (first 3 per study with coefficients)")
print("=" * 70)

df = pd.DataFrame(all_results)
if len(df) > 0:
    print(df.to_string())
    
    # Save to file
    df.to_csv(Path(__file__).parent / "stage2_gt_comparison.csv", index=False)
    print(f"\nResults saved to stage2_gt_comparison.csv")
