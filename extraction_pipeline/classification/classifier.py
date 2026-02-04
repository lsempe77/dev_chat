"""
Table Classifier
================

Main entry point for table classification.
Uses rules first, then LLM for ambiguous cases.
"""

from .rules import classify_table_rules
from .llm import classify_table_llm


def classify_table(caption: str, html: str, use_llm: bool = True) -> str:
    """
    Classify table using rules first, then LLM for ambiguous cases.
    
    Args:
        caption: Table caption text
        html: Table HTML content
        use_llm: Whether to use LLM for ambiguous cases
        
    Returns:
        'results', 'descriptive', or 'figure'
    """
    # First try rules-based (now includes HTML analysis)
    rules_result = classify_table_rules(caption, html)
    
    if rules_result in ['figure', 'descriptive', 'results']:
        return rules_result
    
    # For 'unknown', use LLM if enabled
    if use_llm and rules_result == 'unknown':
        return classify_table_llm(caption, html)
    
    return 'results'  # Default to extracting
