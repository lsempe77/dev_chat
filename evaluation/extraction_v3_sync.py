"""
Extraction V3 - Synchronous version (no asyncio)

Simple synchronous extraction using requests library to avoid asyncio cancellation issues.
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
# VERIFIED COHEN'S D FORMULA
# From reverse engineering: d = (coef/se) * sqrt(1/n1 + 1/n2)
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
    """
    Compute Cohen's d using the verified formula.
    Returns (d, method_used) tuple.
    """
    # Method 1: From coefficient/SE with n_treatment and n_control (most accurate)
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
    
    # Method 4: From means and SDs (classical formula)
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


def fix_json_string(s: str) -> str:
    """Fix common JSON issues from LLM output."""
    # Remove control characters that break JSON
    s = re.sub(r'[\x00-\x1f\x7f-\x9f]', ' ', s)
    # Fix unescaped quotes inside strings (common in evidence quotes)
    # This is a simplified fix - replace problematic patterns
    s = s.replace('\\"', '"').replace('"', '\\"')  # Reset escaping
    # Now properly escape only the quotes that should be escaped
    # Actually, let's try a different approach - just clean the evidence fields
    return s


def robust_json_parse(content: str) -> Dict:
    """Parse JSON with multiple fallback strategies."""
    # Strategy 1: Direct parse
    json_match = re.search(r'\{[\s\S]*\}', content)
    if not json_match:
        return {}
    
    json_str = json_match.group()
    
    # Try direct parse first
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        pass
    
    # Strategy 2: Remove control characters and retry
    cleaned = re.sub(r'[\x00-\x1f\x7f-\x9f]', ' ', json_str)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    
    # Strategy 3: Fix common issues - newlines in strings
    # Replace actual newlines in string values with spaces
    fixed = re.sub(r'(?<=["\'])\s*\n\s*(?=[^"\']*["\'])', ' ', cleaned)
    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass
    
    # Strategy 4: Try to extract fields individually using regex
    result = {}
    # Pattern for "field": {"value": X, "confidence": Y, "evidence": "Z"}
    field_pattern = r'"(\w+)":\s*\{\s*"value":\s*([^,}]+),\s*"confidence":\s*([\d.]+)(?:,\s*"evidence":\s*"([^"]*)")?\s*\}'
    for match in re.finditer(field_pattern, cleaned):
        field_name = match.group(1)
        value_str = match.group(2).strip()
        confidence = float(match.group(3))
        evidence = match.group(4) or ""
        
        # Parse value
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
    
    if result:
        return result
    
    # Strategy 5: Last resort - try with ast.literal_eval after converting to Python dict format
    try:
        import ast
        # Convert JSON booleans to Python
        py_str = cleaned.replace('true', 'True').replace('false', 'False').replace('null', 'None')
        return ast.literal_eval(py_str)
    except:
        pass
    
    return {}


def call_llm(prompt: str, max_tokens: int = 4096, retries: int = 3) -> Dict:
    """Call OpenRouter API with Claude 3.5 Sonnet (synchronous)."""
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
                timeout=300,  # 5 minute timeout
                stream=False  # Disable streaming to avoid chunked encoding issues
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            
            # Use robust JSON parsing
            result = robust_json_parse(content)
            if result:
                return result
            
            # If parsing failed, retry with slightly different prompt
            if attempt < retries - 1:
                print(f"    Retry {attempt + 1}/{retries} after JSON parse failure")
                time.sleep(2)
                continue
            return {}
        except Exception as e:
            if attempt < retries - 1:
                print(f"    Retry {attempt + 1}/{retries} after error: {str(e)[:100]}")
                time.sleep(5 * (attempt + 1))  # Exponential backoff
            else:
                print(f"    Failed after {retries} attempts: {str(e)[:100]}")
                return {}


def load_document_content(study_data: Dict) -> Optional[str]:
    """Load markdown content from R2."""
    try:
        r2_key = study_data.get('r2_key')
        if not r2_key:
            print(f"    No R2 key found")
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
        
        # Try UTF-8 first, then latin-1
        try:
            return content.decode('utf-8')
        except UnicodeDecodeError:
            return content.decode('latin-1')
    except Exception as e:
        print(f"    Error loading document: {e}")
        return None


# ============================================================================
# EXTRACTION PROMPTS
# ============================================================================

METADATA_PROMPT = """You are extracting metadata from an academic study on poverty/development interventions.

