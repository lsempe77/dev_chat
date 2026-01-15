"""
Pipeline V2: Unified Extraction for Impact Evaluation Papers
Test on Bossuroy (121058356)

Stages:
1. Metadata extraction (direct from JSON)
2. Table extraction (BeautifulSoup)
3. Context enrichment (LLM on prose) - optional
"""

import json
import re
import os
from bs4 import BeautifulSoup
import pandas as pd
import boto3
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

# ============================================================================
# CONFIGURATION
# ============================================================================

STUDY_ID = "121058356"
OUTPUT_DIR = "extraction_pipeline/outputs/121058356"
USE_LLM_CLASSIFICATION = True  # Set to True to use LLM for unknown tables

# ============================================================================
# STAGE 0: LOAD MINERU JSON
# ============================================================================

def load_mineru_json(study_id: str) -> dict:
    """Load MineRU JSON from R2 storage."""
    client = boto3.client(
        's3',
        endpoint_url=f"https://{os.environ['CLOUDFLARE_ACCOUNT_ID']}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ['R2_ACCESS_KEY_ID'],
        aws_secret_access_key=os.environ['R2_SECRET_ACCESS_KEY']
    )
    
    key = f"rags/0816e8d3-ab23-417c-bf3f-e45531411c73/outputs/json/8d23199222c8_PDFs_of_included_programs_{study_id}.json"
    response = client.get_object(Bucket='devchat-pdfs', Key=key)
    return json.loads(response['Body'].read().decode('utf-8'))

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
# STAGE 2: TABLE EXTRACTION (BeautifulSoup)
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


def identify_table_type(caption: str, use_llm: bool = False, html_preview: str = None) -> str:
    """
    Identify table type from caption using rules-based approach.
    Falls back to LLM for unknown captions if use_llm=True.
    
    Since MineRU already identifies tables (type='table'), we just need to:
    1. Skip figures
    2. Identify descriptive/definition tables (skip)
    3. Everything else → EXTRACT (including appendix)
    """
    # Normalize: remove extra spaces (handles OCR like "Ta b l e 5")
    caption_normalized = re.sub(r'\s+', '', caption.lower())
    caption_lower = caption.lower().strip()
    
    # Rule 1: Figure
    if re.search(r'figure\s*\d', caption_lower) or caption_normalized.startswith('figure'):
        return 'figure'
    
    # Rule 2: Empty caption - try to extract anyway (MineRU says it's a table)
    if not caption_lower.strip():
        if use_llm and html_preview:
            return classify_table_with_llm(caption, html_preview)
        return 'results'  # Default to extracting since MineRU identified it as table
    
    # Rule 3: Descriptive/definition tables (less useful for effect sizes)
    descriptive_keywords = ['balance', 'baseline', 'attrition', 'compliance', 
                           'definition', 'construction', 'variable', 'hypothesis']
    if any(kw in caption_normalized for kw in descriptive_keywords):
        return 'descriptive'
    
    # Rule 4: Everything else with "table" in caption → extract (including appendix!)
    if 'table' in caption_normalized:
        return 'results'
    
    # Rule 5: Unknown caption - use LLM if enabled, otherwise try to extract
    if use_llm and html_preview:
        return classify_table_with_llm(caption, html_preview)
    
    # Default: try to extract since MineRU identified it as a table
    return 'results'


def classify_table_with_llm(caption: str, html_preview: str) -> str:
    """Use LLM to classify a table when rules-based approach is uncertain."""
    try:
        client = OpenAI()
        
        prompt = f"""You are classifying tables from an academic impact evaluation paper.

TASK: Does this table contain TREATMENT EFFECTS (coefficients, standard errors, p-values)?

- "results": YES - Contains regression coefficients, treatment effects, impact estimates with standard errors
- "descriptive": NO - Contains summary statistics, balance tests, variable definitions, sample characteristics

Caption: {caption}

Table HTML (first 500 chars):
{html_preview[:500]}

Look for patterns like:
- "0.15*** (0.05)" = coefficient with SE → results
- "Mean: 2.5, SD: 1.2" = summary stats → descriptive
- Treatment arm names (Capital, Control, Treatment) with numbers → results

Reply with ONLY one word: results or descriptive"""

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=10
        )
        
        result = response.choices[0].message.content.strip().lower()
        if result in ['results', 'descriptive']:
            return result
        return 'results'  # Default to extracting
        
    except Exception as e:
        print(f"    LLM classification failed: {e}")
        return 'results'  # Default to extracting


