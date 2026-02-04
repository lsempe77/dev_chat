"""
Transposed Table Extractor
==========================

Extract data from transposed tables where outcomes are in rows.
"""

import re
from typing import List, Dict, Any
from bs4 import BeautifulSoup

from extraction_pipeline.parsing.ocr import fix_ocr_spacing
from extraction_pipeline.parsing.cells import parse_cell_comprehensive


def extract_transposed_table(table: dict, study_id: str) -> List[Dict[str, Any]]:
    """
    Extract data from transposed tables where outcomes are in rows.
    
    Expected format:
        |                   | Mean Effect | SE    | p-value |
        | Consumption       | 0.103***    | 0.025 | 0.000   |
        | Food security     | 0.165       | 0.131 | 0.209   |
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
    
    # Parse header to identify column meanings
    header_cells = rows[0].find_all(['td', 'th'])
    header_texts = [c.get_text(strip=True).lower() for c in header_cells]
    
    # Map header positions to fields
    coef_idx = None
    se_idx = None
    pval_idx = None
    
    for i, h in enumerate(header_texts):
        if any(k in h for k in ['mean effect', 'effect', 'coefficient', 'coef', 'estimate']):
            coef_idx = i
        elif any(k in h for k in ['standard error', 'se', 'std. error', 'std error']):
            se_idx = i
        elif any(k in h for k in ['p-value', 'p value', 'pvalue']):
            pval_idx = i
    
    # If we can't find coefficient column, try to infer from data
    if coef_idx is None:
        # Assume second column is coefficient if header doesn't help
        coef_idx = 1 if len(header_texts) > 1 else None
    
    if coef_idx is None:
        return []  # Can't parse without knowing where coefficients are
    
    results = []
    
    # Extract data from each row (each row is an outcome)
    for row in rows[1:]:
        cells = row.find_all(['td', 'th'])
        if len(cells) <= coef_idx:
            continue
        
        # First cell is outcome name
        outcome_name = cells[0].get_text(strip=True)
        if not outcome_name or len(outcome_name) < 2:
            continue
        
        # Skip metadata rows
        outcome_lower = outcome_name.lower()
        skip_keywords = ['observation', 'r-squared', 'r2', 'note', 'source', 'cluster', 
                        'control mean', 'control sd', 'baseline', 'panel']
        if any(k in outcome_lower for k in skip_keywords):
            continue
        
        # Get coefficient cell
        coef_text = cells[coef_idx].get_text(strip=True) if len(cells) > coef_idx else ''
        
        # Parse coefficient using comprehensive parser
        parsed = parse_cell_comprehensive(coef_text)
        
        if parsed['coefficient'] is None:
            continue  # Skip rows without valid coefficients
        
        # Get SE if available
        se = parsed['standard_error']
        if se is None and se_idx and len(cells) > se_idx:
            se_text = cells[se_idx].get_text(strip=True)
            se_match = re.search(r'-?([\d.]+)', se_text.replace('−', '-'))
            if se_match:
                try:
                    se = abs(float(se_match.group(1)))
                except ValueError:
                    pass
        
        # Get p-value if available
        p_value = parsed['p_value']
        p_value_text = parsed['p_value_text']
        if p_value is None and pval_idx and len(cells) > pval_idx:
            pval_text = cells[pval_idx].get_text(strip=True)
            pval_match = re.search(r'([\d.]+(?:E[+-]?\d+)?)', pval_text, re.IGNORECASE)
            if pval_match:
                try:
                    p_value = float(pval_match.group(1))
                    p_value_text = pval_text
                except ValueError:
                    pass
        
        result = {
            'study_id': study_id,
            'table_number': table_number,
            'table_caption': caption[:200] if caption else None,
            'page_number': page_idx + 1,
            'section': None,
            'treatment_arm': 'Treatment',  # Transposed tables usually have single treatment
            'outcome_name': outcome_name,
            'coefficient': parsed['coefficient'],
            'standard_error': se,
            'significance': parsed['significance'],
            'p_value': p_value,
            'p_value_text': p_value_text,
            'ci_lower': parsed['ci_lower'],
            'ci_upper': parsed['ci_upper'],
            't_statistic': parsed.get('t_statistic'),
            'sample_size': None,
            'n_treatment': None,
            'n_control': None,
            'n_clusters': None,
            'control_mean': None,
            'control_sd': None,
            'literal_cell_text': coef_text
        }
        results.append(result)
    
    return results
