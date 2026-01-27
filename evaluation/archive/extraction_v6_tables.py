"""
Extraction V6 - With Structured Table Data

KEY CHANGE from V5:
- Parse the 'tables' field from R2 JSON (HTML table data from MineRU)
- Convert HTML tables to markdown format for LLM consumption
- Include BOTH prose content AND structured tables in extraction prompt

ROOT CAUSE OF LOW RECALL:
- MineRU extracts tables to separate 'tables' field as HTML
- Previous versions only read 'content' field (prose without structured tables)
- Coefficients, SEs, CIs are in tables, not prose text
- This is why we had 25% recall and 0% CI extraction

HYPOTHESIS: Including structured table data should dramatically improve:
- Outcome recall (tables contain all measured outcomes)
- Effect size accuracy (tables have exact coefficients/SEs)
- CI extraction (tables have confidence intervals)
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
from html.parser import HTMLParser
from io import StringIO

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


# ============================================================================
# HTML TABLE PARSER
# ============================================================================

class HTMLTableParser(HTMLParser):
    """Parse HTML tables into list of rows (list of cells)."""
    
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
            if self.current_row:  # Only add non-empty rows
                self.current_table.append(self.current_row)
            self.current_row = []
            self.in_row = False
        elif tag == 'table' and self.in_table:
            if self.current_table:  # Only add non-empty tables
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
        
        # Calculate column widths
        num_cols = max(len(row) for row in table) if table else 0
        if num_cols == 0:
            continue
        
        # Normalize rows to have same number of columns
        normalized = []
        for row in table:
            while len(row) < num_cols:
                row.append("")
            normalized.append(row)
        
        # Build markdown table
        md_rows = []
        for i, row in enumerate(normalized):
            md_row = "| " + " | ".join(cell.replace("|", "\\|") for cell in row) + " |"
            md_rows.append(md_row)
            
            # Add separator after first row (header)
            if i == 0:
                separator = "| " + " | ".join("---" for _ in row) + " |"
                md_rows.append(separator)
        
        result.append("\n".join(md_rows))
    
    return "\n\n".join(result)


def extract_tables_from_json(data: Dict) -> List[str]:
    """Extract and convert tables from MineRU JSON output."""
    tables = data.get("tables", [])
    if not tables:
        return []
    
    markdown_tables = []
    for i, table in enumerate(tables):
        table_html = ""
        
        # MineRU format: table_body contains HTML
        if isinstance(table, dict):
            table_html = table.get("table_body", "") or table.get("html", "") or table.get("content", "")
        elif isinstance(table, str):
            table_html = table
        
        if table_html:
            md = html_to_markdown_table(table_html)
            if md:
                markdown_tables.append(f"### Table {i + 1}\n{md}")
    
    return markdown_tables


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


def load_document_with_tables(study_data: Dict) -> Tuple[Optional[str], List[str], int]:
    """
    Load document content AND structured tables from R2.
    
    Returns:
        (content, tables_markdown, num_tables)
    """
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
        
        # Parse JSON
        data = json.loads(json_str)
        
        # Get prose content
        content = data.get("content", "")
        
        # Extract and convert tables
        tables_markdown = extract_tables_from_json(data)
        
        return content, tables_markdown, len(tables_markdown)
        
    except Exception as e:
        print(f"    Error loading document: {e}")
        return None, [], 0


# ============================================================================
# V6: EXTRACTION PROMPT WITH TABLES
# ============================================================================

EXTRACTION_PROMPT = """Extract ALL outcomes and metadata from this academic study on poverty/development interventions.

## DOCUMENT TEXT:
{content}

## STRUCTURED TABLES (EXTRACTED FROM PDF):
{tables}

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

2. OUTCOMES: Extract EVERY outcome from ALL tables above. For EACH outcome:
- outcome_name: What is being measured (be specific, use exact name from table)
- outcome_category: MUST be one of: "Income", "Assets", "Savings", "Expenditure", "Poverty"
- coefficient: Treatment effect coefficient (exact number from table)
- standard_error: Standard error (often in parentheses below coefficient)
- confidence_interval_lower: Lower bound of CI if available
- confidence_interval_upper: Upper bound of CI if available
- t_statistic: t-stat if available
- p_value: p-value if available  
- n_treatment: Treatment group N
- n_control: Control group N
- n_total: Total N
- evidence_location: "Table X" or column header

