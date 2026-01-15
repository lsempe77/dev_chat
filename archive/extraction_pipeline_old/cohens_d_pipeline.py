"""
Cohen's d Enrichment Pipeline
==============================
Enriches Stage 2 extraction results with Cohen's d effect sizes.

Approach:
1. For each outcome with extracted coefficient, find Control SD in the table
2. Compute Cohen's d = coefficient / Control SD
3. Compare with GT effect_size_d where available

The table format typically has:
- Row: "Control mean Control SD" with values across columns
- Each column corresponds to an outcome
- We need to match outcome column to get the correct SD
"""

import os
import re
import json
import boto3
import math
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime
from dotenv import load_dotenv
import logging
import sys
from pathlib import Path
from dataclasses import dataclass
import requests

# Local imports
from preprocess import preprocess_mineru_table

load_dotenv()

# ============================================================================
# CONFIGURATION
# ============================================================================

CLOUDFLARE_ACCOUNT_ID = os.environ.get('CLOUDFLARE_ACCOUNT_ID')
R2_ACCESS_KEY = os.environ.get('R2_ACCESS_KEY_ID')
R2_SECRET_KEY = os.environ.get('R2_SECRET_ACCESS_KEY')
R2_BUCKET = os.environ.get('R2_BUCKET_NAME', 'devchat-pdfs')

OPENROUTER_API_KEY = os.environ.get('OPENROUTER_API_KEY')
SESSION = requests.Session()
SESSION.headers.update({
    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
    "Content-Type": "application/json"
})

# Paths
STAGE2_PATH = Path(__file__).parent / "v17d_stage2_results.json"
GT_PATH = Path(__file__).parent.parent / "evaluation" / "matched_studies_r2.json"
OUTPUT_PATH = Path(__file__).parent / "v17d_cohens_d_results.json"

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

# ============================================================================
# R2 CLIENT
# ============================================================================

def get_r2_client():
    """Get R2 client."""
    return boto3.client(
        's3',
        endpoint_url=f'https://{CLOUDFLARE_ACCOUNT_ID}.r2.cloudflarestorage.com',
        aws_access_key_id=R2_ACCESS_KEY,
        aws_secret_access_key=R2_SECRET_KEY
    )

_tables_cache: Dict[str, Dict[str, str]] = {}

def load_tables_from_r2(r2_key: str) -> Dict[str, str]:
    """Load all tables from R2 for a study."""
    if r2_key in _tables_cache:
        return _tables_cache[r2_key]
    
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
        
        _tables_cache[r2_key] = tables_dict
        return tables_dict
        
    except Exception as e:
        logger.error(f"Failed to load {r2_key}: {e}")
        return {}

# ============================================================================
# CONTROL SD EXTRACTION (REGEX-BASED)
# ============================================================================

@dataclass
class TableStats:
    """Statistics extracted from a table for an outcome."""
    control_mean: Optional[float] = None
    control_sd: Optional[float] = None
    observations: Optional[int] = None
    column_index: Optional[int] = None

def extract_table_structure(table_md: str) -> Dict:
    """Parse table to understand column structure."""
    lines = table_md.strip().split('\n')
    
    result = {
        "headers": [],
        "control_mean_row": None,
        "control_sd_row": None,
        "observations_row": None,
        "combined_mean_sd_row": None
    }
    
    for i, line in enumerate(lines):
        if '|' not in line:
            continue
        
        cells = [c.strip() for c in line.split('|')]
        cells = [c for c in cells if c]  # Remove empty cells
        
        # Check for header row
        if i == 0 or (i == 1 and '---' not in line):
            if any('(' in c for c in cells):  # Has column numbers like (1), (2)
                result["headers"] = cells
        
        # Check for Control mean/SD rows
        first_cell = cells[0].lower() if cells else ""
        
        if "control mean" in first_cell and "control sd" in first_cell:
            result["combined_mean_sd_row"] = i
            result["combined_mean_sd_values"] = cells[1:] if len(cells) > 1 else []
        elif "control mean" in first_cell:
            result["control_mean_row"] = i
            result["control_mean_values"] = cells[1:] if len(cells) > 1 else []
        elif "control sd" in first_cell:
            result["control_sd_row"] = i
            result["control_sd_values"] = cells[1:] if len(cells) > 1 else []
        elif "observations" in first_cell:
            result["observations_row"] = i
            result["observations_values"] = cells[1:] if len(cells) > 1 else []
    
    return result