DOCUMENT:
{content}

Extract these fields with EVIDENCE QUOTES from the document:

1. study_design: "RCT" or "Quasi-experimental" 
2. country: Country where study was conducted
3. year: Publication year
4. author: First author's last name
5. program_name: Name of the intervention/program
6. targeting_women: true/false - does the program specifically target women?

7-13. INTERVENTION COMPONENTS (true/false for each):
- consumption_support: Cash/food transfers, consumption smoothing support
- health_comp: Health services, healthcare, nutrition, health education
- asset_transfer: Livestock, equipment, productive assets given
- skills_comp: Training, vocational skills, business training
- savings_comp: Savings groups, financial literacy, bank accounts
- coaching_comp: Mentoring, life skills, psychosocial support
- social_comp: Social networks, community groups, collective action

For EACH field, provide:
- value: The extracted value
- confidence: 0.0-1.0 (how confident you are)
- evidence: A SHORT quote from the document supporting this

Return JSON:
{{
  "study_design": {{"value": "RCT", "confidence": 0.95, "evidence": "randomized..."}},
  "country": {{"value": "Bangladesh", "confidence": 0.99, "evidence": "conducted in..."}},
  "year": {{"value": 2015, "confidence": 0.99, "evidence": ""}},
  "author": {{"value": "Bandiera", "confidence": 0.99, "evidence": ""}},
  "program_name": {{"value": "BRAC Ultra-Poor", "confidence": 0.9, "evidence": "..."}},
  "targeting_women": {{"value": true, "confidence": 0.9, "evidence": "women-only..."}},
  "consumption_support": {{"value": true, "confidence": 0.8, "evidence": "cash transfer..."}},
  "health_comp": {{"value": false, "confidence": 0.7, "evidence": "no health..."}},
  "asset_transfer": {{"value": true, "confidence": 0.95, "evidence": "livestock given..."}},
  "skills_comp": {{"value": true, "confidence": 0.85, "evidence": "training provided..."}},
  "savings_comp": {{"value": false, "confidence": 0.6, "evidence": ""}},
  "coaching_comp": {{"value": true, "confidence": 0.8, "evidence": "mentoring..."}},
  "social_comp": {{"value": false, "confidence": 0.7, "evidence": ""}}
}}
"""

OUTCOMES_PROMPT = """You are extracting OUTCOME STATISTICS from an academic study.

DOCUMENT:
{content}

Find ALL outcomes in these categories:
- Income: earnings, wages, profits, revenue
- Assets: wealth, asset value, savings balance
- Savings: formal savings, informal savings
- Expenditure: consumption, spending
- Poverty: poverty status, food security

