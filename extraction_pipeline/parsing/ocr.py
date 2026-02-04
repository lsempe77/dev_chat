"""
OCR Text Fixes
==============

Fix OCR-induced text issues from MinerU parsing.
"""

import re


def fix_ocr_spacing(text: str) -> str:
    """
    Fix OCR-induced character spacing issues.
    
    MineRU sometimes produces spaced-out text like:
    - "Ta b l e A . 1 2 : I n t ra- H o u se h o l d" → "Table A.12: Intra-Household"
    
    Strategy:
    1. Detect if text has excessive single-char spacing pattern
    2. Remove all single spaces between characters
    3. Restore word boundaries based on capital letters and common patterns
    """
    if not text:
        return text
    
    # Quick heuristic: if "T a b l e" or "Ta b l e" pattern exists, fix it
    if re.search(r'[Tt]\s*a\s+b\s+l\s+e', text):
        # Aggressive fix: remove ALL single spaces 
        result = re.sub(r'\s+', '', text)
        
        # Restore spaces before capital letters (word boundaries)
        # "TableA12IntraHousehold" → "Table A12 Intra Household"
        result = re.sub(r'([a-z])([A-Z])', r'\1 \2', result)
        
        # Restore colon spacing
        result = re.sub(r':(?=[A-Za-z0-9])', ': ', result)
        
        # Common patterns: "Table5" → "Table 5"
        result = re.sub(r'(Table)(\d)', r'\1 \2', result)
        result = re.sub(r'(Figure)(\d)', r'\1 \2', result)
        
        # Fix parentheses: "(Household)" needs space before
        result = re.sub(r'([a-z])\(', r'\1 (', result)
        
        return result
    
    return text