CRITICAL INSTRUCTIONS:
- The STRUCTURED TABLES section contains the exact data from PDF tables
- Extract EVERY row from EVERY results table
- Copy coefficients and SEs EXACTLY as they appear
- Look for confidence intervals in format [lower, upper] or with separate columns
- If a table has 10 outcomes, extract all 10
- For outcome_category, map outcomes to the closest category:
  * Income: earnings, wages, income, revenue, profits
  * Assets: livestock, equipment, housing, wealth index
  * Savings: savings amounts, savings groups
  * Expenditure: spending, consumption, expenses
  * Poverty: poverty rate, poverty gap, below poverty line

Return ONLY valid JSON:
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
      "evidence_location": "Table 3, Column 2"
    }}
  ]
}}"""


def process_study(study_data: Dict, study_idx: int) -> Dict:
    """Process a single study with table extraction."""
    study_id = study_data.get('study_id', 'unknown')
    ground_truth = study_data.get('ground_truth', {})
    author = ground_truth.get('author', 'Unknown')
    
    print(f"\n[{study_idx}] Processing: {author} (ID: {study_id})")
    
    # Load content AND tables
    content, tables_markdown, num_tables = load_document_with_tables(study_data)
    
    if not content:
        print(f"    ❌ Failed to load document")
        return {"study_id": study_id, "success": False, "error": "Failed to load document"}
    
    print(f"    📄 Loaded: {len(content):,} chars, {num_tables} tables extracted")
    
    # Format tables for prompt
    if tables_markdown:
        tables_section = "\n\n".join(tables_markdown)
    else:
        tables_section = "(No structured tables found in document)"
    
    # Build prompt
    prompt = EXTRACTION_PROMPT.format(
        content=content[:150000],  # Limit content to avoid token issues
        tables=tables_section
    )
    
    print(f"    🤖 Calling LLM ({len(prompt):,} chars)...")
    result = call_llm(prompt, max_tokens=8000)
    
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
        
        # Compute Cohen's d
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
    
    print(f"    ✅ Extracted: {len(processed_outcomes)} outcomes")
    
    # Count CIs extracted
    ci_count = sum(1 for o in processed_outcomes 
                   if o.get("confidence_interval_lower") is not None 
                   and o.get("confidence_interval_upper") is not None)
    if ci_count > 0:
        print(f"    📊 CIs extracted: {ci_count}")
    
    return {
        "study_id": study_id,
        "success": True,
        "metadata": metadata,
        "outcomes": processed_outcomes,
        "num_tables_found": num_tables,
        "ground_truth": ground_truth
    }


def main():
    """Run V6 extraction on all matched studies."""
    print("=" * 70)
    print("EXTRACTION V6 - With Structured Table Data")
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
            
            # Count CIs
            for o in outcomes:
                if o.get("confidence_interval_lower") is not None and o.get("confidence_interval_upper") is not None:
                    total_cis += 1
        
        # Progress every 10
        if idx % 10 == 0:
            print(f"\n--- Progress: {idx}/{len(studies)} ({success_count} successful, {total_outcomes} outcomes, {total_tables} tables, {total_cis} CIs) ---\n")
    
    # Save results
    output_file = "evaluation/extraction_v6_results.json"
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)
    
    print("\n" + "=" * 70)
    print("EXTRACTION V6 COMPLETE")
    print("=" * 70)
    print(f"Studies processed: {len(studies)}")
    print(f"Successful: {success_count}")
    print(f"Total outcomes extracted: {total_outcomes}")
    print(f"Total tables found: {total_tables}")
    print(f"Total CIs extracted: {total_cis}")
    print(f"Results saved to: {output_file}")


if __name__ == "__main__":
    main()
