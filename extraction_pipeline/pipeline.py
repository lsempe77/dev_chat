"""
Pipeline V2 SOTA: Production-Ready Extraction for Impact Evaluation Papers

Features:
- Stage 1: Metadata extraction (direct from MineRU JSON)
- Stage 2: Table extraction (BeautifulSoup + rules-based filtering)
- Stage 3: LLM classification for ambiguous tables
- Stage 4: Context enrichment (LLM for outcome definitions)

Usage:
    python pipeline_v2_sota.py                    # Extract study 121058356
    python pipeline_v2_sota.py --study_id 12345   # Extract specific study
    python pipeline_v2_sota.py --all              # Extract all studies
"""

import json
import re
import os
import sys
import argparse
from typing import Optional, List, Dict, Any
from bs4 import BeautifulSoup
import pandas as pd
import boto3
from dotenv import load_dotenv
from openai import OpenAI

# Load environment variables
load_dotenv()

# Add src to path for settings
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from src.config.settings import Settings

# Initialize settings
settings = Settings()

# ============================================================================
# CONFIGURATION
# ============================================================================

DEFAULT_STUDY_ID = "121058356"
OUTPUT_DIR = "extraction_pipeline/outputs"

# LLM Configuration (via OpenRouter)
LLM_MODEL = "anthropic/claude-3.5-haiku"  # Cost-effective, fast model

# ============================================================================
# LLM CLIENT (via OpenRouter)
# ============================================================================

def get_openrouter_client():
    """Get OpenRouter client (uses OpenAI-compatible API)."""
    api_key = os.environ.get('OPENROUTER_API_KEY', settings.openrouter_api_key)
    return OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key
    )


def call_llm(prompt: str, max_tokens: int = 100) -> str:
    """Call LLM via OpenRouter."""
    try:
        client = get_openrouter_client()
        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=max_tokens
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"    [LLM ERROR] {e}")
        return ""

# ============================================================================
# R2 STORAGE
# ============================================================================

def get_r2_client():
    """Get R2 storage client."""
    return boto3.client(
        's3',
        endpoint_url=f"https://{os.environ['CLOUDFLARE_ACCOUNT_ID']}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ['R2_ACCESS_KEY_ID'],
        aws_secret_access_key=os.environ['R2_SECRET_ACCESS_KEY']
    )


def load_mineru_json(study_id: str) -> Optional[dict]:
    """Load MineRU JSON from R2 storage."""
    try:
        client = get_r2_client()
        key = f"rags/0816e8d3-ab23-417c-bf3f-e45531411c73/outputs/json/8d23199222c8_PDFs_of_included_programs_{study_id}.json"
        response = client.get_object(Bucket='devchat-pdfs', Key=key)
        return json.loads(response['Body'].read().decode('utf-8'))
    except Exception as e:
        print(f"  [ERROR] Failed to load study {study_id}: {e}")
        return None

# ============================================================================
# STAGE 1: METADATA EXTRACTION
# ============================================================================

def extract_metadata(doc: dict, study_id: str) -> dict:
    """Extract paper metadata directly from MineRU JSON."""
    return {
        'study_id': study_id,
        'title': doc.get('title', ''),
        'authors': doc.get('authors', []),
        'year': doc.get('year', ''),
        'abstract': doc.get('abstract', ''),
        'page_count': doc.get('page_count', 0),
        'source_key': doc.get('source_key', '')
    }

# ============================================================================
# STAGE 2: TABLE CLASSIFICATION
# ============================================================================

def classify_table_rules(caption: str) -> str:
    """
    Rules-based table classification.
    Returns: 'results', 'descriptive', 'figure', or 'unknown'
    """
    # Normalize: remove extra spaces (handles OCR like "Ta b l e 5")
    caption_normalized = re.sub(r'\s+', '', caption.lower())
    caption_lower = caption.lower().strip()
    
    # Rule 1: Figure
    if re.search(r'figure\s*\d', caption_lower) or caption_normalized.startswith('figure'):
        return 'figure'
    
    # Rule 2: Empty caption
    if not caption_lower.strip():
        return 'unknown'
    
    # Rule 3: Descriptive/definition tables
    descriptive_keywords = ['balance', 'baseline', 'attrition', 'compliance', 
                           'definition', 'construction', 'variable', 'hypothesis',
                           'summary statistics', 'sample characteristics']
    if any(kw in caption_normalized for kw in descriptive_keywords):
        return 'descriptive'
    
    # Rule 4: Has "table" in caption → likely results
    if 'table' in caption_normalized:
        return 'results'
    
    return 'unknown'


