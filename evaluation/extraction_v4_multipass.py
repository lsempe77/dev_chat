"""
Extraction V4 - Multi-Pass Outcome Discovery

KEY IMPROVEMENTS over V3:
1. Multi-pass extraction: Scan for outcomes by category in separate passes
2. Table-focused parsing: Special pass to find table data
3. Targeted prompts: More specific prompts for each outcome category
4. Better chunking: Process document in sections to find all outcomes

GOAL: Improve outcome recall from 53.6% to >80%
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
MODEL = "anthropic/claude-3.5-sonnet"  # Use claude-3.5-sonnet (works on OpenRouter)
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
    
    # Strategy 3: Fix newlines in strings
    fixed = re.sub(r'(?<=["\'])\s*\n\s*(?=[^"\']*["\'])', ' ', cleaned)
    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass
    
    # Strategy 4: Extract fields using regex
    result = {}
    field_pattern = r'"(\w+)":\s*\{\s*"value":\s*([^,}]+),\s*"confidence":\s*([\d.]+)'
    for match in re.finditer(field_pattern, cleaned):
        field_name = match.group(1)
        value_str = match.group(2).strip()
        confidence = float(match.group(3))
        
        if value_str.lower() == 'true':
            value = True
        elif value_str.lower() == 'false':
            value = False
        elif value_str.startswith('"'):
            value = value_str.strip('"')
        else:
            try:
                value = float(value_str) if '.' in value_str else int(value_str)
            except ValueError:
                value = value_str
        
        result[field_name] = {"value": value, "confidence": confidence}
    
    if result:
        return result
    
    # Strategy 5: ast.literal_eval
    try:
        import ast
        py_str = cleaned.replace('true', 'True').replace('false', 'False').replace('null', 'None')
        return ast.literal_eval(py_str)
    except:
        pass
    
    return {}


def call_llm(prompt: str, max_tokens: int = 4096, retries: int = 3) -> Dict:
    """Call OpenRouter API with retry logic."""
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
                print(f"    400 Error - likely content too long, truncating...")
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
# V4: MULTI-PASS EXTRACTION PROMPTS
# ============================================================================

METADATA_PROMPT = """Extract metadata from this academic study on poverty/development interventions.

DOCUMENT (first 30K chars):
{content}

Extract these fields with confidence scores:

1. study_design: "RCT" or "Quasi-experimental"
2. country: Where study was conducted
3. year: Publication year
4. author: First author's last name
5. program_name: Name of the intervention/program
6. targeting_women: true/false - does program specifically target women?

INTERVENTION COMPONENTS (true/false):
- consumption_support: Cash/food transfers
- health_comp: Health services/education
- asset_transfer: Livestock, equipment, assets
- skills_comp: Training, vocational skills
- savings_comp: Savings groups, financial literacy
- coaching_comp: Mentoring, life skills support
- social_comp: Social networks, community groups

Return ONLY valid JSON:
{{"study_design": {{"value": "RCT", "confidence": 0.95}}, "country": {{"value": "Bangladesh", "confidence": 0.99}}, ...}}
"""

# V4 KEY INNOVATION: Category-specific outcome prompts
OUTCOME_CATEGORY_PROMPTS = {
    "Income": """Find ALL INCOME-RELATED outcomes in this study.

DOCUMENT:
{content}

Look for outcomes measuring:
- Total income, earnings, wages
- Business profits, revenue, sales
- Agricultural income, crop income
- Non-farm income, labor income
- Self-employment earnings

For EACH outcome found, extract:
- outcome_name: Specific name (e.g., "Monthly household income")
- coefficient: Treatment effect (number)
- standard_error: SE of coefficient
- n_treatment: Treatment group N
- n_control: Control group N
- n_total: Total N if separate Ns not available
- evidence_table: Table/figure reference

Return JSON with array of outcomes:
{{"outcomes": [{{"outcome_name": "...", "coefficient": ..., "standard_error": ..., "n_treatment": ..., "n_control": ..., "n_total": ..., "evidence_table": "..."}}]}}

If NO income outcomes found, return: {{"outcomes": []}}
""",

    "Assets": """Find ALL ASSET-RELATED outcomes in this study.

DOCUMENT:
{content}

Look for outcomes measuring:
- Total asset value, wealth index
- Livestock value/count
- Durable goods, household assets
- Productive assets (tools, equipment)
- Land ownership/value
- Housing quality/value

