"""
Extraction V4 - Multi-pass outcome extraction for improved recall

Key improvements over V3:
1. Multi-pass extraction: Multiple prompts targeting different outcome types
2. Table-focused extraction: Separate pass for table parsing
3. Targeted SE extraction: Dedicated prompt for standard errors
4. Deduplication: Merge results across passes

Target: >80% outcome recall (V3 was 53.6%)
"""

import os
import re
import json
import boto3
import requests
import numpy as np
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple, Set
from datetime import datetime
from dotenv import load_dotenv
import time

load_dotenv()

OPENROUTER_API_KEY = os.environ.get('OPENROUTER_API_KEY')
MODEL = "anthropic/claude-3.5-sonnet"  # Fixed: was using invalid model name
CLOUDFLARE_ACCOUNT_ID = os.environ.get('CLOUDFLARE_ACCOUNT_ID')
R2_ACCESS_KEY = os.environ.get('R2_ACCESS_KEY_ID')
R2_SECRET_KEY = os.environ.get('R2_SECRET_ACCESS_KEY')

# ============================================================================
# VERIFIED COHEN'S D FORMULA
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
    """Compute Cohen's d using the verified formula."""
    # Method 1: From coefficient/SE with n_treatment and n_control
    if coef is not None and se is not None and n_treatment and n_control and se != 0:
        n1, n2 = n_treatment, n_control
        d = (coef / se) * np.sqrt(1/n1 + 1/n2)
        return d, "formula_5_exact"
    
    # Method 2: From t-statistic with sample sizes
    if t_stat is not None and n_treatment and n_control:
        n1, n2 = n_treatment, n_control
        d = t_stat * np.sqrt(1/n1 + 1/n2)
        return d, "t_stat_with_ns"
    
    # Method 3: From coefficient/SE with n_total (assume 50/50 split)
    if coef is not None and se is not None and n_total and se != 0:
        n1 = n2 = n_total / 2
        d = (coef / se) * np.sqrt(1/n1 + 1/n2)
        return d, "formula_6_n_total"
    
    # Method 4: From means and SDs
    if all(x is not None for x in [mean_t, mean_c, sd_t, sd_c]) and (sd_t > 0 or sd_c > 0):
        pooled_sd = np.sqrt((sd_t**2 + sd_c**2) / 2)
        if pooled_sd > 0:
            d = (mean_t - mean_c) / pooled_sd
            return d, "means_and_sds"
    
    return None, "insufficient_data"


# ============================================================================
# ROBUST JSON PARSING (from V3)
# ============================================================================

def robust_json_parse(content: str) -> Dict:
    """Parse JSON with multiple fallback strategies."""
    json_match = re.search(r'\{[\s\S]*\}', content)
    if not json_match:
        # Try to find array
        array_match = re.search(r'\[[\s\S]*\]', content)
        if array_match:
            try:
                return {"outcomes": json.loads(array_match.group())}
            except:
                pass
        return {}
    
    json_str = json_match.group()
    
    # Try direct parse
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        pass
    
    # Remove control characters
    cleaned = re.sub(r'[\x00-\x1f\x7f-\x9f]', ' ', json_str)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    
    # Fix newlines in strings
    fixed = re.sub(r'(?<=["\'])\s*\n\s*(?=[^"\']*["\'])', ' ', cleaned)
    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass
    
    # Regex extraction fallback
    result = {}
    field_pattern = r'"(\w+)":\s*\{\s*"value":\s*([^,}]+),\s*"confidence":\s*([\d.]+)(?:,\s*"evidence":\s*"([^"]*)")?\s*\}'
    for match in re.finditer(field_pattern, cleaned):
        field_name = match.group(1)
        value_str = match.group(2).strip()
        confidence = float(match.group(3))
        evidence = match.group(4) or ""
        
        if value_str.lower() == 'true':
            value = True
        elif value_str.lower() == 'false':
            value = False
        elif value_str.startswith('"'):
            value = value_str.strip('"')
        else:
            try:
                value = int(value_str)
            except ValueError:
                try:
                    value = float(value_str)
                except ValueError:
                    value = value_str
        
        result[field_name] = {"value": value, "confidence": confidence, "evidence": evidence}
    
    return result


# ============================================================================
# API CALLS
# ============================================================================

SESSION = requests.Session()
SESSION.headers.update({
    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
    "Content-Type": "application/json"
})


