"""
New Extraction Approach v1: Parse multi-dimensional tables properly

Key insight from MineRU output:
- Table 1 has HTML structure with all 18 cells (3 outcomes × 3 arms × 2 followups)
- We can parse the HTML directly to extract each cell
- No LLM needed for this structured table!

This approach:
1. Parse HTML table directly (no LLM collapse)
2. Track page_idx from MineRU
3. Track table_caption (literal text)
4. Extract each cell as a separate row
"""

import json
import re
from bs4 import BeautifulSoup
import pandas as pd
import boto3
import os
from dotenv import load_dotenv

load_dotenv()

def load_mineru_json(study_id: str = "121058356"):
    """Load MineRU JSON for Bossuroy paper"""
    client = boto3.client(
        's3',
        endpoint_url=f"https://{os.environ['CLOUDFLARE_ACCOUNT_ID']}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ['R2_ACCESS_KEY_ID'],
        aws_secret_access_key=os.environ['R2_SECRET_ACCESS_KEY']
    )
    
    key = f"rags/0816e8d3-ab23-417c-bf3f-e45531411c73/outputs/json/8d23199222c8_PDFs_of_included_programs_{study_id}.json"
    response = client.get_object(Bucket='devchat-pdfs', Key=key)
    return json.loads(response['Body'].read().decode('utf-8'))


def parse_coefficient_se(cell_text: str) -> tuple:
    """
    Parse coefficient and SE from cell text like:
    "0.15*** (0.05)" -> (0.15, 0.05, "***")
    "0.09* (0.05)" -> (0.09, 0.05, "*")
    "-18.01 (16.11)" -> (-18.01, 16.11, "")
    """
    if not cell_text or cell_text.strip() == "":
        return None, None, None
    
    # Pattern: number (possibly negative), optional stars, then (SE)
    # Handle cases like "0.15*** (0.05)" or "0.12***" or "(0.04) 0.18***"
    
    # First, clean up the text
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
    # Pattern for coefficient with optional stars and SE in parentheses
    # Could be: "0.15*** (0.05)" or "(0.04) 0.18***" (two-line format)
    
    numbers = re.findall(r'-?\d+\.?\d*', text)
    
    if len(numbers) >= 2:
        # First number is coefficient, second is SE (usually)
        # But handle two-line format where SE comes first in parentheses
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
        
        # Fallback: first is coef, second is SE
        return float(numbers[0]), float(numbers[1]), stars
    elif len(numbers) == 1:
        return float(numbers[0]), None, stars
    
    return None, None, None


def find_table_by_caption(tables: list, caption_pattern: str) -> dict:
    """Find a table by caption pattern"""
    for table in tables:
        caption = table.get('table_caption', [])
        if caption and caption_pattern.lower() in str(caption).lower():
            return table
    return None


