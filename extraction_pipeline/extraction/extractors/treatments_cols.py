"""
Treatment Columns Extractor
===========================

Extract from tables with treatment groups in columns, outcomes in rows.
"""

import re
from typing import List, Dict, Any
from bs4 import BeautifulSoup

from extraction_pipeline.parsing.ocr import fix_ocr_spacing
from extraction_pipeline.parsing.cells import parse_cell_comprehensive


def extract_treatments_in_cols_table(table: dict, study_id: str) -> List[Dict[str, Any]]:
    """
    Extract from tables with treatment groups in columns, outcomes in rows.
    
    Format:
        | Outcome Variable    | Overall | Treatment A | Treatment B |
        | Financial literacy  | 0.58*** | 0.80***     | 0.19        |
        | Saving uptake       | 0.26*** | 0.34***     | 0.02        |
    """
    caption_raw = ' '.join(table.get('table_caption', []))
    caption = fix_ocr_spacing(caption_raw)
    html = table.get('table_body', '')
    page_idx = table.get('page_idx', 0)
    
    table_num_match = re.search(r'[Tt]able\s*[A.]?(\d+)', re.sub(r'\s+', '', caption))
    table_number = table_num_match.group(0) if table_num_match else None
    
    soup = BeautifulSoup(html, 'html.parser')
    rows = soup.find_all('tr')
    
    if not rows or len(rows) < 2:
        return []
    
    # Find header row (may be row 0 or row 1)
    header_row_idx = 0
    header_cells = rows[0].find_all(['td', 'th'])
    header_texts = [c.get_text(strip=True) for c in header_cells]
    
    if len(header_texts) <= 1 or not header_texts[1].strip():
        if len(rows) > 1:
            header_row_idx = 1
            header_cells = rows[1].find_all(['td', 'th'])
            header_texts = [c.get_text(strip=True) for c in header_cells]
    
    # Treatment arms are in the header (columns 1+)
    treatment_arms = header_texts[1:] if len(header_texts) > 1 else []
    if not treatment_arms:
        return []
    
    results = []
    
    # Skip section header patterns
    section_patterns = [r'^\d+\)', r'^[A-Z]\)', r'^panel\s+[a-z]', r'^\*+$']
    
    # Extract data from each row (each row is an outcome)
    for row in rows[header_row_idx + 1:]:
        cells = row.find_all(['td', 'th'])
        if len(cells) <= 1:
            continue
        
        # First cell is outcome name
        outcome_name = cells[0].get_text(strip=True)
        if not outcome_name or len(outcome_name) < 3:
            continue
        
        # Skip section headers and metadata rows
        outcome_lower = outcome_name.lower()
        if any(re.search(p, outcome_lower) for p in section_patterns):
            continue
        if any(k in outcome_lower for k in ['observation', 'r-squared', 'note', 'control mean', 'sample']):
            continue
        
        # Check if this row has SE in parentheses (skip - it's an SE row)
        first_data = cells[1].get_text(strip=True) if len(cells) > 1 else ''
        if re.match(r'^\([\d.,]+\)$', first_data):
            continue
        
        # Extract coefficient for each treatment arm column
        for col_idx, arm in enumerate(treatment_arms):
            if col_idx + 1 >= len(cells):
                break
            
            cell_text = cells[col_idx + 1].get_text(strip=True)
            
            # Handle European number format (commas instead of dots)
            cell_text_normalized = cell_text.replace(',', '.')
            
            parsed = parse_cell_comprehensive(cell_text_normalized)
            
            if parsed['coefficient'] is None:
                continue
            
            result = {
                'study_id': study_id,
                'table_number': table_number,
                'table_caption': caption[:200] if caption else None,
                'page_number': page_idx + 1,
                'section': None,
                'treatment_arm': arm,
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
