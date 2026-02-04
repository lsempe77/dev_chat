"""
Outcomes in Rows with SE Split Extractor
========================================

Extract from tables with outcomes in rows, coefficients in columns, SE in separate rows.
"""

import re
from typing import List, Dict, Any
from bs4 import BeautifulSoup

from extraction_pipeline.parsing.ocr import fix_ocr_spacing
from extraction_pipeline.parsing.cells import parse_cell_comprehensive


def extract_outcomes_in_rows_se_split(table: dict, study_id: str) -> List[Dict[str, Any]]:
    """
    Extract from tables with outcomes in rows, coefficients in columns, SE in separate rows.
    
    Format (European numbers, SE in separate rows):
        | Variables             | IV Effect | RE Effect | IV Change | RE Change |
        | Poverty by poverty line | -0,09*    | -0,22*   | 0,05**    | 0,16**    |
        |                        | (0,05)    |          | (0,02)    |           |
        | Extreme poverty        | 0,09      | 0,22     | -0,05**   | -0,16**   |
        |                        | (0,05)    |          | (0,02)    |           |
    """
    caption_raw = ' '.join(table.get('table_caption', []))
    caption = fix_ocr_spacing(caption_raw)
    html = table.get('table_body', '')
    page_idx = table.get('page_idx', 0)
    
    table_num_match = re.search(r'[Tt]able\s*[A.]?(\d+)', re.sub(r'\s+', '', caption))
    table_number = table_num_match.group(0) if table_num_match else None
    
    soup = BeautifulSoup(html, 'html.parser')
    rows = soup.find_all('tr')
    
    if not rows or len(rows) < 3:
        return []
    
    # Try to extract column headers from row 0 or 1
    # Often the headers are malformed, so we'll use column indices as treatment arms
    header_row_idx = 0
    header_cells = rows[0].find_all(['td', 'th'])
    header_texts = [c.get_text(strip=True) for c in header_cells]
    
    # If headers are merged/malformed, try row 1
    if len(header_texts) <= 2 or not any(header_texts[1:]):
        if len(rows) > 1:
            header_cells = rows[1].find_all(['td', 'th'])
            header_texts = [c.get_text(strip=True) for c in header_cells]
            header_row_idx = 1
    
    # Build treatment arms from headers or use defaults
    treatment_arms = []
    for i, h in enumerate(header_texts[1:], 1):
        if h.strip():
            treatment_arms.append(h.strip())
        else:
            treatment_arms.append(f'Column_{i}')
    
    if not treatment_arms:
        treatment_arms = [f'Column_{i}' for i in range(1, 5)]
    
    results = []
    current_outcome = None
    current_coefs = {}  # col_idx -> coefficient info
    
    # Process rows starting after header
    for row_idx, row in enumerate(rows[header_row_idx + 1:]):
        cells = row.find_all(['td', 'th'])
        if not cells:
            continue
        
        first_cell = cells[0].get_text(strip=True)
        first_cell_lower = first_cell.lower() if first_cell else ''
        first_cell_normalized = first_cell.replace(',', '.') if first_cell else ''
        
        # Skip metadata rows
        if any(k in first_cell_lower for k in ['observation', 'r-squared', 'note', 'sample', 'n=']):
            continue
        
        # Check if this is an SE row
        # Pattern 1: SE in first column (e.g., "(0.05)")
        # Pattern 2: SE in second column (e.g., "", "(0.05)")
        is_se_row = False
        se_values = {}  # col_idx -> SE value
        
        # Check if first cell is SE
        if re.match(r'^\([\d.]+\)$', first_cell_normalized):
            is_se_row = True
            # Parse SE from all columns that have them
            for col_idx, cell in enumerate(cells):
                cell_text = cell.get_text(strip=True).replace(',', '.')
                se_match = re.match(r'^\(([\d.]+)\)$', cell_text)
                if se_match:
                    # Map to coefficient column (col 0 SE -> coef col 0, etc.)
                    # But offset by 1 since we're looking at data columns 
                    se_values[col_idx] = float(se_match.group(1))
        elif len(cells) > 1:
            second_cell = cells[1].get_text(strip=True).replace(',', '.')
            if re.match(r'^\([\d.]+\)$', second_cell):
                is_se_row = True
                for col_idx, cell in enumerate(cells[1:]):
                    cell_text = cell.get_text(strip=True).replace(',', '.')
                    se_match = re.match(r'^\(([\d.]+)\)$', cell_text)
                    if se_match:
                        se_values[col_idx] = float(se_match.group(1))
        
        if is_se_row:
            # Associate SEs with previous outcome's coefficients
            if current_outcome and current_coefs:
                for col_idx, se_val in se_values.items():
                    if col_idx in current_coefs:
                        current_coefs[col_idx]['standard_error'] = se_val
            continue
        
        # Skip empty rows
        if not first_cell or len(first_cell) < 3:
            continue
        
        # This is a new outcome row
        # First, save any pending coefficients from previous outcome
        if current_outcome and current_coefs:
            for col_idx, coef_info in current_coefs.items():
                arm_name = treatment_arms[col_idx] if col_idx < len(treatment_arms) else f'Column_{col_idx+1}'
                result = {
                    'study_id': study_id,
                    'table_number': table_number,
                    'table_caption': caption[:200] if caption else None,
                    'page_number': page_idx + 1,
                    'section': None,
                    'treatment_arm': arm_name,
                    'outcome_name': current_outcome,
                    'coefficient': coef_info['coefficient'],
                    'standard_error': coef_info.get('standard_error'),
                    'significance': coef_info.get('significance'),
                    'p_value': coef_info.get('p_value'),
                    'p_value_text': coef_info.get('p_value_text'),
                    'ci_lower': coef_info.get('ci_lower'),
                    'ci_upper': coef_info.get('ci_upper'),
                    't_statistic': None,
                    'sample_size': None,
                    'n_treatment': None,
                    'n_control': None,
                    'n_clusters': None,
                    'control_mean': None,
                    'control_sd': None,
                    'literal_cell_text': coef_info.get('literal_text', '')
                }
                results.append(result)
        
        # Start new outcome
        current_outcome = first_cell
        current_coefs = {}
        
        # Extract coefficients from this row
        for col_idx, cell in enumerate(cells[1:]):
            cell_text = cell.get_text(strip=True)
            if not cell_text:
                continue
            
            # Handle European format
            cell_normalized = cell_text.replace(',', '.')
            
            parsed = parse_cell_comprehensive(cell_normalized)
            if parsed['coefficient'] is not None:
                current_coefs[col_idx] = {
                    'coefficient': parsed['coefficient'],
                    'standard_error': parsed['standard_error'],
                    'significance': parsed['significance'],
                    'p_value': parsed['p_value'],
                    'p_value_text': parsed['p_value_text'],
                    'ci_lower': parsed['ci_lower'],
                    'ci_upper': parsed['ci_upper'],
                    'literal_text': cell_text
                }
    
    # Don't forget to save the last outcome's coefficients
    if current_outcome and current_coefs:
        for col_idx, coef_info in current_coefs.items():
            arm_name = treatment_arms[col_idx] if col_idx < len(treatment_arms) else f'Column_{col_idx+1}'
            result = {
                'study_id': study_id,
                'table_number': table_number,
                'table_caption': caption[:200] if caption else None,
                'page_number': page_idx + 1,
                'section': None,
                'treatment_arm': arm_name,
                'outcome_name': current_outcome,
                'coefficient': coef_info['coefficient'],
                'standard_error': coef_info.get('standard_error'),
                'significance': coef_info.get('significance'),
                'p_value': coef_info.get('p_value'),
                'p_value_text': coef_info.get('p_value_text'),
                'ci_lower': coef_info.get('ci_lower'),
                'ci_upper': coef_info.get('ci_upper'),
                't_statistic': None,
                'sample_size': None,
                'n_treatment': None,
                'n_control': None,
                'n_clusters': None,
                'control_mean': None,
                'control_sd': None,
                'literal_cell_text': coef_info.get('literal_text', '')
            }
            results.append(result)
    
    return results