def call_llm(prompt: str, max_tokens: int = 4096, retries: int = 3) -> Dict:
    """Call OpenRouter API."""
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
                timeout=300,
                stream=False
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            
            result = robust_json_parse(content)
            if result:
                return result
            
            if attempt < retries - 1:
                print(f"    Retry {attempt + 1}/{retries} after JSON parse failure")
                time.sleep(2)
                continue
            return {}
        except Exception as e:
            if attempt < retries - 1:
                print(f"    Retry {attempt + 1}/{retries}: {str(e)[:80]}")
                time.sleep(5 * (attempt + 1))
            else:
                print(f"    Failed after {retries} attempts: {str(e)[:80]}")
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
# MULTI-PASS EXTRACTION PROMPTS
# ============================================================================

METADATA_PROMPT = """Extract metadata from this academic study on poverty/development interventions.

DOCUMENT:
{content}

Extract with evidence quotes:

1. study_design: "RCT" or "Quasi-experimental"
2. country: Where study was conducted
3. year: Publication year
4. author: First author's last name
5. program_name: Intervention/program name
6. targeting_women: true/false - specifically targets women?

7-13. INTERVENTION COMPONENTS (true/false):
- consumption_support: Cash/food transfers
- health_comp: Health services, nutrition
- asset_transfer: Livestock, equipment given
- skills_comp: Training, vocational skills
- savings_comp: Savings groups, financial literacy
- coaching_comp: Mentoring, life skills support
- social_comp: Social networks, community groups

Return JSON with value, confidence (0-1), and evidence quote for each field.
"""

# PASS 1: General outcomes extraction
OUTCOMES_PASS1_PROMPT = """Extract ALL quantitative outcomes from this study.

DOCUMENT:
{content}

Find outcomes measuring:
- INCOME: earnings, wages, profits, revenue, business income
- ASSETS: wealth, asset value, livestock value, land
- SAVINGS: formal/informal savings, bank deposits
- EXPENDITURE: consumption, spending, food expenditure
- POVERTY: poverty status, food security, hunger

For EACH outcome extract:
- outcome_name: Specific name
- outcome_category: Income, Assets, Savings, Expenditure, or Poverty
- coefficient: Treatment effect
- standard_error: SE of coefficient
- t_statistic: t-stat if available
- n_treatment: Treatment sample size
- n_control: Control sample size
- n_total: Total sample if not split
- table_reference: Which table (e.g., "Table 3")

Return JSON:
{{"outcomes": [{{...}}, {{...}}]}}

IMPORTANT: Extract EVERY outcome you can find. Do not skip any.
"""

# PASS 2: Table-focused extraction
OUTCOMES_PASS2_TABLE_PROMPT = """Focus on TABLES in this document. Extract all outcomes from tables.

DOCUMENT:
{content}

For each TABLE that shows treatment effects:
1. Identify the table number
2. Extract EVERY row that shows an outcome

Focus on:
- Table headers indicating outcome variables
- Columns showing coefficients/treatment effects
- Standard errors (usually in parentheses)
- Sample sizes (N)

For each outcome row extract:
- outcome_name: Variable name from table
- outcome_category: Income, Assets, Savings, Expenditure, or Poverty
- coefficient: The treatment effect value
- standard_error: Value in parentheses below coefficient
- n_total: Sample size from table
- table_reference: Table number

Return JSON:
{{"outcomes": [{{...}}, {{...}}]}}

Extract from ALL tables, not just main results.
"""

# PASS 3: Category-specific extraction
OUTCOMES_PASS3_INCOME_PROMPT = """Find ALL INCOME-related outcomes in this study.

DOCUMENT:
{content}

Look for ANY measure of income including:
- Earnings (daily, weekly, monthly, yearly)
- Wages
- Business profits/revenue
- Agricultural income/harvest value
- Livestock income
- Self-employment income
- Household income
- Per capita income

For EACH income outcome:
- outcome_name: Specific name
- outcome_category: "Income"
- coefficient: Treatment effect
- standard_error: SE
- n_treatment, n_control, or n_total

Return JSON:
{{"outcomes": [{{...}}]}}
"""

OUTCOMES_PASS3_ASSETS_PROMPT = """Find ALL ASSET-related outcomes in this study.

DOCUMENT:
{content}

Look for ANY measure of assets including:
- Total assets/wealth
- Livestock value/count
- Land ownership/value
- Productive assets
- Household assets
- Agricultural assets
- Business assets
- Durable goods
- Housing quality

For EACH asset outcome:
- outcome_name: Specific name
- outcome_category: "Assets"
- coefficient: Treatment effect
- standard_error: SE
- n_treatment, n_control, or n_total

Return JSON:
{{"outcomes": [{{...}}]}}
"""