def detect_table_structure(soup: BeautifulSoup, caption: str) -> dict:
    """
    Detect the structure of a results table.
    Returns dict with: outcome_orientation, treatment_arms, followup_periods
    """
    rows = soup.find_all('tr')
    if not rows:
        return None
    
    # Get all text from first column (row labels)
    row_labels = []
    for row in rows:
        cells = row.find_all('td')
        if cells:
            row_labels.append(cells[0].get_text(strip=True))
    
    # Get header row (column labels)
    header_cells = rows[0].find_all('td') if rows else []
    col_labels = [c.get_text(strip=True) for c in header_cells]
    
    # Detect treatment arms
    treatment_keywords = ['capital', 'psychosocial', 'full', 'treatment', 'control', 
                          'intervention', 'placebo', 'arm', 'group']
    arms_in_rows = [l for l in row_labels if any(kw in l.lower() for kw in treatment_keywords)]
    arms_in_cols = [l for l in col_labels if any(kw in l.lower() for kw in treatment_keywords)]
    
    # Detect followup periods
    followup_keywords = ['followup', 'follow-up', 'month', 'year', 'wave', 'round', 'endline', 'midline']
    followups_in_rows = [l for l in row_labels if any(kw in l.lower() for kw in followup_keywords)]
    
    # Detect outcomes
    # If treatment arms are in rows, outcomes are likely in columns
    if len(arms_in_rows) > len(arms_in_cols):
        outcome_orientation = 'columns'
        treatment_orientation = 'rows'
    else:
        outcome_orientation = 'rows'
        treatment_orientation = 'columns'
    
    return {
        'outcome_orientation': outcome_orientation,
        'treatment_orientation': treatment_orientation,
        'detected_arms': arms_in_rows if arms_in_rows else arms_in_cols,
        'detected_followups': followups_in_rows,
        'header_labels': col_labels,
        'row_labels': row_labels[:10]  # First 10 for debugging
    }


def extract_results_table(table: dict, study_id: str) -> list:
    """
    Extract all data cells from a results table.
    Returns list of dicts, one per extracted value.
    """
    caption = ' '.join(table.get('table_caption', []))
    html = table.get('table_body', '')
    page_idx = table.get('page_idx', 0)
    
    # Parse table number from caption
    table_num_match = re.search(r'Table\s*(\d+)', caption, re.IGNORECASE)
    table_number = int(table_num_match.group(1)) if table_num_match else None
    
    soup = BeautifulSoup(html, 'html.parser')
    rows = soup.find_all('tr')
    
    if not rows:
        return []
    
    # Detect structure
    structure = detect_table_structure(soup, caption)
    if not structure:
        return []
    
    # Parse header to get outcome names (assumes outcomes in columns)
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
    
    results = []
    current_section = None  # For followup periods or other groupings
    
    # First pass: collect metadata rows (observations, control mean/sd) by section by section
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
    treatment_arms = ['Capital', 'Psychosocial', 'Full', 'Treatment', 'Treated']
    
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
                
                if coef is not None:
                    # Get section-specific metadata
                    obs = observations_by_section.get(current_section, {}).get(outcome_names[i])
                    ctrl_mean = control_means_by_section.get(current_section, {}).get(outcome_names[i])
                    ctrl_sd = control_sds_by_section.get(current_section, {}).get(outcome_names[i])
                    
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


def extract_all_tables(doc: dict, study_id: str, use_llm_classification: bool = False) -> pd.DataFrame:
    """Extract data from all results tables in the document."""
    tables = doc.get('tables', [])
    all_results = []
    
    print(f"\nFound {len(tables)} tables in document")
    
    for i, table in enumerate(tables):
        caption = ' '.join(table.get('table_caption', []))
        html = table.get('table_body', '')
        
        # Identify table type (with optional LLM fallback)
        table_type = identify_table_type(caption, use_llm=use_llm_classification, html_preview=html)
        
        if table_type == 'results':
            print(f"  Table {i}: {caption[:60]}... [RESULTS - extracting]")
            results = extract_results_table(table, study_id)
            all_results.extend(results)
            print(f"    → Extracted {len(results)} rows")
        else:
            print(f"  Table {i}: {caption[:60]}... [{table_type} - skipping]")
    
    return pd.DataFrame(all_results)

# ============================================================================
# STAGE 3: CONTEXT ENRICHMENT (LLM)
# ============================================================================