def find_outcome_column(table_md: str, outcome_name: str) -> Optional[int]:
    """Find which column contains the outcome."""
    lines = table_md.strip().split('\n')
    
    # Normalize outcome name for matching
    outcome_lower = outcome_name.lower().replace('^', '').replace('{', '').replace('}', '').strip()
    outcome_words = set(outcome_lower.split()[:3])  # First 3 words
    
    for i, line in enumerate(lines):
        if '|' not in line or '---' in line:
            continue
        
        cells = [c.strip() for c in line.split('|')]
        cells = [c for c in cells if c]
        
        # Check each cell for outcome match
        for col_idx, cell in enumerate(cells):
            cell_lower = cell.lower().replace('^', '').replace('{', '').replace('}', '').strip()
            cell_words = set(cell_lower.split()[:3])
            
            # Match if outcome name is in cell or significant word overlap
            if outcome_lower[:20] in cell_lower or cell_lower[:20] in outcome_lower:
                return col_idx
            if len(outcome_words & cell_words) >= 2:
                return col_idx
    
    return None

def extract_control_sd_for_outcome(table_md: str, outcome_name: str) -> TableStats:
    """Extract Control SD for a specific outcome from the table."""
    stats = TableStats()
    
    # Parse table structure
    structure = extract_table_structure(table_md)
    
    # Find outcome column
    col_idx = find_outcome_column(table_md, outcome_name)
    if col_idx is None:
        return stats
    
    stats.column_index = col_idx
    
    # Handle combined "Control mean Control SD" row
    # Format: "Control mean Control SD | mean1 | mean2 | mean3 |"
    #         next row: "                      | sd1   | sd2   | sd3   |"
    if structure.get("combined_mean_sd_row") is not None:
        mean_sd_values = structure.get("combined_mean_sd_values", [])
        
        # The values are typically: mean1, mean2, mean3 in first data row after label
        # and sd1, sd2, sd3 in the next row
        lines = table_md.strip().split('\n')
        combined_row_idx = structure["combined_mean_sd_row"]
        
        # Parse the combined row
        if col_idx - 1 < len(mean_sd_values):
            try:
                # First value on this row is the mean
                stats.control_mean = float(mean_sd_values[col_idx - 1])
            except (ValueError, IndexError):
                pass
        
        # Check next row for SD values
        if combined_row_idx + 1 < len(lines):
            next_line = lines[combined_row_idx + 1]
            next_cells = [c.strip() for c in next_line.split('|')]
            next_cells = [c for c in next_cells if c]
            
            # If first cell is mostly empty or a continuation, these are SD values
            if next_cells and (not next_cells[0] or next_cells[0].replace('.', '').replace('-', '').isdigit()):
                if col_idx < len(next_cells):
                    try:
                        stats.control_sd = float(next_cells[col_idx])
                    except (ValueError, IndexError):
                        pass
    
    # Handle separate Control SD row
    if stats.control_sd is None and structure.get("control_sd_values"):
        sd_values = structure["control_sd_values"]
        if col_idx - 1 < len(sd_values):
            try:
                stats.control_sd = float(sd_values[col_idx - 1])
            except (ValueError, IndexError):
                pass
    
    # Handle separate Control mean row
    if stats.control_mean is None and structure.get("control_mean_values"):
        mean_values = structure["control_mean_values"]
        if col_idx - 1 < len(mean_values):
            try:
                stats.control_mean = float(mean_values[col_idx - 1])
            except (ValueError, IndexError):
                pass
    
    return stats

# ============================================================================
# LLM-BASED EXTRACTION (FALLBACK)
# ============================================================================

COHENS_D_PROMPT = """Extract Control SD for the outcome "{outcome_name}" from this regression table.

TABLE:
{table_markdown}

The outcome has an extracted coefficient of {coefficient}.

Look for:
1. A row labeled "Control mean Control SD" or "Control SD" 
2. Find the column that matches the outcome name
3. Extract the Control SD value for that column

Respond in JSON:
{{
    "found_outcome_column": <boolean>,
    "column_name": "<name of matching column>",
    "control_sd": <float or null>,
    "control_mean": <float or null>,
    "explanation": "<brief explanation>"
}}
"""

def extract_control_sd_via_llm(table_md: str, outcome_name: str, coefficient: float) -> Dict:
    """Use LLM to extract Control SD when regex fails."""
    try:
        response = SESSION.post(
            "https://openrouter.ai/api/v1/chat/completions",
            json={
                "model": "openai/gpt-4o-mini",
                "messages": [{
                    "role": "user",
                    "content": COHENS_D_PROMPT.format(
                        outcome_name=outcome_name,
                        coefficient=coefficient,
                        table_markdown=table_md[:3000]
                    )
                }],
                "response_format": {"type": "json_object"},
                "temperature": 0
            },
            timeout=30
        )
        
        if response.status_code == 200:
            content = response.json()["choices"][0]["message"]["content"]
            return json.loads(content)
        else:
            return {"error": f"API error: {response.status_code}"}
    except Exception as e:
        return {"error": str(e)}

# ============================================================================
# COHEN'S D COMPUTATION
# ============================================================================