OUTCOMES_PASS3_SAVINGS_PROMPT = """Find ALL SAVINGS-related outcomes in this study.

DOCUMENT:
{content}

Look for ANY measure of savings including:
- Formal savings (bank)
- Informal savings
- Savings amount
- Savings rate
- Financial inclusion
- Having a savings account
- Savings group participation

For EACH savings outcome:
- outcome_name: Specific name
- outcome_category: "Savings"
- coefficient: Treatment effect
- standard_error: SE
- n_treatment, n_control, or n_total

Return JSON:
{{"outcomes": [{{...}}]}}
"""

# PASS 4: SE recovery for outcomes missing SE
SE_RECOVERY_PROMPT = """For these outcomes, find the STANDARD ERRORS from the document.

DOCUMENT:
{content}

OUTCOMES NEEDING SE:
{outcomes_list}

For each outcome, search the document for:
1. Standard error (usually in parentheses below coefficient)
2. t-statistic (can compute SE = coef/t)
3. Confidence interval (can estimate SE)
4. p-value with sample size (can estimate SE)

Return JSON mapping outcome names to their SE:
{{"outcome_name_1": {{"standard_error": 0.05, "source": "Table 3"}}, ...}}
"""


def deduplicate_outcomes(all_outcomes: List[Dict]) -> List[Dict]:
    """Deduplicate outcomes across passes using fuzzy matching."""
    if not all_outcomes:
        return []
    
    unique = []
    seen_keys: Set[str] = set()
    
    for o in all_outcomes:
        name = o.get('outcome_name', '').lower().strip()
        cat = o.get('outcome_category', '').lower()
        coef = o.get('coefficient')
        
        # Create a key for deduplication
        # Similar names + same category + same coefficient = duplicate
        name_words = set(re.findall(r'\w+', name))
        
        is_duplicate = False
        for existing in unique:
            existing_name = existing.get('outcome_name', '').lower().strip()
            existing_words = set(re.findall(r'\w+', existing_name))
            existing_cat = existing.get('outcome_category', '').lower()
            existing_coef = existing.get('coefficient')
            
            # Same category
            if cat != existing_cat:
                continue
            
            # Similar coefficient (if both have one)
            if coef is not None and existing_coef is not None:
                if abs(coef - existing_coef) > 0.001:
                    continue
            
            # Similar name (>50% word overlap)
            if name_words and existing_words:
                overlap = len(name_words & existing_words) / max(len(name_words), len(existing_words))
                if overlap > 0.5:
                    is_duplicate = True
                    # Keep the one with more data
                    if o.get('standard_error') and not existing.get('standard_error'):
                        unique.remove(existing)
                        unique.append(o)
                    break
        
        if not is_duplicate:
            unique.append(o)
    
    return unique


