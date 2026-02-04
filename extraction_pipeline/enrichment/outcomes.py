"""
Outcome Classification
======================

Classify outcomes into categories using LLM.
"""

import pandas as pd
from ..core.llm_client import call_llm


def classify_outcomes(df: pd.DataFrame, domain: str = 'graduation') -> pd.DataFrame:
    """
    Classify outcomes into categories using LLM.
    Uses domain-specific category list from DOMAIN_CONFIGS.
    Processes in batches to handle many outcomes.
    """
    if df.empty:
        return df
    
    # Import domain configs
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
    from src.extraction.schemas import DOMAIN_CONFIGS
    
    config = DOMAIN_CONFIGS.get(domain, DOMAIN_CONFIGS['generic'])
    categories = config.get('outcome_categories', ['Primary', 'Secondary'])
    
    # Get unique outcomes
    unique_outcomes = df['outcome_name'].unique().tolist()
    
    # Process in batches of 50
    all_mappings = {}
    batch_size = 50
    
    for i in range(0, len(unique_outcomes), batch_size):
        batch = unique_outcomes[i:i + batch_size]
        
        prompt = f"""Classify these outcome variables into categories.

CATEGORIES: {', '.join(categories)}

OUTCOMES:
{chr(10).join(f'- {o}' for o in batch)}

INSTRUCTIONS:
1. Classify EVERY outcome into the most appropriate category
2. Use exact category names from the list above
3. If unsure, use "Other" or the closest matching category

Return format (one per line, must classify ALL):
outcome_name|category"""

        response = call_llm(prompt, max_tokens=1500)
        result = response.content if hasattr(response, 'content') else str(response)
        
        # Parse response
        for line in result.split('\n'):
            if '|' in line:
                parts = line.split('|', 1)
                if len(parts) == 2:
                    outcome = parts[0].strip()
                    category = parts[1].strip()
                    # Match to closest category name (case insensitive)
                    matched_cat = None
                    for cat in categories:
                        if cat.lower() == category.lower():
                            matched_cat = cat
                            break
                    # If no exact match, try partial match
                    if not matched_cat:
                        for cat in categories:
                            if cat.lower() in category.lower() or category.lower() in cat.lower():
                                matched_cat = cat
                                break
                    if matched_cat:
                        all_mappings[outcome.lower()] = matched_cat
    
    # Apply mapping with fuzzy matching
    def find_category(outcome_name):
        # Exact match
        if outcome_name.lower() in all_mappings:
            return all_mappings[outcome_name.lower()]
        # Partial match
        for key, val in all_mappings.items():
            if key in outcome_name.lower() or outcome_name.lower() in key:
                return val
        return None
    
    df['outcome_category'] = df['outcome_name'].apply(find_category)
    
    return df
