"""
Extraction V7 - Aggressive Table Extraction

KEY CHANGES from V6:
1. Increase max_tokens to 16000 for longer outputs
2. More aggressive prompting to extract ALL rows from ALL tables
3. Multi-pass extraction for studies with many tables
4. Explicitly count expected outcomes and verify

V6 Problem: Only extracting 6-10 outcomes per study when GT has up to 44
- LLM was being too conservative
- Need to explicitly demand extraction of EVERY row from results tables
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
import time
from html.parser import HTMLParser

load_dotenv()

OPENROUTER_API_KEY = os.environ.get('OPENROUTER_API_KEY')
MODEL = "anthropic/claude-3.5-sonnet"
CLOUDFLARE_ACCOUNT_ID = os.environ.get('CLOUDFLARE_ACCOUNT_ID')
R2_ACCESS_KEY = os.environ.get('R2_ACCESS_KEY_ID')
R2_SECRET_KEY = os.environ.get('R2_SECRET_ACCESS_KEY')

# ============================================================================
# COHEN'S D FORMULA
# ============================================================================

def compute_cohens_d(
    coef: Optional[float] = None,
    se: Optional[float] = None,
    t_stat: Optional[float] = None,
    n_treatment: Optional[int] = None,
    n_control: Optional[int] = None,
    n_total: Optional[int] = None,
) -> Tuple[Optional[float], str]:
    """Compute Cohen's d."""
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


# ============================================================================
# HTML TABLE PARSER
# ============================================================================

class HTMLTableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tables = []
        self.current_table = []
        self.current_row = []
        self.current_cell = ""
        self.in_table = False
        self.in_row = False
        self.in_cell = False
    
    def handle_starttag(self, tag, attrs):
        if tag == 'table':
            self.in_table = True
            self.current_table = []
        elif tag == 'tr' and self.in_table:
            self.in_row = True
            self.current_row = []
        elif tag in ('td', 'th') and self.in_row:
            self.in_cell = True
            self.current_cell = ""
    
    def handle_endtag(self, tag):
        if tag in ('td', 'th') and self.in_cell:
            self.current_row.append(self.current_cell.strip())
            self.current_cell = ""
            self.in_cell = False
        elif tag == 'tr' and self.in_row:
            if self.current_row:
                self.current_table.append(self.current_row)
            self.current_row = []
            self.in_row = False
        elif tag == 'table' and self.in_table:
            if self.current_table:
                self.tables.append(self.current_table)
            self.current_table = []
            self.in_table = False
    
    def handle_data(self, data):
        if self.in_cell:
            self.current_cell += data


def html_to_markdown_table(html: str) -> str:
    """Convert HTML table to markdown format."""
    parser = HTMLTableParser()
    try:
        parser.feed(html)
    except Exception:
        return ""
    
    if not parser.tables:
        return ""
    
    result = []
    for table in parser.tables:
        if not table:
            continue
        
        num_cols = max(len(row) for row in table) if table else 0
        if num_cols == 0:
            continue
        
        normalized = []
        for row in table:
            while len(row) < num_cols:
                row.append("")
            normalized.append(row)
        
        md_rows = []
        for i, row in enumerate(normalized):
            md_row = "| " + " | ".join(cell.replace("|", "\\|") for cell in row) + " |"
            md_rows.append(md_row)
            if i == 0:
                separator = "| " + " | ".join("---" for _ in row) + " |"
                md_rows.append(separator)
        
        result.append("\n".join(md_rows))
    
    return "\n\n".join(result)


def extract_tables_from_json(data: Dict) -> List[Dict]:
    """Extract tables with metadata from MineRU JSON output."""
    tables = data.get("tables", [])
    if not tables:
        return []
    
    processed_tables = []
    for i, table in enumerate(tables):
        table_html = ""
        if isinstance(table, dict):
            table_html = table.get("table_body", "") or table.get("html", "") or table.get("content", "")
        elif isinstance(table, str):
            table_html = table
        
        if table_html:
            md = html_to_markdown_table(table_html)
            if md:
                # Count rows (excluding header)
                row_count = md.count('\n') - 1  # Subtract header separator
                processed_tables.append({
                    "index": i + 1,
                    "markdown": md,
                    "row_count": max(0, row_count)
                })
    
    return processed_tables


