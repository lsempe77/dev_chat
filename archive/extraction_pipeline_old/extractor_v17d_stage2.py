"""
Extraction Pipeline V17d Stage 2 - Statistical Parameter Extraction

Stage 1 (V17d): Achieved 100% recall for outcome identification
Stage 2 (this): Extract effect_size, standard_error, CI for each matched outcome

This script:
1. Loads V17d results (matched outcomes with table_source)
2. For each matched outcome, extracts coefficient/effect_size, SE, CI from the table
3. Outputs enriched results with full statistical parameters
"""

import os
import re
import json
import boto3
import requests
import numpy as np
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime
from dotenv import load_dotenv
import time
import logging
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# Local imports
from preprocess import preprocess_mineru_table, ParsedTable

load_dotenv()

# ============================================================================
# CONFIGURATION
# ============================================================================

OPENROUTER_API_KEY = os.environ.get('OPENROUTER_API_KEY')
CLOUDFLARE_ACCOUNT_ID = os.environ.get('CLOUDFLARE_ACCOUNT_ID')
R2_ACCESS_KEY = os.environ.get('R2_ACCESS_KEY_ID')
R2_SECRET_KEY = os.environ.get('R2_SECRET_ACCESS_KEY')
R2_BUCKET = os.environ.get('R2_BUCKET_NAME', 'devchat-pdfs')

SESSION = requests.Session()
SESSION.headers.update({
    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
    "Content-Type": "application/json"
})

# ============================================================================
# LOGGING
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

# ============================================================================
# EXTRACTION PROMPT FOR STATISTICAL PARAMETERS
# ============================================================================

STATS_EXTRACTION_PROMPT = """You are an expert at extracting statistical parameters from academic regression tables.

TASK: Extract the main treatment effect coefficient and its statistics for the specified outcome variable.

OUTCOME TO FIND: "{outcome_name}"
TABLE SOURCE: {table_source}

EXTRACTION RULES:
1. Find the row matching the outcome name (may have slight variations)
2. Extract the MAIN treatment effect coefficient (usually the first column or "Treatment" column)
3. Look for:
   - coefficient: The point estimate (the main number, NOT in parentheses)
   - standard_error: Usually in parentheses below the coefficient
   - p_value: May be indicated by asterisks (* p<0.1, ** p<0.05, *** p<0.01)
   - confidence_interval_lower / confidence_interval_upper: If shown as [low, high] or (low, high)
   - sample_size: N or Observations

IMPORTANT:
- The coefficient is the main number (effect size)
- Standard errors are typically in parentheses BELOW the coefficient
- Asterisks indicate significance: * p<0.1, ** p<0.05, *** p<0.01
- Return null for any value not found

RESPONSE FORMAT (JSON only):
```json
{{
  "outcome_found": true/false,
  "outcome_name_in_table": "exact name as shown in table",
  "coefficient": 0.123,
  "standard_error": 0.045,
  "p_value": 0.05,
  "significance_stars": "**",
  "confidence_interval_lower": null,
  "confidence_interval_upper": null,
  "sample_size": 1500,
  "column_name": "Treatment Effect",
  "notes": "any relevant notes"
}}
```

TABLE CONTENT:
{table_content}
"""

BATCH_STATS_PROMPT = """You are an expert at extracting statistical parameters from academic regression tables.

TASK: For EACH outcome variable listed below, extract the treatment effect coefficient and statistics from the tables.

OUTCOMES TO FIND:
{outcomes_list}

EXTRACTION RULES:
1. For each outcome, find its row in the appropriate table
2. Extract the MAIN treatment effect coefficient (usually first data column or "Treatment" column)
3. Standard errors are typically in parentheses below coefficients
4. Asterisks: * p<0.1, ** p<0.05, *** p<0.01
5. Return null for values not found

RESPONSE FORMAT - Return a JSON array with one object per outcome:
```json
[
  {{
    "outcome_name": "original outcome name from list",
    "outcome_found": true,
    "outcome_name_in_table": "exact name in table",
    "table_source": "Table X",
    "coefficient": 0.123,
    "standard_error": 0.045,
    "p_value": 0.05,
    "significance_stars": "**",
    "confidence_interval_lower": null,
    "confidence_interval_upper": null,
    "sample_size": 1500
  }}
]
```

TABLES:
{tables_content}
"""