For EACH outcome, extract RAW STATISTICS (we compute Cohen's d ourselves):

- outcome_name: Specific outcome name
- outcome_category: Income, Assets, Savings, Expenditure, or Poverty
- coefficient: Treatment effect coefficient
- standard_error: SE of the coefficient
- t_statistic: t-stat if available
- n_treatment: Sample size in treatment group
- n_control: Sample size in control group
- n_total: Total sample size (if treatment/control not separate)
- mean_treatment: Mean in treatment group
- mean_control: Mean in control group
- sd_treatment: SD in treatment group
- sd_control: SD in control group
- evidence_table: Which table/figure this came from
- confidence: 0.0-1.0 how confident you are in these values

Return JSON with an array of outcomes:
{{
  "outcomes": [
    {{
      "outcome_name": "Monthly income",
      "outcome_category": "Income",
      "coefficient": 125.5,
      "standard_error": 45.2,
      "t_statistic": null,
      "n_treatment": 500,
      "n_control": 500,
      "n_total": null,
      "mean_treatment": null,
      "mean_control": null,
      "sd_treatment": null,
      "sd_control": null,
      "evidence_table": "Table 3",
      "confidence": 0.85
    }}
  ]
}}

Extract ALL outcomes you can find. If a statistic is not available, use null.
"""


def extract_study(study_id: str, content: str) -> Dict:
    """Extract all data from a study."""
    # NO TRUNCATION - use full paper to capture results tables at end
    # max_chars = 50000  # Reduced from 100K
    # if len(content) > max_chars:
    #     content = content[:max_chars] + "\n\n[TRUNCATED]"
    
    result = {
        "study_id": study_id,
        "metadata": {},
        "outcomes": [],
        "extraction_timestamp": datetime.now().isoformat()
    }
    
    # Extract metadata
    print(f"    Extracting metadata...")
    metadata_result = call_llm(METADATA_PROMPT.format(content=content))
    if metadata_result:
        result["metadata"] = metadata_result
    
    # Small delay between calls
    time.sleep(1)
    
    # Extract outcomes
    print(f"    Extracting outcomes...")
    outcomes_result = call_llm(OUTCOMES_PROMPT.format(content=content))
    if outcomes_result and "outcomes" in outcomes_result:
        # Compute Cohen's d for each outcome
        for outcome in outcomes_result["outcomes"]:
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
        result["outcomes"] = outcomes_result["outcomes"]
    
    return result


def compare_to_ground_truth(extractions: List[Dict], studies: List[Dict], outcomes_gt: pd.DataFrame) -> Dict:
    """Compare extractions to ground truth using the matched_studies data."""
    
    # Create study lookup
    gt_lookup = {str(s['study_id']): s.get('ground_truth', {}) for s in studies}
    
    # Metadata comparison
    metadata_results = {}
    metadata_fields = [
        "study_design", "country", "consumption_support", "health_comp",
        "asset_transfer", "skills_comp", "savings_comp", "coaching_comp",
        "social_comp", "targeting_women"
    ]
    
    for field in metadata_fields:
        correct = 0
        total = 0
        for extraction in extractions:
            study_id = str(extraction["study_id"])
            
            # Find ground truth
            gt = gt_lookup.get(study_id, {})
            if not gt:
                continue
            
            # Map field names from extraction to GT
            gt_field_map = {
                "study_design": "study_design",
                "country": "country",
                "consumption_support": "consumption_support",
                "health_comp": "health_comp",
                "asset_transfer": "asset_transfer",
                "skills_comp": "skills_comp",
                "savings_comp": "savings_comp",
                "coaching_comp": "coaching_comp",
                "social_comp": "social_comp",
                "targeting_women": "targeting_women"
            }
            gt_field = gt_field_map.get(field, field)
            gt_val = gt.get(gt_field)
            
            if gt_val is None:
                continue
            
            extracted = extraction.get("metadata", {}).get(field, {})
            ext_val = extracted.get("value") if isinstance(extracted, dict) else extracted
            
            # Compare
            total += 1
            if field == "study_design":
                # Normalize
                gt_norm = "RCT" if str(gt_val).upper() == "RCT" else "Quasi-experimental"
                ext_norm = "RCT" if str(ext_val).upper() == "RCT" else "Quasi-experimental"
                if gt_norm == ext_norm:
                    correct += 1
            elif field in ["consumption_support", "health_comp", "asset_transfer", "skills_comp", 
                          "savings_comp", "coaching_comp", "social_comp", "targeting_women"]:
                # Binary comparison
                gt_bool = gt_val == 1 or gt_val == True or str(gt_val).lower() in ["true", "yes", "1"]
                ext_bool = ext_val == True or ext_val == 1 or str(ext_val).lower() in ["true", "yes", "1"]
                if gt_bool == ext_bool:
                    correct += 1
            else:
                # String comparison (case insensitive)
                if str(gt_val).lower().strip() == str(ext_val).lower().strip():
                    correct += 1
        
        if total > 0:
            metadata_results[field] = {"correct": correct, "total": total, "accuracy": correct / total}
    
    # Outcomes comparison - use GT from matched_studies
    outcome_results = {
        "total_extracted": 0,
        "total_gt": 0,
        "d_computed": 0,
        "d_errors": [],
        "category_recall": {}
    }
    
    # Count GT outcomes
    for s in studies:
        gt = s.get('ground_truth', {})
        gt_outcomes = gt.get('outcomes', [])
        outcome_results['total_gt'] += len(gt_outcomes)
    
    for extraction in extractions:
        study_id = str(extraction["study_id"])
        study_outcomes = extraction.get("outcomes", [])
        outcome_results["total_extracted"] += len(study_outcomes)
        
        # Get GT outcomes
        gt = gt_lookup.get(study_id, {})
        gt_outcomes = gt.get('outcomes', [])
        
        for outcome in study_outcomes:
            if outcome.get("computed_d") is not None:
                outcome_results["d_computed"] += 1
                
                # Try to match to GT by category
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
    
    # Calculate summary stats
    if outcome_results["d_errors"]:
        errors = [e["error"] for e in outcome_results["d_errors"]]
        outcome_results["mean_d_error"] = np.mean(errors)
        outcome_results["median_d_error"] = np.median(errors)
        outcome_results["max_d_error"] = np.max(errors)
    
    return {
        "metadata": metadata_results,
        "outcomes": outcome_results
    }


def generate_report(extractions: List[Dict], comparison: Dict) -> str:
    """Generate markdown report."""
    report = []
    report.append("# V3 Extraction Evaluation Report")
    report.append(f"\nGenerated: {datetime.now().isoformat()}")
    report.append(f"\nStudies processed: {len(extractions)}")
    
    # Metadata summary
    report.append("\n## Metadata Accuracy")
    report.append("\n| Field | Correct | Total | Accuracy |")
    report.append("|-------|---------|-------|----------|")
    
    for field, stats in comparison["metadata"].items():
        acc_pct = stats["accuracy"] * 100
        report.append(f"| {field} | {stats['correct']} | {stats['total']} | {acc_pct:.1f}% |")
    
    # Overall metadata accuracy
    total_correct = sum(s["correct"] for s in comparison["metadata"].values())
    total_all = sum(s["total"] for s in comparison["metadata"].values())
    if total_all > 0:
        report.append(f"\n**Overall Metadata Accuracy: {total_correct}/{total_all} = {100*total_correct/total_all:.1f}%**")
    
    # Outcomes summary
    report.append("\n## Outcomes Extraction")
    oc = comparison["outcomes"]
    report.append(f"\n- Ground truth outcomes: {oc['total_gt']}")
    report.append(f"- Extracted outcomes: {oc['total_extracted']}")
    report.append(f"- Cohen's d computed: {oc['d_computed']}")
    
    if "mean_d_error" in oc:
        report.append(f"\n### Cohen's d Accuracy")
        report.append(f"- Mean absolute error: {oc['mean_d_error']:.4f}")
        report.append(f"- Median absolute error: {oc['median_d_error']:.4f}")
        report.append(f"- Max absolute error: {oc['max_d_error']:.4f}")
    
    # Category recall
    report.append("\n### Category Recall")
    report.append("\n| Category | GT Count | Extracted | Recall |")
    report.append("|----------|----------|-----------|--------|")
    for cat, stats in oc["category_recall"].items():
        report.append(f"| {cat} | {stats['gt']} | {stats['extracted']} | {stats['recall']*100:.1f}% |")
    
    # Per-study details
    report.append("\n## Per-Study Details")
    for ext in extractions[:10]:  # First 10 studies
        report.append(f"\n### Study: {ext['study_id']}")
        
        # Metadata
        meta = ext.get("metadata", {})
        report.append("\n**Metadata:**")
        for field in ["study_design", "country", "program_name"]:
            if field in meta:
                val = meta[field].get("value") if isinstance(meta[field], dict) else meta[field]
                conf = meta[field].get("confidence", "?") if isinstance(meta[field], dict) else "?"
                report.append(f"- {field}: {val} (conf: {conf})")
        
        # Components
        report.append("\n**Components:**")
        for comp in ["consumption_support", "health_comp", "asset_transfer", "skills_comp", 
                    "savings_comp", "coaching_comp", "social_comp"]:
            if comp in meta:
                val = meta[comp].get("value") if isinstance(meta[comp], dict) else meta[comp]
                conf = meta[comp].get("confidence", "?") if isinstance(meta[comp], dict) else "?"
                evidence = meta[comp].get("evidence", "")[:50] if isinstance(meta[comp], dict) else ""
                report.append(f"- {comp}: {val} (conf: {conf}) - {evidence}...")
        
        # Outcomes
        outcomes = ext.get("outcomes", [])
        report.append(f"\n**Outcomes: {len(outcomes)} extracted**")
        for o in outcomes[:5]:
            d = o.get("computed_d")
            d_str = f"d={d:.4f}" if d is not None else "d=N/A"
            report.append(f"- {o.get('outcome_category')}: {o.get('outcome_name')} ({d_str}, method={o.get('computation_method')})")
    
    return "\n".join(report)


def main():
    """Run V3 extraction."""
    print("=" * 80)
    print("EXTRACTION V3 - Synchronous Version")
    print("=" * 80)
    
    # Load matched studies
    base_path = Path(__file__).parent.parent
    eval_path = Path(__file__).parent
    with open(eval_path / "matched_studies_r2.json") as f:
        studies = json.load(f)  # Already a list
    print(f"\nLoaded {len(studies)} matched studies")
    
    # Load ground truth
    print("Loading ground truth...")
    outcomes_gt_path = base_path / "8WR QEX Combined.xlsx"  # In root directory
    try:
        outcomes_gt = pd.read_excel(outcomes_gt_path)
        print(f"  Outcomes GT: {len(outcomes_gt)} rows")
    except Exception as e:
        print(f"  Error loading outcomes GT: {e}")
        outcomes_gt = pd.DataFrame()
    
    # Try to load metadata GT
    metadata_gt_path = base_path / "data/metadata.csv"
    try:
        try:
            metadata_gt = pd.read_csv(metadata_gt_path, encoding='utf-8')
        except UnicodeDecodeError:
            metadata_gt = pd.read_csv(metadata_gt_path, encoding='latin-1')
        print(f"  Metadata GT: {len(metadata_gt)} rows")
    except Exception as e:
        print(f"  Error loading metadata GT: {e}")
        metadata_gt = pd.DataFrame()
    
    # Process studies
    extractions = []
    
    for i, study_data in enumerate(studies):
        study_id = study_data.get('study_id')
        print(f"\n[{i+1}/{len(studies)}] Processing {study_id}...")
        
        # Load document
        content = load_document_content(study_data)
        if not content:
            print(f"  Skipping - could not load content")
            continue
        
        print(f"  Content loaded: {len(content)} chars")
        
        # Extract
        extraction = extract_study(study_id, content)
        extractions.append(extraction)
        
        # Brief summary
        n_outcomes = len(extraction.get("outcomes", []))
        meta = extraction.get("metadata", {})
        design = meta.get("study_design", {})
        design_val = design.get("value") if isinstance(design, dict) else design
        print(f"  Extracted: design={design_val}, {n_outcomes} outcomes")
        
        # Save incremental results every 5 studies
        if (i + 1) % 5 == 0:
            with open(base_path / "evaluation/v3_extraction_results_partial.json", "w") as f:
                json.dump(extractions, f, indent=2, default=str)
            print(f"  Saved partial results ({len(extractions)} studies)")
    
    # Compare to ground truth
    print("\n" + "=" * 80)
    print("COMPARING TO GROUND TRUTH")
    print("=" * 80)
    
    comparison = compare_to_ground_truth(extractions, studies, outcomes_gt)
    
    # Print summary
    print("\nMetadata Accuracy:")
    for field, stats in comparison["metadata"].items():
        print(f"  {field}: {stats['correct']}/{stats['total']} = {stats['accuracy']*100:.1f}%")
    
    oc = comparison["outcomes"]
    print(f"\nOutcomes:")
    print(f"  Extracted: {oc['total_extracted']} / GT: {oc['total_gt']}")
    print(f"  Cohen's d computed: {oc['d_computed']}")
    if "mean_d_error" in oc:
        print(f"  Mean d error: {oc['mean_d_error']:.4f}")
    
    # Save results
    output_path = base_path / "evaluation/v3_extraction_results.json"
    with open(output_path, "w") as f:
        json.dump({
            "extractions": extractions,
            "comparison": comparison
        }, f, indent=2, default=str)
    print(f"\nResults saved to {output_path}")
    
    # Generate report
    report = generate_report(extractions, comparison)
    report_path = base_path / "evaluation/v3_extraction_report.md"
    with open(report_path, "w") as f:
        f.write(report)
    print(f"Report saved to {report_path}")


if __name__ == "__main__":
    main()