def compute_cohens_d_from_sd(coefficient: float, control_sd: float) -> Optional[float]:
    """Compute Cohen's d from coefficient and control SD.
    Formula: d = coefficient / SD_control
    """
    if control_sd is None or control_sd <= 0:
        return None
    return coefficient / control_sd

def compute_cohens_d_from_t(coefficient: float, se: float, n: int) -> Optional[float]:
    """Compute Cohen's d from t-statistic and sample size.
    
    This is the formula used in meta-analysis and matches the GT:
    d = 2 * t / sqrt(n)
    
    Where t = coefficient / SE
    """
    if se is None or se <= 0 or n is None or n <= 0:
        return None
    
    t_stat = coefficient / se
    d = 2 * t_stat / math.sqrt(n)
    return d

def compute_cohens_d(
    coefficient: float, 
    se: Optional[float] = None,
    n: Optional[int] = None,
    control_sd: Optional[float] = None
) -> Tuple[Optional[float], str]:
    """Compute Cohen's d using the best available method.
    
    Priority:
    1. t-statistic method (d = 2*t/sqrt(n)) - matches GT formula
    2. SD method (d = coef/SD) - traditional formula
    
    Returns (d, method_description)
    """
    # Method 1: t-statistic (preferred - matches GT)
    if se and n and se > 0 and n > 0:
        t_stat = coefficient / se
        d = 2 * t_stat / math.sqrt(n)
        return d, f"t-stat: d=2*({coefficient}/{se})/sqrt({n})"
    
    # Method 2: Control SD
    if control_sd and control_sd > 0:
        d = coefficient / control_sd
        return d, f"SD: d={coefficient}/{control_sd}"
    
    return None, "insufficient_data"

# ============================================================================
# MAIN PIPELINE
# ============================================================================

def enrich_study_with_cohens_d(
    study_results: Dict,
    tables_dict: Dict[str, str],
    use_llm_fallback: bool = True
) -> Dict:
    """Enrich a study's outcomes with Cohen's d.
    
    Uses t-statistic method (d = 2*t/sqrt(n)) as primary since it matches GT.
    Falls back to SD method when SE/N not available.
    """
    
    enriched_outcomes = []
    n_with_d = 0
    n_t_stat_method = 0
    n_sd_method = 0
    n_llm_used = 0
    
    for outcome in study_results.get("enriched_outcomes", []):
        enriched = outcome.copy()
        
        coef = outcome.get("coefficient")
        se = outcome.get("standard_error")
        n = outcome.get("sample_size")
        table_source = outcome.get("table_source")
        outcome_name = outcome.get("outcome_name", "")
        
        if coef is None:
            enriched["cohens_d"] = None
            enriched["cohens_d_method"] = "no_coefficient"
            enriched_outcomes.append(enriched)
            continue
        
        # Method 1: t-statistic (preferred - matches GT formula)
        if se and n and se > 0 and n > 0:
            d, method = compute_cohens_d(coef, se=se, n=n)
            enriched["cohens_d"] = d
            enriched["cohens_d_method"] = "t_statistic"
            enriched["t_statistic"] = coef / se
            n_with_d += 1
            n_t_stat_method += 1
            enriched_outcomes.append(enriched)
            continue
        
        # Method 2: Extract Control SD from table
        if not table_source:
            enriched["cohens_d"] = None
            enriched["cohens_d_method"] = "no_table_source"
            enriched_outcomes.append(enriched)
            continue
        
        # Find the table
        table_md = None
        for table_id, content in tables_dict.items():
            source_num = re.search(r'\d+', table_source or "")
            table_num = re.search(r'\d+', table_id)
            if source_num and table_num and source_num.group() == table_num.group():
                table_md = content
                break
        
        if not table_md:
            enriched["cohens_d"] = None
            enriched["cohens_d_method"] = "table_not_found"
            enriched_outcomes.append(enriched)
            continue
        
        # Try regex extraction for Control SD
        stats = extract_control_sd_for_outcome(table_md, outcome_name)
        
        if stats.control_sd and stats.control_sd > 0:
            d, method = compute_cohens_d(coef, control_sd=stats.control_sd)
            enriched["control_sd"] = stats.control_sd
            enriched["control_mean"] = stats.control_mean
            enriched["cohens_d"] = d
            enriched["cohens_d_method"] = "control_sd_regex"
            n_with_d += 1
            n_sd_method += 1
        elif use_llm_fallback:
            # Try LLM extraction
            llm_result = extract_control_sd_via_llm(table_md, outcome_name, coef)
            
            if llm_result.get("control_sd"):
                control_sd = llm_result["control_sd"]
                d, method = compute_cohens_d(coef, control_sd=control_sd)
                enriched["control_sd"] = control_sd
                enriched["control_mean"] = llm_result.get("control_mean")
                enriched["cohens_d"] = d
                enriched["cohens_d_method"] = "control_sd_llm"
                n_with_d += 1
                n_sd_method += 1
                n_llm_used += 1
            else:
                enriched["cohens_d"] = None
                enriched["cohens_d_method"] = "extraction_failed"
        else:
            enriched["cohens_d"] = None
            enriched["cohens_d_method"] = "no_se_or_sd"
        
        enriched_outcomes.append(enriched)
    
    return {
        "study_id": study_results.get("study_id"),
        "author": study_results.get("author"),
        "n_outcomes": len(enriched_outcomes),
        "n_with_cohens_d": n_with_d,
        "n_t_stat_method": n_t_stat_method,
        "n_sd_method": n_sd_method,
        "n_llm_extractions": n_llm_used,
        "enriched_outcomes": enriched_outcomes
    }

