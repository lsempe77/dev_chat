"""
Standard Results Table Extractor
================================

Extract all data cells from a standard results table.
"""

import re
from typing import List, Dict, Any
from bs4 import BeautifulSoup

from extraction_pipeline.parsing.ocr import fix_ocr_spacing
from extraction_pipeline.parsing.cells import parse_cell_comprehensive


# Expanded list of treatment arm patterns found across studies (multi-language)
TREATMENT_KEYWORDS = [
    # English - From Graduation/BRAC studies
    'capital', 'psychosocial', 'full', 'treatment', 'treated', 'program',
    # English - Treatment arm codes
    'cct', 'grant', 'training', 'coaching', 'savings', 'stipend', 'transfer',
    # English - Intervention components
    'asset', 'livestock', 'cash', 'input', 'package', 'extension', 'intensive',
    # English - Econometric notation
    'atet', 'ate', 'att', 'itt', 'tot', 'late',
    # English - Common program names
    'psnp', 'spir', 'brac', 'graduation', 'tup', 'vup', 'cfpr',
    # English - Comparison labels
    'vs', 'versus', 'difference',
    # English - Received/intervention labels
    'received', 'intervention', 'eligible', 'beneficiary', 'participant',
    
    # Spanish
    'tratamiento', 'tratado', 'tratados', 'grupo tratamiento', 'grupo control',
    'programa', 'beneficiario', 'beneficiarios', 'intervencion', 'intervención',
    'efecto', 'impacto', 'transferencia', 'capacitación', 'ahorro',
    'intención', 'intencion', 'diferencia', 'intensidad',
    
    # French
    'traitement', 'traité', 'traités', 'groupe traitement', 'groupe contrôle',
    'programme', 'bénéficiaire', 'bénéficiaires', 'intervention',
    'effet', 'impact', 'transfert', 'formation', 'épargne',
    'intention', 'différence', 'intensité',
    
    # Portuguese
    'tratamento', 'tratado', 'tratados', 'grupo tratamento', 'grupo controle',
    'programa', 'beneficiário', 'beneficiários', 'intervenção',
    'efeito', 'impacto', 'transferência', 'treinamento', 'poupança',
    'intenção', 'diferença', 'intensidade'
]

# Patterns that indicate NOT a treatment row (exclude these) - multi-language
EXCLUDE_PATTERNS = [
    # English
    r'^test\s*:', r'^mean\s+of', r'^p[\s-]*value', r'^note', r'^source',
    r'^observation', r'^r[\s-]*squared', r'^n\s*=', r'^control\s+(mean|sd)',
    r'^standard\s+error', r'^panel\s+[a-z]:', r'^\*+', r'^cluster',
    r'^robust', r'^baseline', r'^year\s+fe', r'^district\s+fe',
    # Spanish
    r'^observacion', r'^nota', r'^fuente', r'^error\s+estandar',
    r'^media\s+(control|de)', r'^linea\s+base', r'^línea\s+base',
    # French  
    r'^observation', r'^note', r'^source', r'^erreur\s+type',
    r'^moyenne\s+(contrôle|de)', r'^ligne\s+de\s+base',
    # Portuguese
    r'^observação', r'^nota', r'^fonte', r'^erro\s+padrão',
    r'^média\s+(controle|de)', r'^linha\s+de\s+base'
]


def is_treatment_row(cell_text: str, row_cells=None) -> tuple:
    """
    Check if row label indicates a treatment arm.
    Returns (is_treatment, treatment_name) tuple.
    """
    text = cell_text.strip()
    text_lower = text.lower()
    
    # Skip empty
    if not text:
        return False, None
    
    # Explicit exclusions
    for pattern in EXCLUDE_PATTERNS:
        if re.search(pattern, text_lower):
            return False, None
    
    # Check if row has coefficient pattern in cells (number with SE in parens)
    has_coef_pattern = False
    if row_cells and len(row_cells) > 1:
        for cell in row_cells[1:4]:  # Check first few data cells
            cell_text = cell.get_text(strip=True)
            if re.search(r'-?\d+\.?\d*\s*[\*†‡]*\s*\(', cell_text):
                has_coef_pattern = True
                break
    
    # Match T1, T2, T3, etc. with any suffix
    if re.match(r'^T\d+', text):
        return True, text
    
    # Match "CCT + grant (T3)" style labels
    if re.search(r'\(T\d+\)', text):
        return True, text
    
    # Match ATET/ATE/ATT treatment effect rows
    if re.match(r'^(ATET|ATE|ATT|ITT)\s+', text, re.IGNORECASE):
        return True, text
    
    # Match "Received X" patterns
    if re.match(r'^received\s+', text_lower):
        return True, text
    
    # Match "TUP1-TUP2" comparison patterns
    if re.search(r'tup\d*\s*[-–]\s*tup\d*', text_lower):
        return True, text
    
    # Match "Difference-in-Difference" rows
    if 'difference-in-difference' in text_lower or 'diff-in-diff' in text_lower:
        return True, text
    
    # Match rows containing treatment keywords AND having coefficient pattern
    if has_coef_pattern:
        for kw in TREATMENT_KEYWORDS:
            if kw in text_lower:
                return True, text
    
    # Match common exact patterns
    exact_matches = ['Capital', 'Psychosocial', 'Full', 'Treatment', 'Treated', 
                    'Program', 'Intervention', 'Cash', 'Grant', 'Training']
    if text in exact_matches:
        return True, text
    
    return False, None


