"""
Extraction V4 FIXED - Simplified Multi-Pass Extraction

FIXES from original V4:
1. Fixed model name (was using invalid "claude-sonnet-4-20250514")
2. Use full paper content (results can be anywhere)
3. Simplified to 2 passes instead of 6 to avoid timeouts
4. Better error handling

Strategy:
- Pass 1: Metadata (first 30K chars - study design is in abstract/intro)
- Pass 2: All outcomes (full paper content)
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
MODEL = "anthropic/claude-3.5-sonnet"  # Correct model name
CLOUDFLARE_ACCOUNT_ID = os.environ.get('CLOUDFLARE_ACCOUNT_ID')
R2_ACCESS_KEY = os.environ.get('R2_ACCESS_KEY_ID')
R2_SECRET_KEY = os.environ.get('R2_SECRET_ACCESS_KEY')


def compute_cohens_d(
    coef: Optional[float] = None,
    se: Optional[float] = None,
    t_stat: Optional[float] = None,
    n_treatment: Optional[int] = None,
    n_control: Optional[int] = None,
    n_total: Optional[int] = None
) -> Tuple[Optional[float], str]:
    """Compute Cohen's d using verified formula."""
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
    
    return None, "insufficient_data"


def robust_json_parse(content: str) -> Dict:
    """Parse JSON with fallback strategies."""
    json_match = re.search(r'\{[\s\S]*\}', content)
    if not json_match:
        return {}
    
    json_str = json_match.group()
    
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
    
    return {}


SESSION = requests.Session()
SESSION.headers.update({
    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
    "Content-Type": "application/json"
})


def call_llm(prompt: str, max_tokens: int = 4096, retries: int = 3) -> Dict:
    """Call OpenRouter API with retries."""
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
                print(f"    400 Error (content too large)")
                return {}
            if attempt < retries - 1:
                print(f"    Retry {attempt + 1}/{retries}: {str(e)[:80]}")
                time.sleep(5 * (attempt + 1))
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
# PROMPTS
# ============================================================================

METADATA_PROMPT = """Extract metadata from this academic study.

DOCUMENT:
{content}

Extract:
1. study_design: "RCT" or "Quasi-experimental"
2. country: Where study was conducted
3. year: Publication year
4. program_name: Intervention/program name

INTERVENTION COMPONENTS (true/false):
- consumption_support: Cash/food transfers
- health_comp: Health services
- asset_transfer: Livestock/equipment given
- skills_comp: Training, vocational skills
- savings_comp: Savings groups, financial literacy
- coaching_comp: Mentoring, life skills
- social_comp: Social networks, community groups
- targeting_women: Specifically targets women

Return JSON with value and confidence for each field.
"""

OUTCOMES_PROMPT = """Extract ALL quantitative outcomes from this study.

DOCUMENT:
{content}

Find ALL outcomes in these categories:
- INCOME: earnings, wages, profits, revenue
- ASSETS: wealth, asset value, livestock value
- SAVINGS: formal/informal savings
- EXPENDITURE: consumption, spending
- POVERTY: poverty status, food security

For EACH outcome extract:
- outcome_name: Specific name
- outcome_category: Income, Assets, Savings, Expenditure, or Poverty  
- coefficient: Treatment effect (number)
- standard_error: SE of coefficient
- n_treatment: Treatment sample size
- n_control: Control sample size
- n_total: Total sample if not split
- table_reference: Which table (e.g., "Table 3")

Return JSON:
{{"outcomes": [{{"outcome_name": "...", "outcome_category": "...", "coefficient": ..., ...}}]}}

IMPORTANT: Extract EVERY outcome you can find. Do not skip any.
"""