def classify_table_llm(caption: str, html_preview: str) -> str:
    """
    LLM-based table classification for ambiguous cases.
    """
    prompt = f"""You are classifying tables from an academic impact evaluation paper.

TASK: Does this table contain TREATMENT EFFECTS (regression coefficients with standard errors)?

Classification:
- "results": Contains regression coefficients, treatment effects, impact estimates with standard errors in parentheses like "0.15*** (0.05)"
- "descriptive": Contains summary statistics, means, balance tests, variable definitions, sample characteristics

Caption: {caption if caption else "[No caption]"}

Table HTML preview:
{html_preview[:800]}

Reply with ONLY one word: results or descriptive"""

    result = call_llm(prompt, max_tokens=10)
    if result.lower() in ['results', 'descriptive']:
        return result.lower()
    return 'results'  # Default to extracting


def classify_table(caption: str, html: str, use_llm: bool = True) -> str:
    """
    Classify table using rules first, then LLM for ambiguous cases.
    """
    # First try rules-based
    rules_result = classify_table_rules(caption)
    
    if rules_result in ['figure', 'descriptive', 'results']:
        return rules_result
    
    # For 'unknown', use LLM if enabled
    if use_llm and rules_result == 'unknown':
        return classify_table_llm(caption, html)
    
    return 'results'  # Default to extracting

# ============================================================================
# STAGE 3: TABLE PARSING (BeautifulSoup)
# ============================================================================

def parse_coefficient_se(cell_text: str) -> tuple:
    """
    Parse coefficient and SE from cell text.
    Handles: "0.15*** (0.05)", "(0.04) 0.18***", "0.12***"
    Returns: (coefficient, standard_error, significance)
    """
    if not cell_text or cell_text.strip() == "":
        return None, None, None
    
    text = cell_text.strip()
    
    # Extract significance stars
    stars = ""
    if "***" in text:
        stars = "***"
    elif "**" in text and "***" not in text:
        stars = "**"
    elif "*" in text and "**" not in text:
        stars = "*"
    
    # Find coefficient and SE
    paren_match = re.search(r'\(([^)]+)\)', text)
    if paren_match:
        paren_content = paren_match.group(1)
        paren_nums = re.findall(r'-?\d+\.?\d*', paren_content)
        if paren_nums:
            se = float(paren_nums[0])
            # Find coefficient (number not in parentheses)
            non_paren_text = re.sub(r'\([^)]+\)', '', text)
            non_paren_nums = re.findall(r'-?\d+\.?\d*', non_paren_text)
            if non_paren_nums:
                coef = float(non_paren_nums[0])
                return coef, se, stars
    
    # Fallback: just find numbers
    numbers = re.findall(r'-?\d+\.?\d*', text)
    if len(numbers) >= 1:
        return float(numbers[0]), None, stars
    
    return None, None, None


