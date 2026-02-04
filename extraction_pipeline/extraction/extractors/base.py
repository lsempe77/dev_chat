"""
Base utilities for table extraction.
"""

import re
from typing import List, Dict, Any
from bs4 import BeautifulSoup


def detect_table_orientation(rows: list) -> str:
    """
    Detect table structure type.
    
    Returns:
    - 'columns': Standard format - outcomes in columns, treatments in rows
    - 'rows': Transposed - outcomes in rows, stats (effect, SE, p) in columns
    - 'treatments_in_cols': Outcomes in rows, treatment GROUPS in columns
    - 'outcomes_in_rows_se_split': Outcomes in rows, coefficients with SE in separate rows
    """
    if not rows or len(rows) < 2:
        return 'columns'  # Default
    
    # Get header row (may need to check row 1 if row 0 is merged)
    header_cells = rows[0].find_all(['td', 'th'])
    header_texts = [c.get_text(strip=True).lower() for c in header_cells]
    
    # If first row is mostly empty or single cell, try second row
    if len(header_texts) <= 1 or (len(header_texts) > 1 and not header_texts[1].strip()):
        if len(rows) > 1:
            header_cells = rows[1].find_all(['td', 'th'])
            header_texts = [c.get_text(strip=True).lower() for c in header_cells]
    
    # Strong indicators of transposed format (statistical columns as headers) - multi-language
    transposed_headers = [
        # English
        'mean effect', 'effect', 'coefficient', 'coef', 'estimate', 
        'standard error', 'se', 'std. error', 'p-value', 'p value',
        'q-value', 't-stat', 'ci lower', 'ci upper', '95% ci',
        # Spanish
        'efecto', 'coeficiente', 'estimación', 'error estándar', 'error estandar',
        'valor p', 'valor-p', 'intervalo de confianza',
        'intención del tratamiento', 'impacto del tratamiento',
        # French
        'effet', 'coefficient', 'estimation', 'erreur type', 'erreur standard',
        'valeur p', 'intervalle de confiance',
        # Portuguese
        'efeito', 'coeficiente', 'estimativa', 'erro padrão', 'erro padrao',
        'valor p', 'intervalo de confiança'
    ]
    
    # Count how many header cells match transposed indicators
    transposed_matches = sum(1 for h in header_texts if any(t in h for t in transposed_headers))
    
    # If 2+ header cells look like stat columns, it's transposed
    if transposed_matches >= 2:
        return 'rows'
    
    # Check for treatment groups in columns pattern:
    # Headers like: "Outcome" | "Overall" | "Treatment A" | "Treatment B" | "Control"
    # Multi-language support: Spanish, French, Portuguese
    treatment_group_headers = [
        # English
        'overall', 'treatment', 'control', 'program', 'intervention',
        'lump', 'training', 'cash', 'full', 'partial', 'group',
        # Spanish
        'tratamiento', 'control', 'programa', 'intervención', 'grupo',
        'total', 'completo', 'parcial', 'efectivo', 'capacitación',
        # French
        'traitement', 'contrôle', 'témoin', 'programme', 'intervention',
        'groupe', 'total', 'complet', 'partiel', 'formation',
        # Portuguese
        'tratamento', 'controle', 'programa', 'intervenção', 'grupo',
        'total', 'completo', 'parcial', 'treinamento'
    ]
    group_matches = sum(1 for h in header_texts[1:] if any(t in h for t in treatment_group_headers))
    
    # Also check if first column header suggests outcomes (multi-language)
    outcome_first_col = [
        '', 'outcome', 'variable', 'indicator',  # English
        'resultado', 'variable', 'indicador',    # Spanish
        'résultat', 'variable', 'indicateur',    # French
        'resultado', 'variável', 'indicador'     # Portuguese
    ]
    first_col = header_texts[0] if header_texts else ''
    
    if group_matches >= 2 and first_col in outcome_first_col:
        return 'treatments_in_cols'
    
    # Check: if first column has statistical header, probably NOT transposed
    # Multi-language support
    baseline_first_col = [
        '', 'variable', 'characteristic', 'indicator',  # English
        'variable', 'característica', 'indicador',      # Spanish
        'variable', 'caractéristique', 'indicateur',    # French
        'variável', 'característica', 'indicador'       # Portuguese
    ]
    baseline_headers = [
        # English
        'control', 'treatment', 'treated', 'difference', 'p-value', 'mean', 'sd',
        # Spanish
        'control', 'tratamiento', 'tratado', 'diferencia', 'valor p', 'media', 'de',
        # French
        'contrôle', 'témoin', 'traitement', 'traité', 'différence', 'valeur p', 'moyenne', 'écart',
        # Portuguese
        'controle', 'tratamento', 'tratado', 'diferença', 'valor p', 'média', 'dp'
    ]
    
    if first_col in baseline_first_col or not first_col:
        # Check if other headers look like group comparisons (baseline table)
        baseline_matches = sum(1 for h in header_texts[1:] if any(b in h for b in baseline_headers))
        if baseline_matches >= 2:
            return 'columns'  # It's a baseline/balance table
    
    # NEW: Check for "comparison" or "impact estimates" format
    # Pattern: Must have explicit difference column labels like [A-B], [A-C]
    # This is a common format in BRAC/Graduation studies
    all_rows_text = ' '.join([' '.join([c.get_text(strip=True).lower() for c in r.find_all(['td', 'th'])]) for r in rows[:4]])
    
    # STRICT: Require explicit difference column labels (not just "comparison")
    difference_col_indicators = [
        '[a-b]', '[a-c]', '[b-c]', '(a-b)', '(a-c)', '(b-c)',
        '[1-2]', '[1-3]', '[2-3]', '(1-2)', '(1-3)', '(2-3)'
    ]
    
    has_difference_cols = any(ind in all_rows_text for ind in difference_col_indicators)
    
    if has_difference_cols:
        # Verify: some rows have outcome names in first column
        # Check multiple rows since structure may vary (outcome name may be in row 2 or 3)
        if len(rows) >= 3:
            outcome_found = False
            for check_row_idx in range(2, min(6, len(rows))):
                data_row = rows[check_row_idx]
                cells = data_row.find_all(['td', 'th'])
                if len(cells) >= 4:
                    first_cell = cells[0].get_text(strip=True)
                    # First cell should be long text (outcome name), not a number
                    if first_cell and len(first_cell) > 8 and not re.match(r'^[\d.,\-\s\(\)]+$', first_cell):
                        outcome_found = True
                        break
            if outcome_found:
                return 'comparison_format'
    
    # NEW: Check for outcomes-in-rows with SE in separate rows pattern
    # Look at data rows: if alternating pattern of coefficient row + SE-only row
    if len(rows) >= 4:
        se_row_count = 0
        coef_row_count = 0
        
        for row in rows[2:min(8, len(rows))]:  # Check rows 2-7
            cells = row.find_all(['td', 'th'])
            if len(cells) > 1:
                first_cell = cells[0].get_text(strip=True)
                second_cell = cells[1].get_text(strip=True) if len(cells) > 1 else ''
                
                # Handle European format in SE: (0,05) 
                first_cell_normalized = first_cell.replace(',', '.')
                second_cell_normalized = second_cell.replace(',', '.')
                
                # SE row pattern 1: SE in first column like "(0.05)"
                if re.match(r'^\([\d.]+\)$', first_cell_normalized):
                    se_row_count += 1
                # SE row pattern 2: SE in second column
                elif re.match(r'^\([\d.]+\)$', second_cell_normalized):
                    se_row_count += 1
                # Coefficient row: outcome name in col 0, number with stars in data cols
                elif first_cell and len(first_cell) > 3 and re.search(r'-?[\d.,]+[\*†‡]*', second_cell):
                    coef_row_count += 1
        
        # If we see alternating pattern, it's outcomes-in-rows with split SE
        if se_row_count >= 2 and coef_row_count >= 2:
            return 'outcomes_in_rows_se_split'
    
    return 'columns'