For EACH outcome found, extract:
- outcome_name: Specific name (e.g., "Total asset value")
- coefficient: Treatment effect (number)
- standard_error: SE of coefficient
- n_treatment: Treatment group N
- n_control: Control group N
- n_total: Total N if separate Ns not available
- evidence_table: Table/figure reference

Return JSON: {{"outcomes": [...]}}
If NO asset outcomes found, return: {{"outcomes": []}}
""",

    "Savings": """Find ALL SAVINGS-RELATED outcomes in this study.

DOCUMENT:
{content}

Look for outcomes measuring:
- Formal savings (bank accounts)
- Informal savings (ROSCA, groups)
- Total savings balance
- Savings rate/propensity
- Financial inclusion

For EACH outcome found, extract:
- outcome_name, coefficient, standard_error, n_treatment, n_control, n_total, evidence_table

Return JSON: {{"outcomes": [...]}}
If NO savings outcomes found, return: {{"outcomes": []}}
""",

    "Expenditure": """Find ALL EXPENDITURE/CONSUMPTION outcomes in this study.

DOCUMENT:
{content}

Look for outcomes measuring:
- Total consumption/expenditure
- Food consumption/expenditure
- Non-food expenditure
- Per capita consumption
- Household spending

For EACH outcome found, extract:
- outcome_name, coefficient, standard_error, n_treatment, n_control, n_total, evidence_table

Return JSON: {{"outcomes": [...]}}
If NO expenditure outcomes found, return: {{"outcomes": []}}
""",

    "Poverty": """Find ALL POVERTY-RELATED outcomes in this study.

DOCUMENT:
{content}

Look for outcomes measuring:
- Poverty status (above/below line)
- Poverty index/score
- Food security (meals/day, food diversity)
- Poverty gap measures
- Ultra-poverty indicators

For EACH outcome found, extract:
- outcome_name, coefficient, standard_error, n_treatment, n_control, n_total, evidence_table

Return JSON: {{"outcomes": [...]}}
If NO poverty outcomes found, return: {{"outcomes": []}}
"""
}

# V4 INNOVATION 2: Table-focused extraction pass
TABLE_EXTRACTION_PROMPT = """Look at the TABLES in this document and extract outcome statistics.

DOCUMENT:
{content}

Focus on regression/results tables. For EACH row/outcome in results tables, extract:
- outcome_name: What is being measured
- outcome_category: Income, Assets, Savings, Expenditure, or Poverty
- coefficient: The treatment effect coefficient
- standard_error: The standard error (often in parentheses below coefficient)
- t_statistic: t-stat if shown
- n_treatment: Treatment N
- n_control: Control N  
- n_total: Total N (often at bottom of table)
- evidence_table: Table number/name