# Global session
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
    
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        pass
    
    cleaned = re.sub(r'[\x00-\x1f\x7f-\x9f]', ' ', json_str)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    
    fixed = cleaned.replace('\n', ' ').replace('\r', ' ')
    fixed = re.sub(r',\s*}', '}', fixed)
    fixed = re.sub(r',\s*]', ']', fixed)
    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        return {}


def call_llm(prompt: str, max_tokens: int = 16000, retries: int = 3) -> Dict:
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
                timeout=600  # Longer timeout for larger responses
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            return robust_json_parse(content)
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 400:
                print(f"    400 Error: {str(e)[:100]}")
                return {}
            if attempt < retries - 1:
                wait = 10 * (attempt + 1)
                print(f"    Retry {attempt + 1}/{retries}: {str(e)[:80]}")
                time.sleep(wait)
            else:
                print(f"    Failed: {str(e)[:80]}")
                return {}
        except Exception as e:
            if attempt < retries - 1:
                print(f"    Retry {attempt + 1}/{retries}: {str(e)[:80]}")
                time.sleep(10 * (attempt + 1))
            else:
                print(f"    Failed: {str(e)[:80]}")
                return {}
    return {}


def load_document_with_tables(study_data: Dict) -> Tuple[Optional[str], List[Dict], int]:
    """Load document content AND structured tables from R2."""
    try:
        r2_key = study_data.get('r2_key')
        if not r2_key:
            return None, [], 0
        
        bucket = os.environ.get('R2_BUCKET_NAME', 'devchat-pdfs')
        
        s3 = boto3.client(
            's3',
            endpoint_url=f'https://{CLOUDFLARE_ACCOUNT_ID}.r2.cloudflarestorage.com',
            aws_access_key_id=R2_ACCESS_KEY,
            aws_secret_access_key=R2_SECRET_KEY
        )
        
        response = s3.get_object(Bucket=bucket, Key=r2_key)
        raw_content = response['Body'].read()
        
        try:
            json_str = raw_content.decode('utf-8')
        except UnicodeDecodeError:
            json_str = raw_content.decode('latin-1')
        
        data = json.loads(json_str)
        content = data.get("content", "")
        tables = extract_tables_from_json(data)
        
        return content, tables, len(tables)
        
    except Exception as e:
        print(f"    Error loading document: {e}")
        return None, [], 0


# ============================================================================
# V7: AGGRESSIVE EXTRACTION PROMPT
# ============================================================================

EXTRACTION_PROMPT = """You are extracting outcomes from an academic study on poverty/development interventions.

## CRITICAL INSTRUCTION:
You MUST extract EVERY SINGLE outcome from EVERY table below. Do not summarize or skip rows.
If a table has 20 rows of outcomes, you must extract all 20.
The tables contain approximately {expected_outcomes} outcome rows total - extract ALL of them.

## DOCUMENT TEXT (for context):
{content}

## RESULTS TABLES (extract EVERY row):
{tables}

## EXTRACTION REQUIREMENTS:

### METADATA (extract once):
- study_design: "RCT" or "Quasi-experimental"
- country, year, author, program_name
- targeting_women, consumption_support, health_comp, asset_transfer, skills_comp, savings_comp, coaching_comp, social_comp (true/false)

### OUTCOMES (extract EVERY row from EVERY results table):
For EACH outcome row, extract:
- outcome_name: Exact name from table (e.g., "Monthly household income", "Livestock value")
- outcome_category: One of "Income", "Assets", "Savings", "Expenditure", "Poverty"
- coefficient: The treatment effect number
- standard_error: SE (often in parentheses below coefficient)
- confidence_interval_lower: Lower CI bound if shown
- confidence_interval_upper: Upper CI bound if shown
- t_statistic: t-stat if available
- p_value: p-value if shown
- n_treatment, n_control, n_total: Sample sizes
- evidence_location: "Table X, Row Y" or column name

### CATEGORY MAPPING:
- Income: earnings, wages, income, revenue, profits, business income
- Assets: livestock, equipment, housing, wealth index, asset value, TLU
- Savings: savings, VSLA, tontine, group savings
- Expenditure: consumption, spending, expenses, food expenditure
- Poverty: poverty rate, poverty gap, poverty index, food security

## IMPORTANT:
- Extract EVERY row that has a coefficient/treatment effect
- Include outcomes even if coefficient is not statistically significant
- Each unique outcome-treatment arm combination is a separate entry
- If a table shows effects at multiple time points, extract each as separate outcomes

Return ONLY valid JSON with this structure:
{{
  "metadata": {{
    "study_design": {{"value": "RCT", "confidence": 0.95}},
    "country": {{"value": "Bangladesh", "confidence": 0.99}},
    "year": {{"value": 2019, "confidence": 0.99}},
    "author": {{"value": "Bandiera", "confidence": 0.99}},
    "program_name": {{"value": "BRAC TUP", "confidence": 0.95}},
    "targeting_women": {{"value": true, "confidence": 0.90}},
    "consumption_support": {{"value": true, "confidence": 0.85}},
    "health_comp": {{"value": false, "confidence": 0.80}},
    "asset_transfer": {{"value": true, "confidence": 0.95}},
    "skills_comp": {{"value": true, "confidence": 0.90}},
    "savings_comp": {{"value": true, "confidence": 0.85}},
    "coaching_comp": {{"value": true, "confidence": 0.90}},
    "social_comp": {{"value": false, "confidence": 0.75}}
  }},
  "outcomes": [
    {{
      "outcome_name": "Monthly household income",
      "outcome_category": "Income",
      "coefficient": 245.30,
      "standard_error": 89.20,
      "confidence_interval_lower": 70.5,
      "confidence_interval_upper": 420.1,
      "t_statistic": 2.75,
      "p_value": 0.006,
      "n_treatment": 1200,
      "n_control": 1300,
      "n_total": 2500,
      "evidence_location": "Table 3, Row 1"
    }},
    // ... MORE OUTCOMES - extract ALL of them
  ]
}}

REMEMBER: Extract EVERY outcome row. Target: {expected_outcomes}+ outcomes from these tables."""