def extract_results_table(table: dict, study_id: str) -> List[Dict[str, Any]]:
    """
    Extract all data cells from a results table.
    Returns list of dicts, one per extracted value.
    """
    caption_raw = ' '.join(table.get('table_caption', []))
    caption = fix_ocr_spacing(caption_raw)  # Fix OCR spacing issues
    html = table.get('table_body', '')
    page_idx = table.get('page_idx', 0)
    
    # Parse table number from caption (use normalized for matching)
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
    
    # First pass: collect metadata by section (observations, control means, control SDs)
    observations_by_section = {}
    control_means_by_section = {}
    control_sds_by_section = {}
    n_treatment_by_section = {}
    n_control_by_section = {}
    n_clusters_by_section = {}
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
                n_treatment_by_section[current_section_pass1] = {}
                n_control_by_section[current_section_pass1] = {}
                n_clusters_by_section[current_section_pass1] = {}
        
        # Ensure default section exists
        if current_section_pass1 is None:
            current_section_pass1 = 'default'
            if current_section_pass1 not in observations_by_section:
                observations_by_section[current_section_pass1] = {}
                control_means_by_section[current_section_pass1] = {}
                control_sds_by_section[current_section_pass1] = {}
                n_treatment_by_section[current_section_pass1] = {}
                n_control_by_section[current_section_pass1] = {}
                n_clusters_by_section[current_section_pass1] = {}
        
        # Parse N treatment
        if re.search(r'n\s*treatment|n\s*treated|treatment\s*n|treated\s*n|obs.*treatment|treatment.*obs', first_cell_lower):
            for i, cell in enumerate(cells[1:]):
                if i < len(outcome_names):
                    nums = re.findall(r'\d+', cell.get_text(strip=True).replace(',', ''))
                    if nums:
                        n_treatment_by_section[current_section_pass1][outcome_names[i]] = int(nums[0])
        
        # Parse N control
        elif re.search(r'n\s*control|control\s*n|obs.*control|control.*obs|comparison\s*n', first_cell_lower):
            for i, cell in enumerate(cells[1:]):
                if i < len(outcome_names):
                    nums = re.findall(r'\d+', cell.get_text(strip=True).replace(',', ''))
                    if nums:
                        n_control_by_section[current_section_pass1][outcome_names[i]] = int(nums[0])
        
        # Parse observations (total N)
        elif 'observation' in first_cell_lower:
            for i, cell in enumerate(cells[1:]):
                if i < len(outcome_names):
                    nums = re.findall(r'\d+', cell.get_text(strip=True).replace(',', ''))
                    if nums:
                        observations_by_section[current_section_pass1][outcome_names[i]] = int(nums[0])
        
        # Parse clusters
        elif re.search(r'cluster|school|village|communit', first_cell_lower):
            for i, cell in enumerate(cells[1:]):
                if i < len(outcome_names):
                    nums = re.findall(r'\d+', cell.get_text(strip=True).replace(',', ''))
                    if nums:
                        n_clusters_by_section[current_section_pass1][outcome_names[i]] = int(nums[0])
        
        elif 'control mean' in first_cell_lower:
            for i, cell in enumerate(cells[1:]):
                if i < len(outcome_names):
                    nums = re.findall(r'-?\d+\.?\d*', cell.get_text(strip=True))
                    if nums:
                        control_means_by_section[current_section_pass1][outcome_names[i]] = float(nums[0])
        
        elif 'control sd' in first_cell_lower:
            for i, cell in enumerate(cells[1:]):
                if i < len(outcome_names):
                    nums = re.findall(r'-?\d+\.?\d*', cell.get_text(strip=True))
                    if nums:
                        control_sds_by_section[current_section_pass1][outcome_names[i]] = float(nums[0])
    
    # Second pass: extract treatment effects
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
        
        # Check for treatment arm row (using expanded matching with row context)
        is_treatment, treatment_name = is_treatment_row(first_cell_text, cells)
        if is_treatment:
            treatment_arm = treatment_name or first_cell_text
            
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
                # Use comprehensive parser for all fields
                parsed = parse_cell_comprehensive(cell_text)
                
                coef = parsed['coefficient']
                se = parsed['standard_error']
                stars = parsed['significance']
                p_value = parsed['p_value']
                p_value_text = parsed['p_value_text']
                ci_lower = parsed['ci_lower']
                ci_upper = parsed['ci_upper']
                
                # Use SE from next row if needed
                if se is None and i in se_from_next:
                    se = se_from_next[i]
                
                # Get section-specific metadata
                section_key = current_section or 'default'
                obs = observations_by_section.get(section_key, {}).get(outcome_names[i])
                ctrl_mean = control_means_by_section.get(section_key, {}).get(outcome_names[i])
                ctrl_sd = control_sds_by_section.get(section_key, {}).get(outcome_names[i])
                n_treat = n_treatment_by_section.get(section_key, {}).get(outcome_names[i])
                n_ctrl = n_control_by_section.get(section_key, {}).get(outcome_names[i])
                n_clust = n_clusters_by_section.get(section_key, {}).get(outcome_names[i])
                
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
                        'p_value': p_value,
                        'p_value_text': p_value_text,
                        'ci_lower': ci_lower,
                        'ci_upper': ci_upper,
                        't_statistic': parsed.get('t_statistic'),
                        'sample_size': obs,
                        'n_treatment': n_treat,
                        'n_control': n_ctrl,
                        'n_clusters': n_clust,
                        'control_mean': ctrl_mean,
                        'control_sd': ctrl_sd,
                        'literal_cell_text': cell_text
                    })
    
    return results