def extract_study_v4(study_id: str, content: str) -> Dict:
    """Multi-pass extraction for a study."""
    
    # Use FULL paper - results tables can be anywhere (beginning, middle, or end)
    # Only truncate for metadata extraction (study design info is always at the start)
    max_metadata_chars = 30000
    
    metadata_content = content[:max_metadata_chars]
    outcome_content = content  # Use full paper for outcomes
    
    result = {
        "study_id": study_id,
        "metadata": {},
        "outcomes": [],
        "extraction_passes": {},
        "extraction_timestamp": datetime.now().isoformat()
    }
    
    # Extract metadata (uses first 30K - study design info is in abstract/intro)
    print(f"    [1/5] Extracting metadata...")
    metadata_result = call_llm(METADATA_PROMPT.format(content=metadata_content))
    if metadata_result:
        result["metadata"] = metadata_result
    
    time.sleep(1)
    
    # PASS 1: General outcomes (uses FULL content)
    print(f"    [2/5] Pass 1: General outcomes...")
    pass1 = call_llm(OUTCOMES_PASS1_PROMPT.format(content=outcome_content))
    pass1_outcomes = pass1.get("outcomes", [])
    print(f"          → Found {len(pass1_outcomes)} outcomes")
    result["extraction_passes"]["pass1_general"] = len(pass1_outcomes)
    
    time.sleep(1)
    
    # PASS 2: Table-focused (uses FULL content)
    print(f"    [3/5] Pass 2: Table-focused...")
    pass2 = call_llm(OUTCOMES_PASS2_TABLE_PROMPT.format(content=outcome_content))
    pass2_outcomes = pass2.get("outcomes", [])
    print(f"          → Found {len(pass2_outcomes)} outcomes")
    result["extraction_passes"]["pass2_tables"] = len(pass2_outcomes)
    
    time.sleep(1)
    
    # PASS 3: Category-specific (uses FULL content)
    print(f"    [4/5] Pass 3: Category-specific (Income, Assets, Savings)...")
    
    pass3_income = call_llm(OUTCOMES_PASS3_INCOME_PROMPT.format(content=outcome_content))
    pass3_assets = call_llm(OUTCOMES_PASS3_ASSETS_PROMPT.format(content=outcome_content))
    pass3_savings = call_llm(OUTCOMES_PASS3_SAVINGS_PROMPT.format(content=outcome_content))
    
    pass3_outcomes = (
        pass3_income.get("outcomes", []) + 
        pass3_assets.get("outcomes", []) +
        pass3_savings.get("outcomes", [])
    )
    print(f"          → Found {len(pass3_outcomes)} outcomes (Income: {len(pass3_income.get('outcomes', []))}, Assets: {len(pass3_assets.get('outcomes', []))}, Savings: {len(pass3_savings.get('outcomes', []))})")
    result["extraction_passes"]["pass3_category"] = len(pass3_outcomes)
    
    # Combine all outcomes
    all_outcomes = pass1_outcomes + pass2_outcomes + pass3_outcomes
    
    # Deduplicate
    print(f"    [5/5] Deduplicating {len(all_outcomes)} outcomes...")
    unique_outcomes = deduplicate_outcomes(all_outcomes)
    result["extraction_passes"]["total_before_dedup"] = len(all_outcomes)
    result["extraction_passes"]["total_after_dedup"] = len(unique_outcomes)
    
    # Compute Cohen's d for each outcome
    for outcome in unique_outcomes:
        d, method = compute_cohens_d(
            coef=outcome.get("coefficient"),
            se=outcome.get("standard_error"),
            t_stat=outcome.get("t_statistic"),
            n_treatment=outcome.get("n_treatment"),
            n_control=outcome.get("n_control"),
            n_total=outcome.get("n_total"),
            mean_t=outcome.get("mean_treatment"),
            mean_c=outcome.get("mean_control"),
            sd_t=outcome.get("sd_treatment"),
            sd_c=outcome.get("sd_control")
        )
        outcome["computed_d"] = d
        outcome["computation_method"] = method
    
    result["outcomes"] = unique_outcomes
    
    return result


def compare_to_ground_truth(extractions: List[Dict], studies: List[Dict]) -> Dict:
    """Compare extractions to ground truth."""
    gt_lookup = {str(s['study_id']): s.get('ground_truth', {}) for s in studies}
    
    # Metadata comparison
    metadata_results = {}
    metadata_fields = [
        "study_design", "country", "health_comp", "skills_comp", 
        "savings_comp", "coaching_comp", "social_comp", "targeting_women"
    ]
    
    for field in metadata_fields:
        correct = 0
        total = 0
        for extraction in extractions:
            study_id = str(extraction["study_id"])
            gt = gt_lookup.get(study_id, {})
            if not gt:
                continue
            
            gt_val = gt.get(field)
            if gt_val is None:
                continue
            
            extracted = extraction.get("metadata", {}).get(field, {})
            ext_val = extracted.get("value") if isinstance(extracted, dict) else extracted
            
            total += 1
            if field == "study_design":
                gt_norm = "RCT" if str(gt_val).upper() == "RCT" else "Quasi-experimental"
                ext_norm = "RCT" if str(ext_val).upper() == "RCT" else "Quasi-experimental"
                if gt_norm == ext_norm:
                    correct += 1
            elif field in ["health_comp", "skills_comp", "savings_comp", "coaching_comp", 
                          "social_comp", "targeting_women"]:
                gt_bool = gt_val == 1 or gt_val == True
                ext_bool = ext_val == True or ext_val == 1 or str(ext_val).lower() in ["true", "yes", "1"]
                if gt_bool == ext_bool:
                    correct += 1
            else:
                if str(gt_val).lower().strip() == str(ext_val).lower().strip():
                    correct += 1
        
        if total > 0:
            metadata_results[field] = {"correct": correct, "total": total, "accuracy": correct / total}
    
    # Outcomes comparison
    outcome_results = {
        "total_extracted": 0,
        "total_gt": 0,
        "d_computed": 0,
        "d_errors": [],
        "category_recall": {},
        "pass_contributions": {"pass1": 0, "pass2": 0, "pass3": 0}
    }
    
    for s in studies:
        gt = s.get('ground_truth', {})
        gt_outcomes = gt.get('outcomes', [])
        outcome_results['total_gt'] += len(gt_outcomes)
    
    for extraction in extractions:
        study_id = str(extraction["study_id"])
        study_outcomes = extraction.get("outcomes", [])
        outcome_results["total_extracted"] += len(study_outcomes)
        
        gt = gt_lookup.get(study_id, {})
        gt_outcomes = gt.get('outcomes', [])
        
        for outcome in study_outcomes:
            if outcome.get("computed_d") is not None:
                outcome_results["d_computed"] += 1
                
                cat = outcome.get("outcome_category", "")
                for gt_o in gt_outcomes:
                    gt_cat = gt_o.get('category', '')
                    if gt_cat.lower() == cat.lower():
                        gt_d = gt_o.get('effect_size_d')
                        if gt_d is not None:
                            error = abs(outcome["computed_d"] - gt_d)
                            outcome_results["d_errors"].append({
                                "study_id": study_id,
                                "outcome": outcome.get("outcome_name"),
                                "computed_d": outcome["computed_d"],
                                "gt_d": gt_d,
                                "error": error,
                                "method": outcome.get("computation_method")
                            })
                            break
    
    # Category recall
    for cat in ["Income", "Assets", "Savings", "Expenditure", "Poverty"]:
        gt_count = sum(
            1 for s in studies
            for o in s.get('ground_truth', {}).get('outcomes', [])
            if o.get('category', '').lower() == cat.lower()
        )
        extracted_count = sum(
            1 for ext in extractions
            for o in ext.get("outcomes", [])
            if o.get("outcome_category", "").lower() == cat.lower()
        )
        outcome_results["category_recall"][cat] = {
            "gt": gt_count,
            "extracted": extracted_count,
            "recall": extracted_count / gt_count if gt_count > 0 else 0
        }
    
    if outcome_results["d_errors"]:
        errors = [e["error"] for e in outcome_results["d_errors"]]
        outcome_results["mean_d_error"] = np.mean(errors)
        outcome_results["median_d_error"] = np.median(errors)
    
    return {"metadata": metadata_results, "outcomes": outcome_results}