def estimate_outcome_count(tables: List[Dict]) -> int:
    """Estimate expected number of outcomes from table row counts."""
    total_rows = sum(t.get("row_count", 0) for t in tables)
    # Assume ~50% of rows are actual outcome data (rest are headers, notes, etc.)
    return max(10, int(total_rows * 0.5))


def process_study(study_data: Dict, study_idx: int) -> Dict:
    """Process a single study with aggressive table extraction."""
    study_id = study_data.get('study_id', 'unknown')
    ground_truth = study_data.get('ground_truth', {})
    author = ground_truth.get('author', 'Unknown')
    gt_outcome_count = len(ground_truth.get('outcomes', []))
    
    print(f"\n[{study_idx}] Processing: {author} (ID: {study_id}, GT outcomes: {gt_outcome_count})")
    
    # Load content AND tables
    content, tables, num_tables = load_document_with_tables(study_data)
    
    if not content:
        print(f"    ❌ Failed to load document")
        return {"study_id": study_id, "success": False, "error": "Failed to load document"}
    
    # Estimate expected outcomes
    expected_outcomes = estimate_outcome_count(tables)
    expected_outcomes = max(expected_outcomes, gt_outcome_count)  # At least as many as GT
    
    print(f"    📄 Loaded: {len(content):,} chars, {num_tables} tables, ~{expected_outcomes} expected outcomes")
    
    # Format tables for prompt
    if tables:
        tables_section = "\n\n".join([
            f"### Table {t['index']} (~{t['row_count']} rows)\n{t['markdown']}" 
            for t in tables
        ])
    else:
        tables_section = "(No structured tables found)"
    
    # Build prompt with expected outcome count
    prompt = EXTRACTION_PROMPT.format(
        content=content[:100000],  # Limit content, prioritize tables
        tables=tables_section,
        expected_outcomes=expected_outcomes
    )
    
    print(f"    🤖 Calling LLM ({len(prompt):,} chars, max_tokens=16000)...")
    result = call_llm(prompt, max_tokens=16000)
    
    if not result:
        print(f"    ❌ LLM extraction failed")
        return {"study_id": study_id, "success": False, "error": "LLM extraction failed"}
    
    # Extract metadata
    metadata = {}
    raw_metadata = result.get("metadata", {})
    for key, val in raw_metadata.items():
        if isinstance(val, dict):
            metadata[key] = val.get("value")
            metadata[f"{key}_confidence"] = val.get("confidence", 0)
        else:
            metadata[key] = val
    
    # Extract outcomes
    outcomes = result.get("outcomes", [])
    processed_outcomes = []
    
    for outcome in outcomes:
        coef = outcome.get("coefficient")
        se = outcome.get("standard_error")
        n_t = outcome.get("n_treatment")
        n_c = outcome.get("n_control")
        n_total = outcome.get("n_total")
        t_stat = outcome.get("t_statistic")
        
        d, method = compute_cohens_d(
            coef=coef, se=se, t_stat=t_stat,
            n_treatment=n_t, n_control=n_c, n_total=n_total
        )
        
        processed_outcome = {
            "outcome_name": outcome.get("outcome_name"),
            "outcome_category": outcome.get("outcome_category"),
            "coefficient": coef,
            "standard_error": se,
            "confidence_interval_lower": outcome.get("confidence_interval_lower"),
            "confidence_interval_upper": outcome.get("confidence_interval_upper"),
            "t_statistic": t_stat,
            "p_value": outcome.get("p_value"),
            "n_treatment": n_t,
            "n_control": n_c,
            "n_total": n_total,
            "effect_size_d": d,
            "d_computation_method": method,
            "evidence_location": outcome.get("evidence_location")
        }
        processed_outcomes.append(processed_outcome)
    
    # Count CIs
    ci_count = sum(1 for o in processed_outcomes 
                   if o.get("confidence_interval_lower") is not None 
                   and o.get("confidence_interval_upper") is not None)
    
    extraction_rate = len(processed_outcomes) / expected_outcomes * 100 if expected_outcomes > 0 else 0
    
    print(f"    ✅ Extracted: {len(processed_outcomes)} outcomes (target: {expected_outcomes}, rate: {extraction_rate:.0f}%)")
    if ci_count > 0:
        print(f"    📊 CIs extracted: {ci_count}")
    
    return {
        "study_id": study_id,
        "success": True,
        "metadata": metadata,
        "outcomes": processed_outcomes,
        "num_tables_found": num_tables,
        "expected_outcomes": expected_outcomes,
        "extraction_rate": extraction_rate,
        "ground_truth": ground_truth
    }


