"""
Manual Validation Script for Stage 2 Extraction
================================================
Samples 10-20 outcomes and compares extracted values against actual table markdown.
Also attempts Cohen's d conversion when means/SDs are available.

Cohen's d formula:
  d = (M1 - M2) / SD_pooled
  
Where SD_pooled = sqrt(((n1-1)*SD1^2 + (n2-1)*SD2^2) / (n1+n2-2))

For regression coefficients without group means:
  d ≈ coefficient / SD_control  (approximation)
  d ≈ 2 * t / sqrt(df)  (from t-statistic)
"""
import json
import re
import os
import random
import boto3
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from openai import OpenAI
from dotenv import load_dotenv

# Load environment
load_dotenv(Path(__file__).parent.parent / ".env")

# ============================================================================
# Configuration
# ============================================================================

# R2 credentials (same as extractor_v17d_stage2.py)
CLOUDFLARE_ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID")
R2_ACCESS_KEY = os.getenv("R2_ACCESS_KEY_ID")
R2_SECRET_KEY = os.getenv("R2_SECRET_ACCESS_KEY")
R2_BUCKET = os.getenv("R2_BUCKET_NAME", "devchat-pdfs")

client = OpenAI()

STAGE2_PATH = Path(__file__).parent / "v17d_stage2_results.json"
GT_PATH = Path(__file__).parent.parent / "evaluation" / "matched_studies_r2.json"

# Number of outcomes to sample per study
SAMPLES_PER_STUDY = 4

# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class ValidationResult:
    study: str
    outcome_name: str
    table_source: str
    extracted_coef: Optional[float]
    extracted_se: Optional[float]
    extracted_pval: Optional[float]
    table_markdown: str
    found_in_table: bool
    value_verified: Optional[bool] = None
    cohen_d: Optional[float] = None
    gt_effect_size_d: Optional[float] = None
    notes: str = ""

# ============================================================================
# Table Loading (from R2 via boto3)
# ============================================================================

# Import preprocessing from Stage 2
from extractor_v17d_stage2 import preprocess_mineru_table

def get_r2_client():
    """Get R2 client."""
    return boto3.client(
        's3',
        endpoint_url=f'https://{CLOUDFLARE_ACCOUNT_ID}.r2.cloudflarestorage.com',
        aws_access_key_id=R2_ACCESS_KEY,
        aws_secret_access_key=R2_SECRET_KEY
    )

# Cache for loaded studies
_tables_cache: Dict[str, Dict[str, str]] = {}

def load_all_tables_for_study(r2_key: str) -> Dict[str, str]:
    """Load all tables from R2 for a study, return dict by table_id."""
    if r2_key in _tables_cache:
        return _tables_cache[r2_key]
    
    try:
        r2_client = get_r2_client()
        response = r2_client.get_object(Bucket=R2_BUCKET, Key=r2_key)
        content = response['Body'].read()
        
        try:
            data = json.loads(content.decode('utf-8'))
        except UnicodeDecodeError:
            data = json.loads(content.decode('latin-1'))
        
        raw_tables = data.get("tables", [])
        
        tables_dict = {}
        for idx, table in enumerate(raw_tables):
            parsed = preprocess_mineru_table(table)
            if parsed and len(parsed.rows) >= 2:
                table_id = f"Table {idx + 1}"
                content = parsed.to_markdown() if hasattr(parsed, 'to_markdown') else str(parsed)
                tables_dict[table_id] = content
        
        _tables_cache[r2_key] = tables_dict
        return tables_dict
        
    except Exception as e:
        print(f"Failed to load {r2_key}: {e}")
        return {}

def load_table_markdown(study_id: str, table_source: str, r2_key: str) -> Optional[str]:
    """Load specific table markdown from R2."""
    tables_dict = load_all_tables_for_study(r2_key)
    
    if not tables_dict:
        return None
    
    # Find the matching table
    for table_id, content in tables_dict.items():
        # Match "Table 3" to "Table 3" or similar
        if table_source and table_source.lower() in table_id.lower():
            return content
        # Also try numeric match
        source_num = re.search(r'\d+', table_source or "")
        table_num = re.search(r'\d+', table_id)
        if source_num and table_num and source_num.group() == table_num.group():
            return content
    
    return None

# ============================================================================
# Value Verification
# ============================================================================