def main():
    """Run V4 multi-pass extraction."""
    print("=" * 70)
    print("EXTRACTION V4 - Multi-Pass Outcome Extraction")
    print("=" * 70)
    
    eval_path = Path(__file__).parent
    base_path = eval_path.parent
    
    with open(eval_path / "matched_studies_r2.json") as f:
        studies = json.load(f)
    print(f"\nLoaded {len(studies)} matched studies")
    
    extractions = []
    
    for i, study_data in enumerate(studies):
        study_id = study_data.get('study_id')
        print(f"\n[{i+1}/{len(studies)}] Processing {study_id}...")
        
        content = load_document_content(study_data)
        if not content:
            print(f"  Skipping - could not load content")
            continue
        
        print(f"  Content: {len(content)} chars")
        
        extraction = extract_study_v4(study_id, content)
        extractions.append(extraction)
        
        passes = extraction.get("extraction_passes", {})
        n_outcomes = len(extraction.get("outcomes", []))
        print(f"  Outcomes: {n_outcomes} (P1:{passes.get('pass1_general',0)} P2:{passes.get('pass2_tables',0)} P3:{passes.get('pass3_category',0)})")
        
        # Save incremental results
        if (i + 1) % 5 == 0:
            with open(eval_path / "v4_extraction_results_partial.json", "w") as f:
                json.dump(extractions, f, indent=2, default=str)
            print(f"  Saved partial results")
    
    # Compare to ground truth
    print("\n" + "=" * 70)
    print("COMPARING TO GROUND TRUTH")
    print("=" * 70)
    
    comparison = compare_to_ground_truth(extractions, studies)
    
    # Print summary
    print("\nMetadata Accuracy:")
    for field, stats in comparison["metadata"].items():
        print(f"  {field}: {stats['correct']}/{stats['total']} = {stats['accuracy']*100:.1f}%")
    
    oc = comparison["outcomes"]
    print(f"\nOutcomes:")
    print(f"  GT: {oc['total_gt']}")
    print(f"  Extracted: {oc['total_extracted']}")
    print(f"  Recall: {100*oc['total_extracted']/oc['total_gt']:.1f}%")
    print(f"  Cohen's d computed: {oc['d_computed']}")
    if "mean_d_error" in oc:
        print(f"  Mean d error: {oc['mean_d_error']:.4f}")
    
    print("\nCategory Recall:")
    for cat, stats in oc["category_recall"].items():
        print(f"  {cat}: {stats['extracted']}/{stats['gt']} = {stats['recall']*100:.1f}%")
    
    # Save results
    output = {
        "extractions": extractions,
        "comparison": comparison,
        "version": "v4_multipass"
    }
    
    with open(eval_path / "v4_extraction_results.json", "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nResults saved to v4_extraction_results.json")


if __name__ == "__main__":
    main()