def enrich_with_context(df: pd.DataFrame, doc: dict) -> pd.DataFrame:
    """Use LLM to enrich extracted data with context from prose."""
    if df.empty:
        return df
    
    # Get unique outcomes
    outcomes = df['outcome_name'].unique().tolist()
    prose = doc.get('content', '')[:15000]  # First 15k chars
    
    client = OpenAI()
    
    prompt = f"""Given this paper excerpt and list of outcome variables, provide brief definitions.

OUTCOME VARIABLES:
{chr(10).join(f'- {o}' for o in outcomes[:10])}

PAPER TEXT:
{prose}

For each outcome, provide a one-sentence definition based on the paper.
Format: outcome_name|definition

Only include outcomes you can find definitions for."""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )
        
        definitions = {}
        for line in response.choices[0].message.content.strip().split('\n'):
            if '|' in line:
                parts = line.split('|', 1)
                if len(parts) == 2:
                    definitions[parts[0].strip()] = parts[1].strip()
        
        # Add definitions to dataframe
        df['outcome_definition'] = df['outcome_name'].map(
            lambda x: next((v for k, v in definitions.items() if k.lower() in x.lower()), None)
        )
        
        print(f"\n  Added definitions for {len(definitions)} outcomes")
        
    except Exception as e:
        print(f"\n  Warning: Could not enrich with LLM: {e}")
        df['outcome_definition'] = None
    
    return df

# ============================================================================
# MAIN PIPELINE
# ============================================================================

def run_pipeline(study_id: str, run_stage3: bool = True):
    """Run the full extraction pipeline."""
    
    print("=" * 70)
    print(f"PIPELINE V2: Extracting study {study_id}")
    print("=" * 70)
    
    # Create output directory
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # Stage 0: Load data
    print("\n[STAGE 0] Loading MineRU JSON...")
    doc = load_mineru_json(study_id)
    print(f"  Loaded document with {len(doc.get('tables', []))} tables, {len(doc.get('content', ''))} chars")
    
    # Stage 1: Metadata
    print("\n[STAGE 1] Extracting metadata...")
    metadata = extract_metadata(doc, study_id)
    print(f"  Title: {metadata['title'][:60]}...")
    print(f"  Authors: {metadata['authors'][:3]}...")
    print(f"  Year: {metadata['year']}")
    
    with open(f"{OUTPUT_DIR}/metadata.json", 'w') as f:
        json.dump(metadata, f, indent=2)
    print(f"  Saved to {OUTPUT_DIR}/metadata.json")
    
    # Stage 2: Tables
    print("\n[STAGE 2] Extracting tables with BeautifulSoup...")
    df = extract_all_tables(doc, study_id, use_llm_classification=USE_LLM_CLASSIFICATION)
    print(f"\n  Total rows extracted: {len(df)}")
    
    if not df.empty:
        print(f"  Unique outcomes: {df['outcome_name'].nunique()}")
        print(f"  Unique treatment arms: {df['treatment_arm'].nunique()}")
        print(f"  Tables processed: {df['table_number'].nunique()}")
    
    # Stage 3: Context (optional)
    if run_stage3 and not df.empty:
        print("\n[STAGE 3] Enriching with LLM context...")
        df = enrich_with_context(df, doc)
    
    # Save results
    if not df.empty:
        df.to_csv(f"{OUTPUT_DIR}/extracted_data.csv", index=False)
        print(f"\n  Saved to {OUTPUT_DIR}/extracted_data.csv")
        
        # Also save as JSON for inspection
        df.to_json(f"{OUTPUT_DIR}/extracted_data.json", orient='records', indent=2)
    
    # Summary
    print("\n" + "=" * 70)
    print("EXTRACTION SUMMARY")
    print("=" * 70)
    print(f"Study ID: {study_id}")
    print(f"Tables found: {len(doc.get('tables', []))}")
    print(f"Results tables processed: {df['table_number'].nunique() if not df.empty else 0}")
    print(f"Total rows extracted: {len(df)}")
    print(f"Coefficient coverage: {df['coefficient'].notna().sum()}/{len(df)} ({100*df['coefficient'].notna().mean():.1f}%)" if not df.empty else "N/A")
    print(f"SE coverage: {df['standard_error'].notna().sum()}/{len(df)} ({100*df['standard_error'].notna().mean():.1f}%)" if not df.empty else "N/A")
    
    return metadata, df


if __name__ == "__main__":
    metadata, df = run_pipeline(STUDY_ID, run_stage3=False)  # Skip LLM for now
    
    # Show sample of extracted data
    if not df.empty:
        print("\n" + "=" * 70)
        print("SAMPLE EXTRACTED DATA (first 10 rows)")
        print("=" * 70)
        pd.set_option('display.max_columns', None)
        pd.set_option('display.width', None)
        print(df[['table_number', 'section', 'treatment_arm', 'outcome_name', 'coefficient', 'standard_error', 'sample_size']].head(10).to_string(index=False))