def find_value_in_table(table_md: str, value: float, tolerance: float = 0.01) -> bool:
    """Check if a value exists in the table markdown."""
    if value is None:
        return False
    
    # Find all numbers in the table
    numbers = re.findall(r'[-+]?\d*\.?\d+', table_md)
    
    for num_str in numbers:
        try:
            num = float(num_str)
            if abs(num - value) <= tolerance:
                return True
            # Also check if we need to handle percentage format
            if abs(num / 100 - value) <= tolerance:
                return True
        except ValueError:
            continue
    
    return False

def find_outcome_row_in_table(table_md: str, outcome_name: str) -> Optional[str]:
    """Find the row in the table that contains the outcome."""
    lines = table_md.split('\n')
    outcome_lower = outcome_name.lower().replace('^', '').strip()
    
    for line in lines:
        line_lower = line.lower().replace('^', '').strip()
        # Check for partial match
        if outcome_lower[:20] in line_lower or line_lower[:20] in outcome_lower:
            return line
    
    return None

# ============================================================================
# Cohen's d Extraction
# ============================================================================

COHENS_D_PROMPT = """You are a statistics expert. Given this regression table, extract information needed to compute Cohen's d effect size for the specified outcome.

OUTCOME: {outcome_name}
EXTRACTED COEFFICIENT: {coefficient}
EXTRACTED SE: {standard_error}

TABLE CONTENT:
{table_markdown}

Look for:
1. Control group mean (baseline, control mean)
2. Control group SD (standard deviation of control)
3. Treatment group mean
4. Treatment group SD
5. Sample sizes (n_treatment, n_control)
6. T-statistic or degrees of freedom

Respond in JSON format:
{{
    "control_mean": <float or null>,
    "control_sd": <float or null>,
    "treatment_mean": <float or null>,
    "treatment_sd": <float or null>,
    "n_treatment": <int or null>,
    "n_control": <int or null>,
    "t_statistic": <float or null>,
    "df": <int or null>,
    "can_compute_cohens_d": <boolean>,
    "cohens_d_estimate": <float or null>,
    "computation_method": "<string explaining how d was computed or why it can't be>"
}}
"""

def extract_control_sd_from_table(table_md: str) -> Optional[float]:
    """Try to extract Control SD from table markdown using regex."""
    # Pattern: "Control SD" followed by number
    patterns = [
        r'Control\s+SD[:\s]+([0-9.]+)',
        r'SD[:\s]+([0-9.]+)',
        r'Control mean.*?([0-9.]+)\s*$',  # Last number on Control mean line might be SD
    ]
    
    # Look for "Control mean Control SD" row pattern
    lines = table_md.split('\n')
    for line in lines:
        if 'Control' in line and ('SD' in line or 'mean' in line):
            # Extract all numbers from this line
            numbers = re.findall(r'[-+]?[0-9]*\.?[0-9]+', line)
            # Usually format is: "Control mean Control SD | value1 | value2 | value3..."
            # or "Control mean | value1 | SD: value2"
            if len(numbers) >= 2:
                # Last number is often SD
                try:
                    return float(numbers[-1])
                except:
                    pass
    
    return None

def extract_cohens_d_components(
    table_md: str, 
    outcome_name: str, 
    coefficient: float, 
    se: float
) -> Dict:
    """Extract components needed for Cohen's d - using regex first, then LLM if available."""
    # Try regex extraction first (faster, no API calls)
    control_sd = extract_control_sd_from_table(table_md)
    
    if control_sd and control_sd > 0:
        cohen_d = coefficient / control_sd
        return {
            "control_sd": control_sd,
            "can_compute_cohens_d": True,
            "cohens_d_estimate": cohen_d,
            "computation_method": f"d = coef/SD_control = {coefficient}/{control_sd:.3f} = {cohen_d:.4f}"
        }
    
    # If regex fails, try LLM (may fail due to API issues)
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{
                "role": "user",
                "content": COHENS_D_PROMPT.format(
                    outcome_name=outcome_name,
                    coefficient=coefficient,
                    standard_error=se,
                    table_markdown=table_md[:4000]  # Limit context
                )
            }],
            response_format={"type": "json_object"},
            temperature=0
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        return {"error": str(e), "can_compute_cohens_d": False}