def extract_results_table(table: dict, study_id: str) -> List[Dict[str, Any]]:
    """
    Extract all data cells from a results table.
    Returns list of dicts, one per extracted value.
    """
    caption = ' '.join(table.get('table_caption', []))
    html = table.get('table_body', '')
    page_idx = table.get('page_idx', 0)
    
    # Parse table number from caption
    caption_normalized = re.sub(r'\s+', '', caption)
    table_num_match = re.search(r'[Tt]able\s*[A.]?(\d+)', caption_normalized)
    table_number = table_num_match.group(0) if table_num_match else None
    
    soup = BeautifulSoup(html, 'html.parser')
    rows = soup.find_all('tr')
    
    if not rows:
        return []
    
    # Parse header to get outcome names
    header_row = rows[0]
    header_cells = header_row.find_all('td')
    outcome_names = []
    for cell in header_cells[1:]:  # Skip first (empty or row label header)
        text = cell.get_text(strip=True)
        if text:
            # Clean column numbers like "(1) Gross consumption" -> "Gross consumption"
            match = re.match(r'\(?\d+\)?\s*(.+)', text)
            if match:
                outcome_names.append(match.group(1).strip())
            else:
                outcome_names.append(text)
    
    if not outcome_names:
        return []
    
    results = []
    current_section = None
    
    # First pass: collect metadata by section
    observations_by_section = {}
    control_means_by_section = {}
    control_sds_by_section = {}
    current_section_pass1 = None
    
    for row in rows[1:]:
        cells = row.find_all('td')
        if not cells:
            continue
        first_cell = cells[0].get_text(strip=True)
        first_cell_lower = first_cell.lower()
        
        # Track section
        if 'followup' in first_cell_lower or 'follow-up' in first_cell_lower:
            current_section_pass1 = first_cell
            if current_section_pass1 not in observations_by_section:
                observations_by_section[current_section_pass1] = {}
                control_means_by_section[current_section_pass1] = {}
                control_sds_by_section[current_section_pass1] = {}
        
        if 'observation' in first_cell_lower:
            for i, cell in enumerate(cells[1:]):
                if i < len(outcome_names):
                    nums = re.findall(r'\d+', cell.get_text(strip=True))
                    if nums and current_section_pass1:
                        observations_by_section[current_section_pass1][outcome_names[i]] = int(nums[0])
        
        elif 'control mean' in first_cell_lower:
            for i, cell in enumerate(cells[1:]):
                if i < len(outcome_names):
                    nums = re.findall(r'-?\d+\.?\d*', cell.get_text(strip=True))
                    if nums and current_section_pass1:
                        control_means_by_section[current_section_pass1][outcome_names[i]] = float(nums[0])
        
        elif 'control sd' in first_cell_lower:
            for i, cell in enumerate(cells[1:]):
                if i < len(outcome_names):
                    nums = re.findall(r'-?\d+\.?\d*', cell.get_text(strip=True))
                    if nums and current_section_pass1:
                        control_sds_by_section[current_section_pass1][outcome_names[i]] = float(nums[0])
    
    # Second pass: extract treatment effects
    treatment_arms = ['Capital', 'Psychosocial', 'Full', 'Treatment', 'Treated', 'Program']
    
    for row_idx, row in enumerate(rows[1:], start=1):
        cells = row.find_all('td')
        if not cells:
            continue
        
        first_cell_text = cells[0].get_text(strip=True)
        first_cell_lower = first_cell_text.lower()
        
        # Check for section header (followup period)
        if 'followup' in first_cell_lower or 'follow-up' in first_cell_lower:
            current_section = first_cell_text
            continue
        
        # Check for treatment arm row
        if first_cell_text in treatment_arms:
            treatment_arm = first_cell_text
            
            # Look ahead for SE values in next row (handles split format)
            next_row = rows[row_idx + 1] if row_idx + 1 < len(rows) else None
            se_from_next = {}
            if next_row:
                next_cells = next_row.find_all('td')
                for ni, nc in enumerate(next_cells[1:]):
                    if ni >= len(outcome_names):
                        break
                    nc_text = nc.get_text(strip=True)
                    lead_paren = re.match(r'^\(([\d.]+)\)', nc_text)
                    if lead_paren:
                        se_from_next[ni] = float(lead_paren.group(1))
            
            # Extract values for each outcome
            for i, cell in enumerate(cells[1:]):
                if i >= len(outcome_names):
                    break
                
                cell_text = cell.get_text(strip=True)
                coef, se, stars = parse_coefficient_se(cell_text)
                
                # Use SE from next row if needed
                if se is None and i in se_from_next:
                    se = se_from_next[i]
                
                # Get section-specific metadata
                obs = observations_by_section.get(current_section, {}).get(outcome_names[i])
                ctrl_mean = control_means_by_section.get(current_section, {}).get(outcome_names[i])
                ctrl_sd = control_sds_by_section.get(current_section, {}).get(outcome_names[i])
                
                if coef is not None:
                    results.append({
                        'study_id': study_id,
                        'table_number': table_number,
                        'table_caption': caption,
                        'page_number': page_idx + 1,
                        'section': current_section,
                        'treatment_arm': treatment_arm,
                        'outcome_name': outcome_names[i],
                        'coefficient': coef,
                        'standard_error': se,
                        'significance': stars,
                        'sample_size': obs,
                        'control_mean': ctrl_mean,
                        'control_sd': ctrl_sd,
                        'literal_cell_text': cell_text
                    })
    
    return results

# ============================================================================
# STAGE 4: CONTEXT ENRICHMENT (LLM)
# ============================================================================

def enrich_with_context(df: pd.DataFrame, doc: dict) -> pd.DataFrame:
    """Use LLM to enrich extracted data with outcome definitions."""
    if df.empty:
        return df
    
    # Get unique outcomes
    outcomes = df['outcome_name'].unique().tolist()[:15]  # Limit to 15
    prose = doc.get('content', '')[:20000]  # First 20k chars
    
    prompt = f"""Given this paper excerpt and list of outcome variables, provide brief definitions.

OUTCOME VARIABLES:
{chr(10).join(f'- {o}' for o in outcomes)}

PAPER TEXT:
{prose[:15000]}

For each outcome, provide a one-sentence definition based on the paper.
Format each line as: outcome_name|definition

Only include outcomes you can find definitions for in the text."""

    result = call_llm(prompt, max_tokens=1000)
    
    definitions = {}
    for line in result.split('\n'):
        if '|' in line:
            parts = line.split('|', 1)
            if len(parts) == 2:
                definitions[parts[0].strip()] = parts[1].strip()
    
    # Add definitions to dataframe
    df['outcome_definition'] = df['outcome_name'].map(
        lambda x: next((v for k, v in definitions.items() if k.lower() in x.lower()), None)
    )
    
    print(f"    Added definitions for {len(definitions)} outcomes")
    
    return df