Return JSON: {{"outcomes": [...]}}
Focus on getting ALL outcomes from ALL tables, not just the first one.
"""


def extract_study_v4(study_id: str, content: str) -> Dict:
    """
    V4 Multi-pass extraction:
    1. Metadata extraction
    2. Table-focused pass (finds most outcomes)
    3. Category-by-category passes (catches missed outcomes)
    4. Deduplicate and merge
    """
    
    # NO TRUNCATION - use full paper to capture results tables at end
    # max_chars = 25000
    # truncated = content[:max_chars] if len(content) > max_chars else content
    
    result = {
        "study_id": study_id,
        "metadata": {},
        "outcomes": [],
        "extraction_method": "v4_multipass_fullpaper",
        "extraction_timestamp": datetime.now().isoformat()
    }
    
    # Pass 1: Metadata
    print(f"    [1/3] Metadata extraction...")
    metadata_result = call_llm(METADATA_PROMPT.format(content=content))
    if metadata_result:
        result["metadata"] = metadata_result
    time.sleep(1)
    
    # Pass 2: Table-focused extraction (most outcomes are in tables)
    print(f"    [2/3] Table-focused extraction...")
    table_result = call_llm(TABLE_EXTRACTION_PROMPT.format(content=content))
    all_outcomes = []
    if table_result and "outcomes" in table_result:
        for o in table_result["outcomes"]:
            o["source"] = "table_pass"
        all_outcomes.extend(table_result["outcomes"])
    time.sleep(1)
    
    # Pass 3: Category-specific passes (catch what tables missed)
    print(f"    [3/3] Category-specific passes...")
    categories_to_scan = ["Income", "Assets", "Savings", "Expenditure", "Poverty"]
    
    for category in categories_to_scan:
        prompt = OUTCOME_CATEGORY_PROMPTS[category].format(content=content)
        cat_result = call_llm(prompt, max_tokens=2048)
        if cat_result and "outcomes" in cat_result:
            for o in cat_result["outcomes"]:
                o["outcome_category"] = category
                o["source"] = f"{category.lower()}_pass"
            all_outcomes.extend(cat_result["outcomes"])
        time.sleep(0.5)  # Shorter delay between category passes
    
    # Deduplicate outcomes by name similarity
    unique_outcomes = deduplicate_outcomes(all_outcomes)
    
    # Compute Cohen's d for each outcome
    for outcome in unique_outcomes:
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
    
    result["outcomes"] = unique_outcomes
    return result


def deduplicate_outcomes(outcomes: List[Dict]) -> List[Dict]:
    """Remove duplicate outcomes based on name similarity."""
    if not outcomes:
        return []
    
    unique = []
    seen_names = set()
    
    for o in outcomes:
        name = o.get("outcome_name", "").lower().strip()
        if not name:
            continue
        
        # Normalize name for comparison
        normalized = re.sub(r'[^\w\s]', '', name)
        words = set(normalized.split())
        
        # Check if this is too similar to an existing outcome
        is_duplicate = False
        for seen in seen_names:
            seen_words = set(seen.split())
            # If >70% word overlap, consider duplicate
            if len(words & seen_words) >= 0.7 * min(len(words), len(seen_words)):
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
    
    d_comparisons = []
    
    # Group GT by study
    for study_id in ext_lookup.keys():
        study_gt = outcomes_gt_filtered[
            outcomes_gt_filtered['study_id'].apply(lambda x: str(int(x)) if pd.notna(x) else "") == study_id
        ]
        extracted = ext_lookup[study_id].get("outcomes", [])
        
        for _, gt_row in study_gt.iterrows():
            cat = gt_row.get('outcome_category', 'Other')
            if cat not in category_stats:
                continue
            
            category_stats[cat]["gt_count"] += 1
            
            # Find matching extracted outcome
            gt_name = str(gt_row.get('outcome_name', '')).lower()
            matched = False
            for ext_out in extracted:
                ext_name = str(ext_out.get('outcome_name', '')).lower()
                if gt_name in ext_name or ext_name in gt_name:
                    matched = True
                    # Compare Cohen's d
                    gt_d = gt_row.get('effect_size_d')
                    ext_d = ext_out.get('computed_d')
                    if gt_d is not None and ext_d is not None:
                        d_comparisons.append({
                            "study_id": study_id,
                            "outcome": gt_name,
                            "gt_d": gt_d,
                            "extracted_d": ext_d,
                            "diff": abs(gt_d - ext_d)
                        })
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
    
    return {
        "by_category": category_stats,
        "total_gt_outcomes": total_gt,
        "total_matched": total_matched,
        "overall_recall": total_matched / total_gt if total_gt > 0 else 0,
        "d_comparisons": d_comparisons,
        "d_within_0.2": sum(1 for d in d_comparisons if d["diff"] < 0.2) / len(d_comparisons) if d_comparisons else 0
    }


def main():
    """Run V4 multi-pass extraction on test studies."""
    print("=" * 60)
    print("V4 MULTI-PASS EXTRACTION")
    print("Goal: Improve outcome recall from 53.6% to >80%")
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
    
    # Run extraction on all studies
    extractions = []
    for i, study in enumerate(studies):
        study_id = study.get('study_id', f'study_{i}')
        print(f"\n[{i+1}/{len(studies)}] Processing {study_id}...")
        
        content = load_document_content(study)
        if not content:
            print(f"    SKIP: No content")
            continue
        
        result = extract_study_v4(study_id, content)
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
    print(f"   (V3 was 53.6%, target is >80%)")
    
    d_accuracy = comparison["outcomes"]["d_within_0.2"] * 100
    print(f"📊 Cohen's d within 0.2: {d_accuracy:.1f}%")
    
    # Save results
    output = {
        "version": "v4_multipass",
        "timestamp": datetime.now().isoformat(),
        "n_studies": len(extractions),
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
    
    with open("evaluation/v4_extraction_results.json", "w") as f:
        json.dump(output, f, indent=2, default=str)
    
    print(f"\nResults saved to evaluation/v4_extraction_results.json")


if __name__ == "__main__":
    main()