def compute_cohens_d(
    coefficient: float,
    se: float,
    control_sd: Optional[float] = None,
    t_stat: Optional[float] = None,
    n_treatment: Optional[int] = None,
    n_control: Optional[int] = None
) -> Tuple[Optional[float], str]:
    """Compute Cohen's d using available information."""
    
    # Method 1: Using control SD (most common for regression)
    if control_sd and control_sd > 0:
        d = coefficient / control_sd
        return d, f"d = coef/SD_control = {coefficient}/{control_sd}"
    
    # Method 2: Using t-statistic and sample sizes
    if t_stat and n_treatment and n_control:
        import math
        df = n_treatment + n_control - 2
        d = 2 * t_stat / math.sqrt(df)
        return d, f"d = 2*t/sqrt(df) = 2*{t_stat}/sqrt({df})"
    
    # Method 3: Approximate using SE (rough estimate)
    # d ≈ coef / (SE * sqrt(N))
    # This is a very rough approximation
    if se and se > 0 and n_treatment and n_control:
        import math
        n_total = n_treatment + n_control
        # Rough approximation: SD ≈ SE * sqrt(N)
        approx_sd = se * math.sqrt(n_total)
        d = coefficient / approx_sd
        return d, f"d ≈ coef/(SE*sqrt(N)) = {coefficient}/({se}*sqrt({n_total})) [ROUGH ESTIMATE]"
    
    return None, "Insufficient information to compute Cohen's d"

# ============================================================================
# Main Validation
# ============================================================================