def deduplicate_outcomes(outcomes: List[Dict]) -> List[Dict]:
    """Deduplicate outcomes by name and coefficient similarity."""
    if not outcomes:
        return []
    
    unique = []
    
    for o in outcomes:
        name = o.get('outcome_name', '').lower().strip()
        cat = o.get('outcome_category', '').lower()
        coef = o.get('coefficient')
        
        name_words = set(re.findall(r'\w+', name))
        
        is_duplicate = False
        for existing in unique:
            existing_name = existing.get('outcome_name', '').lower().strip()
            existing_words = set(re.findall(r'\w+', existing_name))
            existing_cat = existing.get('outcome_category', '').lower()
            existing_coef = existing.get('coefficient')
            
            if cat != existing_cat:
                continue
            
            if coef is not None and existing_coef is not None:
                if abs(coef - existing_coef) > 0.001:
                    continue
            
            if name_words and existing_words:
                overlap = len(name_words & existing_words) / max(len(name_words), len(existing_words))
                if overlap > 0.5:
                    is_duplicate = True
                    break
        
        if not is_duplicate:
            unique.append(o)
    
    return unique


def extract_study_v4(study_id: str, content: str) -> Dict:
    """Simplified 2-pass extraction."""
    
    result = {
        "study_id": study_id,
        "metadata": {},
        "outcomes": [],
        "extraction_method": "v4_fixed",
        "extraction_timestamp": datetime.now().isoformat()
    }
    
    # Pass 1: Metadata (first 30K - study design is in abstract/intro)
    print(f"    [1/2] Extracting metadata...")
    metadata_content = content[:30000]
    metadata_result = call_llm(METADATA_PROMPT.format(content=metadata_content))
    if metadata_result:
        result["metadata"] = metadata_result
    
    time.sleep(1)
    
    # Pass 2: All outcomes (FULL content)
    print(f"    [2/2] Extracting outcomes (full paper: {len(content):,} chars)...")
    outcomes_result = call_llm(OUTCOMES_PROMPT.format(content=content), max_tokens=8192)
    
    outcomes = outcomes_result.get("outcomes", [])
    print(f"          → Found {len(outcomes)} outcomes")
    
    # Deduplicate
    unique_outcomes = deduplicate_outcomes(outcomes)
    print(f"          → After dedup: {len(unique_outcomes)} outcomes")
    
    # Compute Cohen's d
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


def main():
    """Run V4 fixed extraction on all studies."""
    print("=" * 70)
    print("V4 FIXED - Simplified Multi-Pass Extraction")
    print("=" * 70)
    
    # Load matched studies
    with open("evaluation/matched_studies_r2.json") as f:
        studies = json.load(f)
    
    print(f"Loaded {len(studies)} matched studies\n")
    
    extractions = []
    
    for i, study in enumerate(studies):
        study_id = study.get('study_id', f'study_{i}')
        print(f"[{i+1}/{len(studies)}] Processing {study_id}...")
        
        content = load_document_content(study)
        if not content:
            print(f"    SKIP: No content")
            continue
        
        print(f"    Content: {len(content):,} chars")
        
        result = extract_study_v4(study_id, content)
        extractions.append(result)
        
        # Save progress after each study
        if (i + 1) % 5 == 0:
            with open("evaluation/v4_extraction_results_partial.json", "w") as f:
                json.dump(extractions, f, indent=2, default=str)
            print(f"    [Saved progress: {i+1} studies]")
    
    # Save final results
    output = {
        "version": "v4_fixed",
        "timestamp": datetime.now().isoformat(),
        "n_studies": len(extractions),
        "total_outcomes": sum(len(e['outcomes']) for e in extractions),
        "extractions": extractions
    }
    
    with open("evaluation/v4_extraction_results.json", "w") as f:
        json.dump(output, f, indent=2, default=str)
    
    print(f"\n{'='*70}")
    print(f"DONE: {len(extractions)} studies, {output['total_outcomes']} outcomes")
    print(f"Results saved to evaluation/v4_extraction_results.json")
    print("="*70)


if __name__ == "__main__":
    main()