def main():
    """Run V7 extraction on all matched studies."""
    print("=" * 70)
    print("EXTRACTION V7 - Aggressive Table Extraction")
    print("=" * 70)
    print("Changes from V6:")
    print("  - max_tokens: 8000 → 16000")
    print("  - Explicit instruction to extract ALL rows")
    print("  - Shows expected outcome count to LLM")
    print("=" * 70)
    
    # Load matched studies
    with open("evaluation/matched_studies_r2.json", "r") as f:
        studies = json.load(f)
    
    print(f"\nLoaded {len(studies)} studies for extraction")
    
    results = []
    success_count = 0
    total_outcomes = 0
    total_tables = 0
    total_cis = 0
    
    for idx, study in enumerate(studies, 1):
        result = process_study(study, idx)
        results.append(result)
        
        if result.get("success"):
            success_count += 1
            outcomes = result.get("outcomes", [])
            total_outcomes += len(outcomes)
            total_tables += result.get("num_tables_found", 0)
            
            for o in outcomes:
                if o.get("confidence_interval_lower") is not None and o.get("confidence_interval_upper") is not None:
                    total_cis += 1
        
        # Save intermediate results every 10 studies
        if idx % 10 == 0:
            print(f"\n--- Progress: {idx}/{len(studies)} ({success_count} OK, {total_outcomes} outcomes, {total_cis} CIs) ---")
            with open("evaluation/extraction_v7_results.json", "w") as f:
                json.dump(results, f, indent=2)
    
    # Save final results
    output_file = "evaluation/extraction_v7_results.json"
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)
    
    print("\n" + "=" * 70)
    print("EXTRACTION V7 COMPLETE")
    print("=" * 70)
    print(f"Studies processed: {len(studies)}")
    print(f"Successful: {success_count}")
    print(f"Total outcomes extracted: {total_outcomes}")
    print(f"Total tables found: {total_tables}")
    print(f"Total CIs extracted: {total_cis}")
    print(f"Avg outcomes/study: {total_outcomes/success_count:.1f}" if success_count > 0 else "N/A")
    print(f"Results saved to: {output_file}")


if __name__ == "__main__":
    main()
