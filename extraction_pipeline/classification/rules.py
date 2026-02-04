"""
Rules-Based Table Classification
================================

Classify tables using regex patterns and keywords.
"""

import re


def classify_table_rules(caption: str, html: str = '') -> str:
    """
    Rules-based table classification with multilingual support.
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
    
    # Rule 3: RESULTS indicators (check FIRST - these are strong signals)
    # English keywords
    results_keywords_en = [
        'impact', 'effect', 'treatment effect', 'regression', 'coefficient', 
        'estimate', 'itt', 'atet', 'ate', 'did', 'difference-in-diff',
        'treatment impact', 'program effect', 'intervention effect',
        'average treatment', 'intent to treat', 'heterogeneity',
    ]
    # Spanish keywords (common in Latin America studies)
    results_keywords_es = [
        'impacto', 'efecto', 'coeficiente', 'diferencia de medias',
        'impactos de la', 'efectos de la', 'regresión',
    ]
    # Portuguese keywords
    results_keywords_pt = [
        'impacto', 'efeito', 'coeficiente',
    ]
    # French keywords
    results_keywords_fr = [
        'effet', 'impact', 'coefficient',
    ]
    
    all_results_keywords = results_keywords_en + results_keywords_es + results_keywords_pt + results_keywords_fr
    
    # Check if caption has results keywords
    has_results_keyword = any(kw in caption_lower for kw in all_results_keywords)
    
    # Rule 4: EXCLUSION - Sample/composition tables (BUT only if no results keywords)
    sample_keywords = [
        'number of', 'sample size', 'households in', 'villages in', 
        'number of treatment', 'number of control', 'sample composition',
        'randomization test', 'allocation', 'assignment',
    ]
    is_sample_table = any(kw in caption_lower for kw in sample_keywords)
    
    # If has results keyword, it's a results table (even if has "baseline")
    if has_results_keyword and not is_sample_table:
        return 'results'
    
    # Rule 5: Check HTML for coefficient patterns (numbers with stars and parens)
    if html:
        # Look for patterns like "0.103***" or "0.15 (0.05)"
        if re.search(r'-?\d+\.\d+\s*\*{1,3}', html):
            return 'results'
        # Look for header pattern indicating transposed results table
        if re.search(r'(mean\s*effect|standard\s*error|p[\s-]*value)', html.lower()):
            return 'results'
    
    # Rule 6: Descriptive tables (only if NO results keywords present)
    # Be more specific to avoid false positives
    descriptive_patterns = [
        'baseline characteristics',
        'balance table', 'balance of baseline', 'baseline balance',
        'attrition', 'compliance',
        'variable definition', 'variable construction', 'hypothesis',
        'summary statistics', 'sample characteristics', 'descriptive statistics',
        'randomization test',
    ]
    if any(p in caption_lower for p in descriptive_patterns):
        return 'descriptive'
    
    # Rule 7: Sample composition tables
    if is_sample_table:
        return 'descriptive'
    
    # Rule 8: Appendix tables often contain results
    if re.search(r'(appendix|annex)\s*(table|tabla|tableau)', caption_lower):
        return 'unknown'  # Let LLM decide - could be either
    
    # Rule 9: Has "table" in caption → likely contains data
    if 'table' in caption_normalized or 'tabla' in caption_normalized:
        return 'unknown'  # Let LLM decide or default to results
    
    return 'unknown'