def run_validation():
    """Run manual validation on sampled outcomes."""
    
    # Load data
    with open(STAGE2_PATH) as f:
        stage2_results = json.load(f)
    
    with open(GT_PATH) as f:
        gt_studies = json.load(f)
    
    # Build GT lookup with r2_key
    gt_lookup = {}
    r2_key_lookup = {}
    for study in gt_studies:
        study_id = study["study_id"]
        r2_key_lookup[study_id] = study.get("r2_key", "")
        gt_data = study.get("ground_truth", {})
        gt_lookup[study_id] = {
            "outcomes": {o["name"].lower(): o for o in gt_data.get("outcomes", [])}
        }
    
    print("=" * 80)
    print("MANUAL VALIDATION: Stage 2 Extraction")
    print("=" * 80)
    print(f"\nSampling {SAMPLES_PER_STUDY} outcomes per study...")
    
    all_validations = []
    
    for study in stage2_results["studies"]:
        study_id = study["study_id"]
        author = study["author"]
        r2_key = r2_key_lookup.get(study_id, "")
        
        print(f"\n{'='*60}")
        print(f"STUDY: {author} (ID: {study_id})")
        print(f"R2 Key: {r2_key[:50]}...")
        print("=" * 60)
        
        if not r2_key:
            print("  No R2 key found - skipping")
            continue
        
        # Pre-load all tables for this study
        tables_dict = load_all_tables_for_study(r2_key)
        print(f"  Loaded {len(tables_dict)} tables")
        
        # Filter outcomes with coefficients from tables
        table_outcomes = [
            o for o in study["enriched_outcomes"]
            if o.get("coefficient") is not None and o.get("table_source")
        ]
        
        if not table_outcomes:
            print("  No table outcomes with coefficients")
            continue
        
        # Sample outcomes
        n_samples = min(SAMPLES_PER_STUDY, len(table_outcomes))
        sampled = random.sample(table_outcomes, n_samples)
        
        for i, outcome in enumerate(sampled, 1):
            outcome_name = outcome["outcome_name"]
            table_source = outcome["table_source"]
            coef = outcome.get("coefficient")
            se = outcome.get("standard_error")
            pval = outcome.get("p_value")
            
            print(f"\n  [{i}/{n_samples}] {outcome_name[:50]}...")
            print(f"      Table: {table_source}")
            print(f"      Extracted: coef={coef}, SE={se}, p={pval}")
            
            # Load table from cached dict
            table_md = load_table_markdown(study_id, table_source, r2_key)
            
            if not table_md:
                print("      ⚠️  Could not load table markdown")
                all_validations.append(ValidationResult(
                    study=author,
                    outcome_name=outcome_name,
                    table_source=table_source,
                    extracted_coef=coef,
                    extracted_se=se,
                    extracted_pval=pval,
                    table_markdown="",
                    found_in_table=False,
                    notes="Table not found"
                ))
                continue
            
            # Verify value in table
            coef_found = find_value_in_table(table_md, coef) if coef else False
            se_found = find_value_in_table(table_md, se) if se else False
            row = find_outcome_row_in_table(table_md, outcome_name)
            
            print(f"      Coef in table: {'✅' if coef_found else '❌'}")
            print(f"      SE in table: {'✅' if se_found else '❌'}")
            if row:
                print(f"      Row found: {row[:80]}...")
            
            # Try to compute Cohen's d
            cohen_d = None
            d_notes = ""
            if coef and table_md:
                d_components = extract_cohens_d_components(table_md, outcome_name, coef, se or 0)
                
                if d_components.get("can_compute_cohens_d"):
                    cohen_d = d_components.get("cohens_d_estimate")
                    d_notes = d_components.get("computation_method", "")
                else:
                    # Try our own computation
                    cohen_d, d_notes = compute_cohens_d(
                        coef, se,
                        control_sd=d_components.get("control_sd"),
                        t_stat=d_components.get("t_statistic"),
                        n_treatment=d_components.get("n_treatment"),
                        n_control=d_components.get("n_control")
                    )
                
                if cohen_d:
                    print(f"      Cohen's d: {cohen_d:.4f}")
                    print(f"      Method: {d_notes}")
            
            # Check against GT
            gt_effect = None
            gt_outcomes = gt_lookup.get(study_id, {}).get("outcomes", {})
            outcome_lower = outcome_name.lower().strip()
            if outcome_lower in gt_outcomes:
                gt_effect = gt_outcomes[outcome_lower].get("effect_size_d")
                if gt_effect:
                    print(f"      GT effect_size_d: {gt_effect:.4f}")
                    if cohen_d:
                        diff = abs(cohen_d - gt_effect)
                        print(f"      Difference: {diff:.4f} ({'CLOSE' if diff < 0.1 else 'LARGE'})")
            
            all_validations.append(ValidationResult(
                study=author,
                outcome_name=outcome_name,
                table_source=table_source,
                extracted_coef=coef,
                extracted_se=se,
                extracted_pval=pval,
                table_markdown=table_md[:500] if table_md else "",
                found_in_table=coef_found,
                value_verified=coef_found and (se_found or se is None),
                cohen_d=cohen_d,
                gt_effect_size_d=gt_effect,
                notes=d_notes
            ))
    
    # Summary
    print("\n" + "=" * 80)
    print("VALIDATION SUMMARY")
    print("=" * 80)
    
    n_total = len(all_validations)
    n_coef_verified = sum(1 for v in all_validations if v.found_in_table)
    n_with_cohen_d = sum(1 for v in all_validations if v.cohen_d is not None)
    n_with_gt = sum(1 for v in all_validations if v.gt_effect_size_d is not None)
    
    print(f"\nTotal sampled: {n_total}")
    print(f"Coefficients verified in table: {n_coef_verified} ({100*n_coef_verified/n_total:.1f}%)")
    print(f"Cohen's d computed: {n_with_cohen_d} ({100*n_with_cohen_d/n_total:.1f}%)")
    print(f"With GT comparison: {n_with_gt}")
    
    # Save detailed results
    output_path = Path(__file__).parent / "stage2_validation_results.json"
    results = {
        "summary": {
            "n_sampled": n_total,
            "n_coef_verified": n_coef_verified,
            "verification_rate": n_coef_verified / n_total if n_total else 0,
            "n_with_cohen_d": n_with_cohen_d,
            "n_with_gt_comparison": n_with_gt
        },
        "validations": [
            {
                "study": v.study,
                "outcome_name": v.outcome_name,
                "table_source": v.table_source,
                "extracted_coef": v.extracted_coef,
                "extracted_se": v.extracted_se,
                "found_in_table": v.found_in_table,
                "cohen_d": v.cohen_d,
                "gt_effect_size_d": v.gt_effect_size_d,
                "notes": v.notes
            }
            for v in all_validations
        ]
    }
    
    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\nDetailed results saved to: {output_path}")
    
    # Show sample table for verification
    print("\n" + "=" * 80)
    print("SAMPLE TABLE CONTENT (for manual review)")
    print("=" * 80)
    
    for v in all_validations[:2]:
        if v.table_markdown:
            print(f"\n--- {v.outcome_name[:40]} ---")
            print(f"Extracted coef: {v.extracted_coef}")
            print(f"Table excerpt:\n{v.table_markdown}")


if __name__ == "__main__":
    run_validation()
