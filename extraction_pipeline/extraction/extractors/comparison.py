"""
Comparison Format Extractor
===========================

Extract data from "comparison format" tables common in BRAC/Graduation studies.
"""

import re
from typing import List, Dict, Any
from bs4 import BeautifulSoup

from extraction_pipeline.parsing.ocr import fix_ocr_spacing
from extraction_pipeline.parsing.cells import parse_cell_comprehensive


def extract_comparison_format_table(table: dict, study_id: str) -> List[Dict[str, Any]]:
    """
    Extract data from "comparison format" tables common in BRAC/Graduation studies.
    
    Format:
        |                           | TUP   | ultra-poor | village | [A-B]    | [A-C]    |
        | Outcome name              | 0.97  | 0.22       | 0.16    | 0.75***  | 0.82***  |
    
    The impact estimates are in columns labeled [A-B], [A-C] or similar difference columns.
    Outcomes are in rows (first column).
    """
    caption_raw = ' '.join(table.get('table_caption', []))
    caption = fix_ocr_spacing(caption_raw)
    html = table.get('table_body', '')
    page_idx = table.get('page_idx', 0)
    
    table_num_match = re.search(r'[Tt]able\s*[A.]?(\d+)', re.sub(r'\s+', '', caption))
    table_number = table_num_match.group(0) if table_num_match else None
    
    soup = BeautifulSoup(html, 'html.parser')
    rows = soup.find_all('tr')
    
    if not rows or len(rows) < 4:
        return []
    
    # Find the header row with column labels like [A-B], [A-C] (difference columns)
    # Scan ALL header rows (first 4) to find the row with difference labels
    impact_col_indices = []
    treatment_arms = []
    
    # Priority 1: Look for explicit difference columns like [A-B], [A-C]
    for header_row_idx in range(min(4, len(rows))):
        header_cells = rows[header_row_idx].find_all(['td', 'th'])
        header_texts = [c.get_text(strip=True) for c in header_cells]
        
        for col_idx, text in enumerate(header_texts):
            text_clean = text.lower().strip()
            # Match patterns like [A-B], [A-C], (A-B), A-B, etc. (must have dash)
            if re.search(r'\[?[a-c]\s*[-–]\s*[a-c]\]?', text_clean):
                impact_col_indices.append(col_idx)
                arm_name = text.replace('[', '').replace(']', '').strip()
                treatment_arms.append(arm_name)
    
    if not impact_col_indices:
        # Priority 2: Fallback to columns with *** patterns
        for row_idx in range(3, min(6, len(rows))):
            row_cells = rows[row_idx].find_all(['td', 'th'])
            for col_idx, cell in enumerate(row_cells):
                text = cell.get_text(strip=True)
                if re.search(r'\*{2,3}', text) and col_idx > 0:
                    if col_idx not in impact_col_indices:
                        impact_col_indices.append(col_idx)
                        treatment_arms.append(f"impact_{col_idx}")
    
    if not impact_col_indices:
        return []
    
    results = []
    
    # Skip metadata row patterns
    skip_patterns = [
        r'^observation', r'^n\s*=', r'^r[\s-]*squared', r'^note', r'^source',
        r'^\*+$', r'^test\s*:', r'^control', r'^standard', r'^sample'
    ]
    
    # Process each data row (outcomes are in first column)
    # Handle two formats: 
    # 1) Outcome name and values in same row
    # 2) Outcome name in one row, values in next row (alternating)
    current_outcome = None
    
    for row_idx, row in enumerate(rows[2:], start=2):  # Start from row 2 (after headers)
        cells = row.find_all(['td', 'th'])
        if len(cells) < 2:
            continue
        
        # First cell might be outcome name or empty (if values row)
        first_cell = cells[0].get_text(strip=True)
        first_cell_lower = first_cell.lower() if first_cell else ''
        
        # Skip metadata rows
        if any(re.search(p, first_cell_lower) for p in skip_patterns):
            continue
        
        # Check if first cell looks like an outcome name (not a number/header code)
        is_outcome_name = (
            first_cell and 
            len(first_cell) > 3 and 
            not re.match(r'^[\d.,\-\s\(\)\[\]]+$', first_cell) and
            not re.match(r'^\[?[A-C]\]?$', first_cell)  # Not column labels like [A], [B]
        )
        
        if is_outcome_name:
            current_outcome = first_cell
            
            # Check if this row also has coefficient values
            has_values = False
            for col_idx in impact_col_indices:
                if col_idx < len(cells):
                    cell_text = cells[col_idx].get_text(strip=True)
                    if cell_text and re.search(r'-?\d+\.?\d*', cell_text):
                        has_values = True
                        break
            
            if not has_values:
                # Values will be in next row
                continue
        
        # If no outcome name in this row, use the previous one
        outcome_name = first_cell if is_outcome_name else current_outcome
        
        if not outcome_name or len(outcome_name) < 3:
            continue
        
        # Extract impact estimates from each impact column
        for arm_idx, col_idx in enumerate(impact_col_indices):
            if col_idx >= len(cells):
                continue
            
            cell_text = cells[col_idx].get_text(strip=True)
            if not cell_text:
                continue
            
            # Parse the cell
            parsed = parse_cell_comprehensive(cell_text)
            
            if parsed['coefficient'] is not None:
                treatment_arm = treatment_arms[arm_idx] if arm_idx < len(treatment_arms) else f"impact_{col_idx}"
                
                result = {
                    'study_id': study_id,
                    'table_number': table_number,
                    'table_caption': caption[:200] if caption else None,
                    'page_number': page_idx + 1,
                    'section': None,
                    'treatment_arm': treatment_arm,
                    'outcome_name': outcome_name,
                    'coefficient': parsed['coefficient'],
                    'standard_error': parsed['standard_error'],
                    'significance': parsed['significance'],
                    'p_value': parsed['p_value'],
                    'p_value_text': parsed['p_value_text'],
                    'ci_lower': parsed['ci_lower'],
                    'ci_upper': parsed['ci_upper'],
                    't_statistic': parsed.get('t_statistic'),
                    'sample_size': None,
                    'n_treatment': None,
                    'n_control': None,
                    'n_clusters': None,
                    'control_mean': None,
                    'control_sd': None,
                    'literal_cell_text': cell_text
                }
                results.append(result)
    
    return results
