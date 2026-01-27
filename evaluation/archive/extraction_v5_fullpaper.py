"""
Extraction V5 - Full Paper Processing

KEY CHANGE from V4:
- REMOVE the 25K char truncation limit
- Process the FULL document content
- Results tables are typically at the END of papers, so truncation was killing recall

Strategy:
1. Load full document from R2 (no truncation)
2. Single comprehensive extraction pass with full context
3. Simpler than V4's multi-pass approach but with complete data

HYPOTHESIS: V4's 34.4% recall was due to truncation cutting off results tables.
Reading full papers should restore recall to >V3's 53.6% and hopefully reach >80% target.
"""

import os
import re
import json
import boto3
import requests
import numpy as np
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from dotenv import load_dotenv
import pandas as pd
import time

load_dotenv()

OPENROUTER_API_KEY = os.environ.get('OPENROUTER_API_KEY')
MODEL = "anthropic/claude-3.5-sonnet"
CLOUDFLARE_ACCOUNT_ID = os.environ.get('CLOUDFLARE_ACCOUNT_ID')
R2_ACCESS_KEY = os.environ.get('R2_ACCESS_KEY_ID')
R2_SECRET_KEY = os.environ.get('R2_SECRET_ACCESS_KEY')

# ============================================================================
# COHEN'S D FORMULA (verified in V3)
# ============================================================================

def compute_cohens_d(
    coef: Optional[float] = None,
    se: Optional[float] = None,
    t_stat: Optional[float] = None,
    n_treatment: Optional[int] = None,
    n_control: Optional[int] = None,
    n_total: Optional[int] = None,
    mean_t: Optional[float] = None,
    mean_c: Optional[float] = None,
    sd_t: Optional[float] = None,
    sd_c: Optional[float] = None
) -> Tuple[Optional[float], str]:
    """Compute Cohen's d using verified formula: d = (coef/se) * sqrt(1/n1 + 1/n2)"""
    
    if coef is not None and se is not None and n_treatment and n_control and se != 0:
        d = (coef / se) * np.sqrt(1/n_treatment + 1/n_control)
        return d, "formula_exact"
    
    if t_stat is not None and n_treatment and n_control:
        d = t_stat * np.sqrt(1/n_treatment + 1/n_control)
        return d, "t_stat_with_ns"
    
    if coef is not None and se is not None and n_total and se != 0:
        n1 = n2 = n_total / 2
        d = (coef / se) * np.sqrt(1/n1 + 1/n2)
        return d, "formula_n_total"
    
    if all(x is not None for x in [mean_t, mean_c, sd_t, sd_c]) and (sd_t > 0 or sd_c > 0):
        pooled_sd = np.sqrt((sd_t**2 + sd_c**2) / 2)
        if pooled_sd > 0:
            d = (mean_t - mean_c) / pooled_sd
            return d, "means_and_sds"
    
    return None, "insufficient_data"


# Global session for connection reuse
SESSION = requests.Session()
SESSION.headers.update({
    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
    "Content-Type": "application/json"
})


def robust_json_parse(content: str) -> Dict:
    """Parse JSON with multiple fallback strategies."""
    json_match = re.search(r'\{[\s\S]*\}', content)
    if not json_match:
        return {}
    
    json_str = json_match.group()
    
    # Strategy 1: Direct parse
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        pass
    
    # Strategy 2: Remove control characters
    cleaned = re.sub(r'[\x00-\x1f\x7f-\x9f]', ' ', json_str)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    
    # Strategy 3: Fix common issues
    fixed = cleaned.replace('\n', ' ').replace('\r', ' ')
    fixed = re.sub(r',\s*}', '}', fixed)
    fixed = re.sub(r',\s*]', ']', fixed)
    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        return {}