def run_cohens_d_pipeline(use_llm: bool = True):
    """Run the full Cohen's d enrichment pipeline."""
    
    logger.info("=" * 70)
    logger.info("COHEN'S D ENRICHMENT PIPELINE")
    logger.info("=" * 70)
    
    # Load Stage 2 results
    with open(STAGE2_PATH) as f:
        stage2_results = json.load(f)
    
    # Load GT for r2_keys
    with open(GT_PATH) as f:
        gt_studies = json.load(f)
    
    r2_key_lookup = {s["study_id"]: s.get("r2_key", "") for s in gt_studies}
    
    logger.info(f"Processing {len(stage2_results['studies'])} studies")
    logger.info(f"LLM fallback: {'enabled' if use_llm else 'disabled'}")
    logger.info(f"Primary method: t-statistic (d = 2*t/sqrt(n)) - matches GT formula")
    
    start_time = datetime.now()
    all_results = []
    
    total_outcomes = 0
    total_with_d = 0
    total_t_stat = 0
    total_sd = 0
    total_llm = 0
    
    for study in stage2_results["studies"]:
        study_id = study["study_id"]
        author = study["author"]
        r2_key = r2_key_lookup.get(study_id, "")
        
        logger.info(f"\nProcessing: {author}")
        
        if not r2_key:
            logger.warning(f"  No R2 key found - skipping")
            continue
        
        # Load tables
        tables_dict = load_tables_from_r2(r2_key)
        logger.info(f"  Loaded {len(tables_dict)} tables")
        
        # Enrich with Cohen's d
        enriched = enrich_study_with_cohens_d(study, tables_dict, use_llm_fallback=use_llm)
        all_results.append(enriched)
        
        total_outcomes += enriched["n_outcomes"]
        total_with_d += enriched["n_with_cohens_d"]
        total_t_stat += enriched.get("n_t_stat_method", 0)
        total_sd += enriched.get("n_sd_method", 0)
        total_llm += enriched.get("n_llm_extractions", 0)
        
        logger.info(f"  ✅ Cohen's d: {enriched['n_with_cohens_d']}/{enriched['n_outcomes']}")
        logger.info(f"     - t-stat method: {enriched.get('n_t_stat_method', 0)}")
        logger.info(f"     - SD method: {enriched.get('n_sd_method', 0)}")
        if use_llm:
            logger.info(f"  🤖 LLM extractions: {enriched.get('n_llm_extractions', 0)}")
    
    elapsed = datetime.now() - start_time
    
    # Summary
    logger.info("\n" + "=" * 70)
    logger.info("RESULTS SUMMARY")
    logger.info("=" * 70)
    logger.info(f"Total outcomes: {total_outcomes}")
    logger.info(f"With Cohen's d: {total_with_d} ({100*total_with_d/total_outcomes:.1f}%)")
    logger.info(f"  - t-stat method: {total_t_stat} ({100*total_t_stat/total_outcomes:.1f}%)")
    logger.info(f"  - SD method: {total_sd} ({100*total_sd/total_outcomes:.1f}%)")
    if use_llm:
        logger.info(f"LLM extractions (for SD): {total_llm}")
    logger.info(f"Time elapsed: {elapsed}")
    
    # Save results
    output = {
        "summary": {
            "total_outcomes": total_outcomes,
            "n_with_cohens_d": total_with_d,
            "n_t_stat_method": total_t_stat,
            "n_sd_method": total_sd,
            "cohens_d_rate": total_with_d / total_outcomes if total_outcomes else 0,
            "n_llm_extractions": total_llm,
            "elapsed_seconds": elapsed.total_seconds()
        },
        "studies": all_results
    }
    
    with open(OUTPUT_PATH, 'w') as f:
        json.dump(output, f, indent=2)
    
    logger.info(f"\nResults saved to: {OUTPUT_PATH}")
    
    return output


if __name__ == "__main__":
    use_llm = "--no-llm" not in sys.argv
    run_cohens_d_pipeline(use_llm=use_llm)