def call_llm(prompt: str, model: str = "openai/gpt-4o", max_tokens: int = 4000, timeout: int = 120) -> Optional[str]:
    """Call LLM via OpenRouter."""
    for attempt in range(3):
        try:
            response = SESSION.post(
                "https://openrouter.ai/api/v1/chat/completions",
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": max_tokens,
                    "temperature": 0.0,
                },
                timeout=timeout
            )
            
            if response.status_code == 200:
                data = response.json()
                return data["choices"][0]["message"]["content"]
            elif response.status_code == 429:
                time.sleep(5 * (attempt + 1))
            else:
                logger.error(f"API error: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            if attempt < 2:
                time.sleep(5)
    
    return None


def parse_json_response(response: str) -> Any:
    """Parse JSON from LLM response."""
    if not response:
        return None
    
    # Clean markdown code blocks
    response = re.sub(r'```json\s*', '', response)
    response = re.sub(r'```\s*', '', response)
    response = response.strip()
    
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        # Try to find JSON array or object
        match = re.search(r'[\[\{][\s\S]*[\]\}]', response)
        if match:
            try:
                return json.loads(match.group())
            except:
                pass
    
    return None


def get_r2_client():
    """Get R2 client."""
    return boto3.client(
        's3',
        endpoint_url=f'https://{CLOUDFLARE_ACCOUNT_ID}.r2.cloudflarestorage.com',
        aws_access_key_id=R2_ACCESS_KEY,
        aws_secret_access_key=R2_SECRET_KEY
    )


def load_tables_from_r2(r2_key: str) -> Dict[str, str]:
    """Load document from R2 and return tables as dict by table_id."""
    try:
        client = get_r2_client()
        response = client.get_object(Bucket=R2_BUCKET, Key=r2_key)
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
        
        return tables_dict
        
    except Exception as e:
        logger.error(f"Failed to load {r2_key}: {e}")
        return {}


def extract_stats_for_outcome(outcome_name: str, table_source: str, tables_dict: Dict[str, str]) -> Dict:
    """Extract statistical parameters for a single outcome from its table."""
    
    # Find the matching table
    table_content = None
    for table_id, content in tables_dict.items():
        # Match "Table 3" to "Table 3" or similar
        if table_source and table_source.lower() in table_id.lower():
            table_content = content
            break
        # Also try numeric match
        source_num = re.search(r'\d+', table_source or "")
        table_num = re.search(r'\d+', table_id)
        if source_num and table_num and source_num.group() == table_num.group():
            table_content = content
            break
    
    if not table_content:
        # Try to find outcome in any table
        for table_id, content in tables_dict.items():
            if outcome_name.lower()[:30] in content.lower():
                table_content = content
                table_source = table_id
                break
    
    if not table_content:
        return {
            "outcome_name": outcome_name,
            "outcome_found": False,
            "error": "table_not_found"
        }
    
    # Build prompt and call LLM
    prompt = STATS_EXTRACTION_PROMPT.format(
        outcome_name=outcome_name,
        table_source=table_source,
        table_content=table_content[:10000]
    )
    
    response = call_llm(prompt, model="openai/gpt-4o-mini", max_tokens=1000)
    result = parse_json_response(response)
    
    if result:
        result["outcome_name"] = outcome_name
        result["table_source"] = table_source
        return result
    
    return {
        "outcome_name": outcome_name,
        "outcome_found": False,
        "error": "extraction_failed"
    }


def extract_stats_batch(outcomes: List[Dict], tables_dict: Dict[str, str]) -> List[Dict]:
    """Extract stats for multiple outcomes in batch (more efficient)."""
    if not outcomes:
        return []
    
    # Group outcomes by table
    by_table = {}
    for o in outcomes:
        table = o.get("table_source", "unknown")
        if table not in by_table:
            by_table[table] = []
        by_table[table].append(o)
    
    all_results = []
    
    # Process each table group
    for table_source, table_outcomes in by_table.items():
        # Find table content
        table_content = None
        for table_id, content in tables_dict.items():
            source_num = re.search(r'\d+', table_source or "")
            table_num = re.search(r'\d+', table_id)
            if source_num and table_num and source_num.group() == table_num.group():
                table_content = content
                break
        
        if not table_content:
            # Mark all as not found
            for o in table_outcomes:
                all_results.append({
                    "outcome_name": o.get("outcome_name"),
                    "outcome_found": False,
                    "table_source": table_source,
                    "error": "table_not_found"
                })
            continue
        
        # Build batch prompt
        outcomes_list = "\n".join([
            f"- {o.get('outcome_name')} (from {table_source})" 
            for o in table_outcomes
        ])
        
        prompt = BATCH_STATS_PROMPT.format(
            outcomes_list=outcomes_list,
            tables_content=f"### {table_source}\n{table_content[:15000]}"
        )
        
        response = call_llm(prompt, model="openai/gpt-4o", max_tokens=4000)
        results = parse_json_response(response)
        
        if results and isinstance(results, list):
            all_results.extend(results)
        else:
            # Fall back to individual extraction
            for o in table_outcomes:
                result = extract_stats_for_outcome(
                    o.get("outcome_name", ""),
                    table_source,
                    tables_dict
                )
                all_results.append(result)
    
    return all_results


def process_study_stage2(study_result: Dict, study_data: Dict) -> Dict:
    """Process Stage 2 for a single study - extract stats for matched outcomes."""
    
    study_id = study_result.get("study_id")
    author = study_result.get("author", "Unknown")
    extracted_outcomes = study_result.get("extracted_outcomes", [])
    
    logger.info(f"Stage 2: {author} - {len(extracted_outcomes)} outcomes to enrich")
    
    # Load tables from R2
    r2_key = study_data.get("r2_key")
    if not r2_key:
        logger.error(f"  No R2 key for {author}")
        return {
            "study_id": study_id,
            "author": author,
            "success": False,
            "error": "no_r2_key",
            "outcomes": []
        }
    
    tables_dict = load_tables_from_r2(r2_key)
    logger.info(f"  Loaded {len(tables_dict)} tables")
    
    if not tables_dict:
        return {
            "study_id": study_id,
            "author": author,
            "success": False,
            "error": "no_tables",
            "outcomes": []
        }
    
    # Filter to table-sourced outcomes only (prose outcomes don't have stats)
    table_outcomes = [o for o in extracted_outcomes if o.get("table_source")]
    prose_outcomes = [o for o in extracted_outcomes if o.get("source") == "prose"]
    
    logger.info(f"  Table outcomes: {len(table_outcomes)}, Prose: {len(prose_outcomes)}")
    
    # Extract stats in batch
    enriched = extract_stats_batch(table_outcomes, tables_dict)
    
    # Count success
    found_count = sum(1 for e in enriched if e.get("outcome_found"))
    coef_count = sum(1 for e in enriched if e.get("coefficient") is not None)
    se_count = sum(1 for e in enriched if e.get("standard_error") is not None)
    
    logger.info(f"  ✅ Found: {found_count}/{len(table_outcomes)}")
    logger.info(f"  📊 Coefficients: {coef_count}, SEs: {se_count}")
    
    return {
        "study_id": study_id,
        "author": author,
        "success": True,
        "n_table_outcomes": len(table_outcomes),
        "n_prose_outcomes": len(prose_outcomes),
        "n_found": found_count,
        "n_with_coefficient": coef_count,
        "n_with_se": se_count,
        "enriched_outcomes": enriched,
        "prose_outcomes": prose_outcomes
    }


def run_stage2_pipeline(v17d_results_path: str = None, num_studies: int = None):
    """Run Stage 2 pipeline to extract statistical parameters."""
    
    logger.info("=" * 70)
    logger.info("STAGE 2: STATISTICAL PARAMETER EXTRACTION")
    logger.info("=" * 70)
    
    # Load V17d results
    if v17d_results_path is None:
        v17d_results_path = Path(__file__).parent / "v16_results.json"
    
    with open(v17d_results_path) as f:
        v17d_data = json.load(f)
    
    # Load original study data (for R2 keys)
    eval_path = Path(__file__).parent.parent / "evaluation" / "matched_studies_r2.json"
    with open(eval_path) as f:
        studies_data = json.load(f)
    
    # Create lookup by study_id
    studies_lookup = {s["study_id"]: s for s in studies_data}
    
    study_results = v17d_data.get("studies", [])
    if num_studies:
        study_results = study_results[:num_studies]
    
    logger.info(f"Processing {len(study_results)} studies")
    logger.info("")
    
    results = []
    start_time = datetime.now()
    
    total_outcomes = 0
    total_found = 0
    total_with_coef = 0
    total_with_se = 0
    
    for idx, study_result in enumerate(study_results, 1):
        study_id = study_result.get("study_id")
        study_data = studies_lookup.get(study_id, {})
        
        result = process_study_stage2(study_result, study_data)
        results.append(result)
        
        if result.get("success"):
            total_outcomes += result.get("n_table_outcomes", 0)
            total_found += result.get("n_found", 0)
            total_with_coef += result.get("n_with_coefficient", 0)
            total_with_se += result.get("n_with_se", 0)
        
        logger.info(f"Progress: {idx}/{len(study_results)}")
        logger.info("")
    
    elapsed = datetime.now() - start_time
    
    # Summary
    logger.info("=" * 70)
    logger.info("STAGE 2 RESULTS")
    logger.info("=" * 70)
    logger.info(f"Studies processed: {len(results)}")
    logger.info(f"Time elapsed: {elapsed}")
    logger.info("")
    logger.info(f"Table outcomes processed: {total_outcomes}")
    logger.info(f"Outcomes found in tables: {total_found} ({100*total_found/max(1,total_outcomes):.1f}%)")
    logger.info(f"With coefficient extracted: {total_with_coef} ({100*total_with_coef/max(1,total_outcomes):.1f}%)")
    logger.info(f"With SE extracted: {total_with_se} ({100*total_with_se/max(1,total_outcomes):.1f}%)")
    logger.info("=" * 70)
    
    # Save results
    output = {
        "summary": {
            "total_table_outcomes": total_outcomes,
            "total_found": total_found,
            "total_with_coefficient": total_with_coef,
            "total_with_se": total_with_se,
            "coef_extraction_rate": total_with_coef / max(1, total_outcomes),
            "se_extraction_rate": total_with_se / max(1, total_outcomes),
            "elapsed_seconds": elapsed.total_seconds()
        },
        "studies": results
    }
    
    output_path = Path(__file__).parent / "v17d_stage2_results.json"
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2)
    
    logger.info(f"Results saved to {output_path}")
    
    return output


if __name__ == "__main__":
    num_studies = int(sys.argv[1]) if len(sys.argv) > 1 else None
    run_stage2_pipeline(num_studies=num_studies)
