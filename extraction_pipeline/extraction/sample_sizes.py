"""
Sample Size Extraction
======================

Extract sample sizes from tables and prose text.
"""

import re
from typing import Dict, List, Any

from bs4 import BeautifulSoup

from ..core.llm_client import call_llm


def extract_sample_sizes_from_table(table: dict, outcome_names: List[str]) -> Dict[str, Dict[str, int]]:
    """
    Extract N_treatment, N_control, and N_clusters from table rows.
    
    Args:
        table: Table dictionary with 'table_body' HTML
        outcome_names: List of outcome column names
        
    Returns:
        Nested dict with structure:
        {
            'section_name': {
                'outcome_name': {
                    'n_treatment': int,
                    'n_control': int,
                    'n_total': int,
                    'n_clusters': int
                }
            }
        }
    """
    html = table.get('table_body', '')
    soup = BeautifulSoup(html, 'html.parser')
    rows = soup.find_all('tr')
    
    sample_sizes = {}
    current_section = None
    
    # Patterns for identifying sample size rows
    n_treat_patterns = [
        r'n\s*treatment', r'n\s*treated', r'obs\.?\s*treatment', 
        r'treatment\s*n', r'treated\s*n', r'treatment\s*obs',
        r'n_t', r'n1'
    ]
    n_ctrl_patterns = [
        r'n\s*control', r'obs\.?\s*control', r'control\s*n',
        r'control\s*obs', r'comparison\s*n', r'n_c', r'n0'
    ]
    n_total_patterns = [
        r'observation', r'n\s*$', r'^n$', r'sample\s*size',
        r'total\s*n', r'n\s*total'
    ]
    cluster_patterns = [
        r'cluster', r'school', r'village', r'community', 
        r'household', r'group', r'site'
    ]
    
    for row in rows:
        cells = row.find_all('td')
        if not cells:
            continue
        
        first_cell = cells[0].get_text(strip=True)
        first_cell_lower = first_cell.lower()
        
        # Track section
        if 'followup' in first_cell_lower or 'follow-up' in first_cell_lower:
            current_section = first_cell
            if current_section not in sample_sizes:
                sample_sizes[current_section] = {}
            continue
        
        # Ensure current section is initialized
        if current_section is None:
            current_section = 'default'
        if current_section not in sample_sizes:
            sample_sizes[current_section] = {}
        
        # Check row type
        row_type = None
        for pattern in n_treat_patterns:
            if re.search(pattern, first_cell_lower, re.IGNORECASE):
                row_type = 'n_treatment'
                break
        if not row_type:
            for pattern in n_ctrl_patterns:
                if re.search(pattern, first_cell_lower, re.IGNORECASE):
                    row_type = 'n_control'
                    break
        if not row_type:
            for pattern in n_total_patterns:
                if re.search(pattern, first_cell_lower, re.IGNORECASE):
                    row_type = 'n_total'
                    break
        if not row_type:
            for pattern in cluster_patterns:
                if re.search(pattern, first_cell_lower, re.IGNORECASE):
                    row_type = 'n_clusters'
                    break
        
        if row_type:
            for i, cell in enumerate(cells[1:]):
                if i >= len(outcome_names):
                    break
                outcome = outcome_names[i]
                if outcome not in sample_sizes[current_section]:
                    sample_sizes[current_section][outcome] = {}
                
                # Extract number from cell
                nums = re.findall(r'\d+', cell.get_text(strip=True).replace(',', ''))
                if nums:
                    sample_sizes[current_section][outcome][row_type] = int(nums[0])
    
    return sample_sizes


def extract_sample_sizes_from_prose(doc: dict) -> Dict[str, Any]:
    """
    Extract sample sizes from prose text when not available in tables.
    Uses LLM to identify sample size information.
    
    Args:
        doc: MineRU JSON document
        
    Returns:
        Dictionary with n_treatment, n_control, n_total, n_clusters
    """
    prose = doc.get('content', '')[:15000]
    
    prompt = f"""Extract sample sizes from this research paper text.

TEXT:
{prose}

Find and return:
1. N_treatment - number of individuals/units in treatment group
2. N_control - number of individuals/units in control group  
3. N_total - total sample size
4. N_clusters - number of clusters (schools, villages, etc.) if cluster-randomized

Return in this format exactly:
n_treatment: NUMBER or UNKNOWN
n_control: NUMBER or UNKNOWN
n_total: NUMBER or UNKNOWN
n_clusters: NUMBER or UNKNOWN

Only return numbers you're confident about. Say UNKNOWN if not found or unclear."""

    result = call_llm(prompt, max_tokens=200)
    
    extracted = {
        'n_treatment': None,
        'n_control': None,
        'n_total': None,
        'n_clusters': None
    }
    
    for line in result.split('\n'):
        line_lower = line.lower().strip()
        if ':' in line_lower:
            key, value = line_lower.split(':', 1)
            value = value.strip()
            if value != 'unknown':
                nums = re.findall(r'\d+', value.replace(',', ''))
                if nums:
                    key_clean = key.strip().replace(' ', '_')
                    if key_clean in extracted:
                        extracted[key_clean] = int(nums[0])
    
    return extracted


__all__ = [
    'extract_sample_sizes_from_table',
    'extract_sample_sizes_from_prose',
]