def call_llm(prompt: str, max_tokens: int = 4096, retries: int = 3) -> Dict:
    """Call OpenRouter API with exponential backoff."""
    for attempt in range(retries):
        try:
            response = SESSION.post(
                "https://openrouter.ai/api/v1/chat/completions",
                json={
                    "model": MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": max_tokens,
                    "temperature": 0
                },
                timeout=300
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            return robust_json_parse(content)
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 400:
                print(f"    400 Error: {str(e)[:100]}")
                return {}
            if attempt < retries - 1:
                wait = 5 * (attempt + 1)
                print(f"    Retry {attempt + 1}/{retries}: {str(e)[:80]}")
                time.sleep(wait)
            else:
                print(f"    Failed: {str(e)[:80]}")
                return {}
        except Exception as e:
            if attempt < retries - 1:
                print(f"    Retry {attempt + 1}/{retries}: {str(e)[:80]}")
                time.sleep(5 * (attempt + 1))
            else:
                print(f"    Failed: {str(e)[:80]}")
                return {}
    return {}


def load_document_content(study_data: Dict) -> Optional[str]:
    """Load markdown content from R2."""
    try:
        r2_key = study_data.get('r2_key')
        if not r2_key:
            return None
        
        bucket = os.environ.get('R2_BUCKET_NAME', 'devchat-pdfs')
        
        s3 = boto3.client(
            's3',
            endpoint_url=f'https://{CLOUDFLARE_ACCOUNT_ID}.r2.cloudflarestorage.com',
            aws_access_key_id=R2_ACCESS_KEY,
            aws_secret_access_key=R2_SECRET_KEY
        )
        
        response = s3.get_object(Bucket=bucket, Key=r2_key)
        content = response['Body'].read()
        
        try:
            return content.decode('utf-8')
        except UnicodeDecodeError:
            return content.decode('latin-1')
    except Exception as e:
        print(f"    Error loading document: {e}")
        return None


# ============================================================================
# V5: FULL PAPER EXTRACTION PROMPT
# ============================================================================

FULL_PAPER_PROMPT = """Extract ALL outcomes and metadata from this COMPLETE academic study on poverty/development interventions.

FULL DOCUMENT:
{content}

Extract in TWO sections:

1. METADATA (return as nested objects with confidence scores):
- study_design: "RCT" or "Quasi-experimental"
- country: Where study was conducted
- year: Publication year
- author: First author's last name
- program_name: Name of the intervention/program
- targeting_women: true/false - does program specifically target women?
- consumption_support: true/false - Cash/food transfers
- health_comp: true/false - Health services/education
- asset_transfer: true/false - Livestock, equipment, assets
- skills_comp: true/false - Training, vocational skills
- savings_comp: true/false - Savings groups, financial literacy
- coaching_comp: true/false - Mentoring, life skills support
- social_comp: true/false - Social networks, community groups

2. OUTCOMES: Extract EVERY outcome from ALL results tables. For EACH outcome:
- outcome_name: What is being measured (be specific)
- outcome_category: MUST be one of: "Income", "Assets", "Savings", "Expenditure", "Poverty"
- coefficient: Treatment effect coefficient
- standard_error: Standard error (often in parentheses)
- t_statistic: t-stat if available
- n_treatment: Treatment group N
- n_control: Control group N
- n_total: Total N
- evidence_location: "Table X" or "Page Y"

CRITICAL INSTRUCTIONS:
- Read the ENTIRE document including ALL tables at the end
- Extract EVERY outcome from EVERY results table
- Results tables are typically near the end of the paper - don't miss them!
- If a table has 10 outcomes, extract all 10
- For outcome_category, map outcomes to the closest category:
  * Income: earnings, wages, income, revenue
  * Assets: livestock, equipment, housing, wealth index
  * Savings: savings amounts, savings groups
  * Expenditure: spending, consumption, expenses
  * Poverty: poverty rate, poverty gap, below poverty line

Return ONLY valid JSON:
{{
  "metadata": {{
    "study_design": {{"value": "RCT", "confidence": 0.95}},
    "country": {{"value": "Bangladesh", "confidence": 0.99}},
    ...
  }},
  "outcomes": [
    {{
      "outcome_name": "Monthly income",
      "outcome_category": "Income",
      "coefficient": 245.30,
      "standard_error": 89.20,
      "t_statistic": 2.75,
      "n_treatment": 1200,
      "n_control": 1300,
      "n_total": 2500,
      "evidence_location": "Table 3"
    }},
    ...
  ]
}}

DO NOT truncate or summarize. Extract EVERY outcome you can find with as much detail as available.
"""


def extract_study_v5(study_id: str, content: str) -> Dict:
    """
    V5: Full paper extraction - NO TRUNCATION
    
    Key change: Use the ENTIRE document content in one comprehensive pass.
    This ensures we capture results tables that are typically at the end of papers.
    """
    
    print(f"    Document size: {len(content)/1000:.0f}K chars")
    
    result = {
        "study_id": study_id,
        "metadata": {},
        "outcomes": [],
        "extraction_method": "v5_fullpaper",
        "extraction_timestamp": datetime.now().isoformat(),
        "document_size_chars": len(content)
    }
    
    # Single comprehensive extraction with full document
    print(f"    Extracting from full paper...")
    extraction = call_llm(FULL_PAPER_PROMPT.format(content=content), max_tokens=8192)
    
    if extraction:
        result["metadata"] = extraction.get("metadata", {})
        raw_outcomes = extraction.get("outcomes", [])
        
        # Compute Cohen's d for each outcome
        for outcome in raw_outcomes:
            d, method = compute_cohens_d(
                coef=outcome.get("coefficient"),
                se=outcome.get("standard_error"),
                t_stat=outcome.get("t_statistic"),
                n_treatment=outcome.get("n_treatment"),
                n_control=outcome.get("n_control"),
                n_total=outcome.get("n_total")
            )
            outcome["computed_d"] = d
            outcome["computation_method"] = method
        
        result["outcomes"] = raw_outcomes
    
    return result


def deduplicate_outcomes(outcomes: List[Dict]) -> List[Dict]:
    """Remove duplicate outcomes based on name similarity."""
    if not outcomes:
        return []
    
    def normalize_name(name: str) -> str:
        if not name:
            return ""
        return re.sub(r'[^a-z0-9]', '', str(name).lower())
    
    seen_names = set()
    unique = []
    
    for o in outcomes:
        name = o.get("outcome_name", "")
        normalized = normalize_name(name)
        
        if not normalized:
            continue
        
        is_duplicate = False
        for seen in seen_names:
            if normalized == seen or normalized in seen or seen in normalized:
                is_duplicate = True
                break
        
        if not is_duplicate:
            seen_names.add(normalized)
            unique.append(o)
    
    return unique


def compare_to_ground_truth(extractions: List[Dict], studies: List[Dict], outcomes_gt: pd.DataFrame) -> Dict:
    """Compare extractions to ground truth."""
    
    gt_lookup = {str(s['study_id']): s.get('ground_truth', {}) for s in studies}
    
    # Metadata comparison
    metadata_fields = [
        "study_design", "country", "consumption_support", "health_comp",
        "asset_transfer", "skills_comp", "savings_comp", "coaching_comp",
        "social_comp", "targeting_women"
    ]
    
    metadata_results = {f: {"correct": 0, "total": 0} for f in metadata_fields}
    
    for ext in extractions:
        study_id = str(ext["study_id"])
        gt = gt_lookup.get(study_id, {})
        
        for field in metadata_fields:
            if field not in gt:
                continue
            
            metadata_results[field]["total"] += 1
            
            extracted = ext.get("metadata", {}).get(field, {})
            if isinstance(extracted, dict):
                extracted_val = extracted.get("value")
            else:
                extracted_val = extracted
            
            gt_val = gt[field]
            
            # Normalize for comparison
            if isinstance(gt_val, str):
                match = str(extracted_val).lower().strip() == gt_val.lower().strip()
            else:
                match = extracted_val == gt_val
            
            if match:
                metadata_results[field]["correct"] += 1
    
    # Calculate accuracies
    for field in metadata_fields:
        total = metadata_results[field]["total"]
        correct = metadata_results[field]["correct"]
        metadata_results[field]["accuracy"] = correct / total if total > 0 else 0
    
    # Outcome comparison
    outcome_comparison = compare_outcomes_to_gt(extractions, outcomes_gt)
    
    return {
        "metadata": metadata_results,
        "outcomes": outcome_comparison
    }


def compare_outcomes_to_gt(extractions: List[Dict], outcomes_gt: pd.DataFrame) -> Dict:
    """Compare extracted outcomes to ground truth outcomes."""
    
    # Map study_id to extractions
    ext_lookup = {str(e["study_id"]): e for e in extractions}
    
    # FILTER GT to only include studies that were extracted
    # Convert study_id properly: float -> int -> str (e.g., 121058356.0 -> 121058356 -> "121058356")
    extracted_study_ids = list(ext_lookup.keys())
    outcomes_gt_filtered = outcomes_gt[
        outcomes_gt['study_id'].apply(lambda x: str(int(x)) if pd.notna(x) else "").isin(extracted_study_ids)
    ]
    
    category_stats = {
        "Income": {"gt_count": 0, "extracted_count": 0, "matched": 0},
        "Assets": {"gt_count": 0, "extracted_count": 0, "matched": 0},
        "Savings": {"gt_count": 0, "extracted_count": 0, "matched": 0},
        "Expenditure": {"gt_count": 0, "extracted_count": 0, "matched": 0},
        "Poverty": {"gt_count": 0, "extracted_count": 0, "matched": 0}
    }
    
    matched_outcomes = []
    total_gt_outcomes = 0
    d_within_02_count = 0
    d_comparison_count = 0
    
    for _, row in outcomes_gt_filtered.iterrows():
        study_id = str(row['study_id'])
        outcome_cat = row['outcome_category']
        outcome_name = str(row['outcome_name']).lower().strip()
        gt_d = row.get('effect_size_d')
        
        total_gt_outcomes += 1
        if outcome_cat in category_stats:
            category_stats[outcome_cat]["gt_count"] += 1
        
        # Check if extracted
        ext = ext_lookup.get(study_id)
        if not ext:
            continue
        
        # Look for matching outcome
        for extracted_outcome in ext.get("outcomes", []):
            ext_name = str(extracted_outcome.get("outcome_name", "")).lower().strip()
            ext_cat = extracted_outcome.get("outcome_category", "")
            ext_d = extracted_outcome.get("computed_d")
            
            # Name matching (fuzzy)
            if outcome_name in ext_name or ext_name in outcome_name or \
               (len(outcome_name) > 3 and len(ext_name) > 3 and \
                outcome_name[:4] == ext_name[:4]):
                
                if outcome_cat in category_stats:
                    category_stats[outcome_cat]["matched"] += 1
                
                matched_outcomes.append({
                    "study_id": study_id,
                    "outcome_name": outcome_name,
                    "gt_d": gt_d,
                    "extracted_d": ext_d
                })
                
                # Compare d values
                if gt_d is not None and ext_d is not None and pd.notna(gt_d) and pd.notna(ext_d):
                    d_comparison_count += 1
                    if abs(gt_d - ext_d) <= 0.2:
                        d_within_02_count += 1
                
                break
    
    # Count extracted outcomes by category
    for ext in extractions:
        for outcome in ext.get("outcomes", []):
            cat = outcome.get("outcome_category", "")
            if cat in category_stats:
                category_stats[cat]["extracted_count"] += 1
    
    # Calculate recall by category
    for cat in category_stats:
        gt_count = category_stats[cat]["gt_count"]
        matched = category_stats[cat]["matched"]
        category_stats[cat]["recall"] = matched / gt_count if gt_count > 0 else 0
    
    overall_recall = sum(cat["matched"] for cat in category_stats.values()) / total_gt_outcomes if total_gt_outcomes > 0 else 0
    d_accuracy = d_within_02_count / d_comparison_count if d_comparison_count > 0 else 0
    
    return {
        "by_category": category_stats,
        "overall_recall": overall_recall,
        "d_within_0.2": d_accuracy,
        "total_gt_outcomes": total_gt_outcomes,
        "total_matched": sum(cat["matched"] for cat in category_stats.values()),
        "matched_outcomes": matched_outcomes
    }


def main():
    """Run V5 full-paper extraction on test studies."""
    print("=" * 60)
    print("V5 FULL-PAPER EXTRACTION")
    print("Key change: NO truncation - use complete documents")
    print("=" * 60)
    
    # Load matched studies
    with open("evaluation/matched_studies_r2.json") as f:
        studies = json.load(f)
    
    # Load ground truth outcomes from Excel file
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
    
    # TEST MODE: Run on first 3 studies to check document sizes and costs
    test_mode = False
    if test_mode:
        print("\n🧪 TEST MODE: Processing first 3 studies to check feasibility...")
        studies = studies[:3]
    else:
        print(f"\n🚀 FULL RUN: Processing all {len(studies)} studies...")
    
    # Run extraction on all studies
    extractions = []
    for i, study in enumerate(studies):
        study_id = study.get('study_id', f'study_{i}')
        print(f"\n[{i+1}/{len(studies)}] Processing {study_id}...")
        
        content = load_document_content(study)
        if not content:
            print(f"    SKIP: No content")
            continue
        
        result = extract_study_v5(study_id, content)
        extractions.append(result)
        
        print(f"    Extracted {len(result['outcomes'])} outcomes")
    
    # Compare to ground truth
    print("\n" + "=" * 60)
    print("COMPARING TO GROUND TRUTH")
    print("=" * 60)
    
    comparison = compare_to_ground_truth(extractions, studies, outcomes_gt)
    
    # Print metadata results
    print("\nMetadata Accuracy:")
    for field, stats in comparison["metadata"].items():
        acc = stats.get("accuracy", 0) * 100
        print(f"  {field}: {acc:.1f}% ({stats['correct']}/{stats['total']})")
    
    # Print outcome results
    print("\nOutcome Recall by Category:")
    for cat, stats in comparison["outcomes"]["by_category"].items():
        recall = stats.get("recall", 0) * 100
        print(f"  {cat}: {recall:.1f}% ({stats['matched']}/{stats['gt_count']})")
    
    overall_recall = comparison["outcomes"]["overall_recall"] * 100
    print(f"\n📊 OVERALL OUTCOME RECALL: {overall_recall:.1f}%")
    print(f"   V3: 53.6% | V4: 34.4% | V5 Target: >80%")
    
    d_accuracy = comparison["outcomes"]["d_within_0.2"] * 100
    print(f"📊 Cohen's d within 0.2: {d_accuracy:.1f}%")
    
    # Document size stats
    if extractions:
        sizes = [e["document_size_chars"] for e in extractions]
        print(f"\n📄 Document sizes:")
        print(f"   Avg: {sum(sizes)/len(sizes)/1000:.0f}K chars")
        print(f"   Max: {max(sizes)/1000:.0f}K chars")
        print(f"   Min: {min(sizes)/1000:.0f}K chars")
    
    # Save results
    output = {
        "version": "v5_fullpaper",
        "timestamp": datetime.now().isoformat(),
        "n_studies": len(extractions),
        "test_mode": test_mode,
        "extractions": extractions,
        "comparison": {
            "metadata": comparison["metadata"],
            "outcome_recall": comparison["outcomes"]["overall_recall"],
            "outcome_recall_by_category": {
                cat: stats["recall"] 
                for cat, stats in comparison["outcomes"]["by_category"].items()
            },
            "d_accuracy": comparison["outcomes"]["d_within_0.2"]
        }
    }
    
    filename = "evaluation/v5_test_results.json" if test_mode else "evaluation/v5_extraction_results.json"
    with open(filename, "w") as f:
        json.dump(output, f, indent=2, default=str)
    
    print(f"\nResults saved to {filename}")
    
    if test_mode:
        print("\n" + "=" * 60)
        print("TEST COMPLETE")
        print("Review results, then set test_mode=False to run on all 43 studies")
        print("=" * 60)


if __name__ == "__main__":
    main()
