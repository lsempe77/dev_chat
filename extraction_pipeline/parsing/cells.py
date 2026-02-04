"""
Cell Parsing
============

Parse numeric values from table cells.
"""

import re
import sys
import os

# Add src to path for significance parser
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from src.extraction.significance import SignificanceParser

# Initialize significance parser (reuse across all tables)
_significance_parser = SignificanceParser(use_llm_fallback=False)  # Rules-only for speed


def parse_cell_comprehensive(cell_text: str) -> dict:
    """
    Parse all numeric values from a table cell.
    
    Handles multiple formats:
    - "0.15*** (0.05)"              → coef, SE
    - "0.15 [0.05, 0.25]"           → coef, CI
    - "0.15*** (0.05) [0.05, 0.25]" → coef, SE, CI
    - "2.45"                        → t-stat (context-dependent)
    
    Returns dict with all parsed values.
    """
    result = {
        'coefficient': None,
        'standard_error': None,
        't_statistic': None,
        'ci_lower': None,
        'ci_upper': None,
        'significance': None,
        'p_value': None,
        'p_value_text': None,
    }
    
    if not cell_text or cell_text.strip() == "":
        return result
    
    text = cell_text.strip()
    
    # Handle European number format (commas as decimal separators)
    # Only convert if it looks like European format (e.g., "0,15" not "1,234,567")
    # Pattern: single comma between digits, not followed by another comma group
    if re.search(r'-?\d+,\d{1,3}(?!\d*,)', text):
        # Likely European format - convert commas to dots
        text = re.sub(r'(\d),(\d)', r'\1.\2', text)
    
    # Use SignificanceParser for significance indicators
    sig_result = _significance_parser.parse_cell(text)
    result['significance'] = sig_result.raw_indicator if sig_result.indicator_type == "stars" else ""
    result['p_value'] = sig_result.p_value_threshold or sig_result.p_value_exact
    result['p_value_text'] = sig_result.p_value_text
    
    # Extract p-value from single number in brackets [0.347] (q-value / FDR-adjusted p-value)
    # This must come BEFORE CI extraction to avoid confusion
    # Pattern: single number in brackets, not two numbers separated by comma/dash
    bracket_single = re.search(r'\[(\d+\.?\d*)\]', text)
    if bracket_single:
        bracket_val = float(bracket_single.group(1))
        # If it looks like a p-value (between 0 and 1), use it
        if 0 <= bracket_val <= 1 and result['p_value'] is None:
            result['p_value'] = bracket_val
            result['p_value_text'] = str(bracket_val)
    
    # Extract CI bounds: [0.05, 0.25] or (0.05, 0.25) with comma or 95% CI patterns
    # Note: Only matches TWO numbers in brackets (CI), not single number (p-value)
    ci_patterns = [
        r'\[(-?\d+\.?\d*)\s*,\s*(-?\d+\.?\d*)\]',  # [0.05, 0.25]
        r'\[(-?\d+\.?\d*)\s*[-–]\s*(-?\d+\.?\d*)\]',  # [0.05-0.25] or [0.05–0.25]
        r'95%?\s*CI:?\s*\(?(-?\d+\.?\d*)\s*[-–,]\s*(-?\d+\.?\d*)\)?',  # 95% CI: 0.05-0.25
        r'CI\s*[:=]?\s*\[?(-?\d+\.?\d*)\s*[-–,]\s*(-?\d+\.?\d*)\]?',  # CI: 0.05, 0.25
    ]
    
    for pattern in ci_patterns:
        ci_match = re.search(pattern, text, re.IGNORECASE)
        if ci_match:
            result['ci_lower'] = float(ci_match.group(1))
            result['ci_upper'] = float(ci_match.group(2))
            break
    
    # Extract SE from parentheses (most common format)
    # But distinguish from CI which uses brackets or comma-separated
    paren_match = re.search(r'\(([^)]+)\)', text)
    if paren_match:
        paren_content = paren_match.group(1)
        # Check if it's a CI (has comma or dash between numbers)
        if not re.search(r'-?\d+\.?\d*\s*[-–,]\s*-?\d+\.?\d*', paren_content):
            paren_nums = re.findall(r'-?\d+\.?\d*', paren_content)
            if paren_nums and len(paren_nums) == 1:
                result['standard_error'] = float(paren_nums[0])
    
    # Extract coefficient (number not in parentheses/brackets, before significance)
    # Remove CI and SE portions first
    text_for_coef = text
    text_for_coef = re.sub(r'\[.*?\]', '', text_for_coef)  # Remove brackets
    text_for_coef = re.sub(r'\(.*?\)', '', text_for_coef)  # Remove parens
    text_for_coef = re.sub(r'[\*†‡§]+', '', text_for_coef)  # Remove significance markers
    
    coef_nums = re.findall(r'-?\d+\.?\d*', text_for_coef)
    if coef_nums:
        result['coefficient'] = float(coef_nums[0])
    
    return result


def parse_coefficient_se(cell_text: str) -> tuple:
    """
    Parse coefficient and SE from cell text.
    Handles: "0.15*** (0.05)", "(0.04) 0.18***", "0.12***"
    Returns: (coefficient, standard_error, significance_stars, p_value, p_value_text)
    
    Note: For full extraction including CI, use parse_cell_comprehensive()
    """
    parsed = parse_cell_comprehensive(cell_text)
    return (
        parsed['coefficient'],
        parsed['standard_error'],
        parsed['significance'],
        parsed['p_value'],
        parsed['p_value_text']
    )