def extract_table1_primary_outcomes(doc: dict) -> pd.DataFrame:
    """
    Extract Table 1: Primary Outcomes with proper multi-dimensional structure.
    
    Expected structure:
    - 3 outcomes: Gross consumption, Food security, Food consumption
    - 3 treatment arms: Capital, Psychosocial, Full
    - 2 followup periods: 6 months, 18 months
    = 18 rows total
    """
    tables = doc.get('tables', [])
    
    # Find Table 1 by caption
    table1 = find_table_by_caption(tables, "Table 1")
    if not table1:
        print("Table 1 not found!")
        return pd.DataFrame()
    
    print(f"Found Table 1 on page {table1.get('page_idx', 'unknown') + 1}")
    print(f"Caption: {table1.get('table_caption', [])}")
    
    # Parse HTML
    html = table1.get('table_body', '')
    soup = BeautifulSoup(html, 'html.parser')
    
    # Extract all rows
    rows = soup.find_all('tr')
    
    # Parse header to get outcome names
    header_row = rows[0] if rows else None
    outcome_names = []
    if header_row:
        cells = header_row.find_all('td')
        for cell in cells[1:]:  # Skip first empty cell
            text = cell.get_text(strip=True)
            if text:
                # Extract just the outcome name (remove column number)
                match = re.match(r'\(?\d+\)?\s*(.+)', text)
                if match:
                    outcome_names.append(match.group(1).strip())
                else:
                    outcome_names.append(text)
    
    print(f"Outcome names from header: {outcome_names}")
    
    # Storage for observations by outcome
    observations_followup1 = {}
    observations_followup2 = {}
    
    # First pass: collect observations
    current_followup = None
    for row in rows:
        cells = row.find_all('td')
        if not cells:
            continue
        first_cell = cells[0].get_text(strip=True)
        
        if "followup 1" in first_cell.lower():
            current_followup = 1
        elif "followup 2" in first_cell.lower():
            current_followup = 2
        elif "observations" in first_cell.lower():
            for i, cell in enumerate(cells[1:]):
                if i >= len(outcome_names):
                    break
                cell_text = cell.get_text(strip=True)
                obs_match = re.search(r'(\d+)', cell_text)
                if obs_match:
                    if current_followup == 1:
                        observations_followup1[outcome_names[i]] = int(obs_match.group(1))
                    elif current_followup == 2:
                        observations_followup2[outcome_names[i]] = int(obs_match.group(1))
    
    # Second pass: extract data with SE from next row if needed
    # Special handling for Followup 2 where Capital row lacks SE
    # and SE appears in the parentheses at the start of the next row
    results = []
    current_followup = None
    
    # Store SE values from next row that belong to current row
    # Pattern: "(0.04) 0.18***" means 0.04 is SE for prev row, 0.18 is coef for current
    
    for idx, row in enumerate(rows[1:], start=1):  # Skip header
        cells = row.find_all('td')
        if not cells:
            continue
        
        first_cell = cells[0].get_text(strip=True)
        
        # Check for followup period marker
        if "followup 1" in first_cell.lower():
            current_followup = "Followup 1 (6 months)"
            continue
        elif "followup 2" in first_cell.lower():
            current_followup = "Followup 2 (18 months)"
            continue
        
        # Check for treatment arm
        if first_cell in ["Capital", "Psychosocial", "Full"]:
            treatment_arm = first_cell
            
            # Look at next row to get SE for this row if format is split
            next_row = rows[idx + 1] if idx + 1 < len(rows) else None
            se_from_next_row = {}
            
            if next_row:
                next_cells = next_row.find_all('td')
                if next_cells:
                    for ni, nc in enumerate(next_cells[1:]):  # Skip first cell
                        if ni >= len(outcome_names):
                            break
                        nc_text = nc.get_text(strip=True)
                        # Pattern: "(0.04) 0.18***" - extract 0.04 as SE for current row
                        lead_paren = re.match(r'^\(([\d.]+)\)', nc_text)
                        if lead_paren:
                            se_from_next_row[ni] = float(lead_paren.group(1))
            
            # Also check if there's a pure SE row (just "(0.05)" format) 
            # This happens for the Full row in Followup 2
            next_row2 = rows[idx + 1] if idx + 1 < len(rows) else None
            if next_row2:
                next_cells2 = next_row2.find_all('td')
                if next_cells2:
                    next_first2 = next_cells2[0].get_text(strip=True)
                    # Check if it's an empty first cell (SE row) or treatment arm
                    if next_first2 == "" or re.match(r'^\([\d.]+\)', next_first2):
                        for ni, nc in enumerate(next_cells2):
                            if ni == 0:
                                continue  # Skip first cell
                            if ni - 1 >= len(outcome_names):
                                break
                            nc_text = nc.get_text(strip=True)
                            pure_se = re.match(r'^\(([\d.]+)\)$', nc_text)
                            if pure_se:
                                se_from_next_row[ni - 1] = float(pure_se.group(1))
            
            # Extract values for each outcome
            for i, cell in enumerate(cells[1:]):
                if i >= len(outcome_names):
                    break
                
                cell_text = cell.get_text(strip=True)
                coef, se, stars = parse_coefficient_se(cell_text)
                
                # If SE is None but we have it from next row, use that
                if se is None and i in se_from_next_row:
                    se = se_from_next_row[i]
                
                # Get sample size
                if current_followup == "Followup 1 (6 months)":
                    sample_size = observations_followup1.get(outcome_names[i])
                else:
                    sample_size = observations_followup2.get(outcome_names[i])
                
                if coef is not None:
                    results.append({
                        'study_id': 121058356,
                        'author': 'Bossuroy',
                        'table_number': 1,
                        'table_caption': 'Table 1: Primary Outcomes',
                        'page_number': table1.get('page_idx', 0) + 1,  # 1-indexed
                        'followup_period': current_followup,
                        'treatment_arm': treatment_arm,
                        'outcome_name': outcome_names[i],
                        'coefficient': coef,
                        'standard_error': se,
                        'significance': stars,
                        'sample_size': sample_size,
                        'literal_cell_text': cell_text
                    })
    
    df = pd.DataFrame(results)
    return df


if __name__ == "__main__":
    print("=" * 70)
    print("EXTRACTION V1: PARSE TABLE 1 DIRECTLY FROM HTML")
    print("=" * 70)
    
    # Load MineRU JSON
    print("\nLoading MineRU output...")
    doc = load_mineru_json()
    
    # Extract Table 1
    print("\nExtracting Table 1: Primary Outcomes...")
    df = extract_table1_primary_outcomes(doc)
    
    print(f"\n{'=' * 70}")
    print(f"EXTRACTION RESULTS")
    print(f"{'=' * 70}")
    print(f"Total rows extracted: {len(df)}")
    print(f"Expected: 18 (3 outcomes × 3 arms × 2 followups)")
    
    if not df.empty:
        print(f"\nUnique outcomes: {df['outcome_name'].nunique()}")
        print(f"Unique treatment arms: {df['treatment_arm'].nunique()}")
        print(f"Unique followup periods: {df['followup_period'].nunique()}")
        
        print(f"\n--- Full DataFrame ---")
        pd.set_option('display.max_columns', None)
        pd.set_option('display.width', None)
        print(df.to_string(index=False))
        
        # Save to CSV
        output_path = "extraction_pipeline/table1_extracted_v1.csv"
        df.to_csv(output_path, index=False)
        print(f"\nSaved to: {output_path}")
        
        # Compare with ground truth
        print(f"\n{'=' * 70}")
        print(f"COMPARISON WITH USER'S GROUND TRUTH")
        print(f"{'=' * 70}")
        
        gt_path = "extraction_pipeline/table1_121058356.csv"
        try:
            gt_df = pd.read_csv(gt_path)
            print(f"Ground truth rows: {len(gt_df)}")
            print(f"Extracted rows: {len(df)}")
            
            # Check if we got all the key values
            print(f"\nGT coefficients for 'Gross consumption':")
            gt_gross = gt_df[gt_df['outcome_name'].str.contains('Gross', case=False, na=False)]
            for _, row in gt_gross.iterrows():
                print(f"  {row.get('table_section', 'N/A')}, {row.get('Row', 'N/A')}: {row.get('coefficient', 'N/A')}")
            
            print(f"\nExtracted coefficients for 'Gross consumption':")
            ext_gross = df[df['outcome_name'].str.contains('Gross', case=False, na=False)]
            for _, row in ext_gross.iterrows():
                print(f"  {row['followup_period']}, {row['treatment_arm']}: {row['coefficient']}")
                
        except FileNotFoundError:
            print(f"Ground truth file not found at {gt_path}")