# ============================================================================
# MAIN PIPELINE
# ============================================================================

def extract_all_tables(doc: dict, study_id: str, use_llm: bool = True) -> pd.DataFrame:
    """Extract data from all results tables in the document."""
    tables = doc.get('tables', [])
    all_results = []
    
    print(f"\n  Found {len(tables)} tables in document")
    
    tables_extracted = 0
    tables_skipped = 0
    
    for i, table in enumerate(tables):
        caption = ' '.join(table.get('table_caption', []))
        html = table.get('table_body', '')
        
        # Classify table
        table_type = classify_table(caption, html, use_llm=use_llm)
        
        if table_type == 'results':
            results = extract_results_table(table, study_id)
            if results:
                all_results.extend(results)
                print(f"    Table {i}: {caption[:50]}... → {len(results)} rows")
                tables_extracted += 1
        else:
            tables_skipped += 1
    
    print(f"\n  Tables: {tables_extracted} extracted, {tables_skipped} skipped")
    
    return pd.DataFrame(all_results)


def run_pipeline(study_id: str, use_llm: bool = True, enrich: bool = True) -> tuple:
    """Run the full extraction pipeline for a single study."""
    
    print("=" * 70)
    print(f"PIPELINE V2 SOTA: Extracting study {study_id}")
    print("=" * 70)
    
    # Create output directory
    study_output_dir = f"{OUTPUT_DIR}/{study_id}"
    os.makedirs(study_output_dir, exist_ok=True)
    
    # Stage 0: Load data
    print("\n[STAGE 0] Loading MineRU JSON from R2...")
    doc = load_mineru_json(study_id)
    if not doc:
        return None, pd.DataFrame()
    print(f"  ✓ Loaded: {len(doc.get('tables', []))} tables, {len(doc.get('content', ''))} chars")
    
    # Stage 1: Metadata
    print("\n[STAGE 1] Extracting metadata...")
    metadata = extract_metadata(doc, study_id)
    print(f"  ✓ Title: {metadata['title'][:60]}...")
    print(f"  ✓ Year: {metadata['year']}")
    
    with open(f"{study_output_dir}/metadata.json", 'w') as f:
        json.dump(metadata, f, indent=2)
    
    # Stage 2 & 3: Table extraction with classification
    print("\n[STAGE 2] Extracting tables (BeautifulSoup + LLM classification)...")
    df = extract_all_tables(doc, study_id, use_llm=use_llm)
    
    if not df.empty:
        print(f"\n  ✓ Total rows: {len(df)}")
        print(f"  ✓ Unique outcomes: {df['outcome_name'].nunique()}")
        print(f"  ✓ Tables with data: {df['table_number'].nunique()}")
        print(f"  ✓ Coefficient coverage: {100*df['coefficient'].notna().mean():.1f}%")
        print(f"  ✓ SE coverage: {100*df['standard_error'].notna().mean():.1f}%")
    
    # Stage 4: Context enrichment (optional)
    if enrich and not df.empty:
        print("\n[STAGE 4] Enriching with LLM context...")
        df = enrich_with_context(df, doc)
    
    # Save results
    if not df.empty:
        df.to_csv(f"{study_output_dir}/extracted_data.csv", index=False)
        df.to_json(f"{study_output_dir}/extracted_data.json", orient='records', indent=2)
        print(f"\n  ✓ Saved to {study_output_dir}/")
    
    # Summary
    print("\n" + "=" * 70)
    print("EXTRACTION COMPLETE")
    print("=" * 70)
    
    return metadata, df


def main():
    parser = argparse.ArgumentParser(description='Extract impact evaluation data from papers')
    parser.add_argument('--study_id', type=str, default=DEFAULT_STUDY_ID, help='Study ID to extract')
    parser.add_argument('--no-llm', action='store_true', help='Disable LLM classification')
    parser.add_argument('--no-enrich', action='store_true', help='Disable LLM enrichment')
    
    args = parser.parse_args()
    
    metadata, df = run_pipeline(
        study_id=args.study_id,
        use_llm=not args.no_llm,
        enrich=not args.no_enrich
    )
    
    if not df.empty:
        print(f"\nSample output:")
        print(df[['table_number', 'treatment_arm', 'outcome_name', 'coefficient', 'standard_error']].head(10).to_string())


if __name__ == "__main__":
    main()
