"""
LLM-Based Table Classification
==============================

Use LLM to classify ambiguous tables.
"""

import json
from loguru import logger

from ..core.llm_client import call_llm


def classify_all_tables_llm(table_inventory: list[dict]) -> dict[str, str]:
    """
    Two-pass table classification: Send ALL table captions to LLM at once.
    
    The LLM sees the full context of all tables and can make smarter decisions
    about which ones contain treatment effects vs. descriptive statistics.
    
    Args:
        table_inventory: List of dicts with 'table_id', 'caption', 'preview' keys
        
    Returns:
        Dict mapping table_id -> 'results' or 'descriptive'
    """
    if not table_inventory:
        return {}
    
    # Build the table list for the prompt
    table_list = []
    for t in table_inventory:
        preview = t.get('preview', '')[:200]  # First 200 chars of content
        table_list.append(f"- {t['table_id']}: {t['caption']}\n  Preview: {preview}")
    
    tables_text = "\n".join(table_list)
    
    prompt = f"""You are an expert at analyzing academic impact evaluation papers.

TASK: Identify which tables contain TREATMENT EFFECT ESTIMATES that should be extracted.

WHAT TO EXTRACT (mark as "results"):
- Regression tables showing causal impact estimates (ITT, ATT, LATE, DiD)
- Tables with coefficients and standard errors in parentheses like "0.15*** (0.05)"
- Tables showing program effects on outcomes (consumption, income, assets, health, etc.)
- Heterogeneity analysis tables (effects by subgroup, baseline characteristics)
- Tables in Spanish/Portuguese with "impacto", "efecto", "coeficiente"
- Tables in French with "effet", "impact"

WHAT TO SKIP (mark as "descriptive"):
- Sample composition tables ("Number of treatment/control villages")
- Balance tables comparing treatment and control at baseline
- "Baseline characteristics" tables (unless they show treatment EFFECTS)
- Summary statistics and means without treatment effects
- Variable definitions and data description
- Attrition and compliance tables
- Randomization test tables

IMPORTANT: A table mentioning "treatment" is NOT necessarily a treatment effect table.
"Table 6: Number of treatment villages" describes sample SIZE → SKIP
"Table 12: Treatment effects on consumption" contains regression results → EXTRACT
"Table 3: Impacts by baseline asset level" is heterogeneity analysis → EXTRACT

Here are all tables from this paper:
{tables_text}

Return a JSON object mapping each table ID to either "results" or "descriptive".
Example: {{"Table1": "descriptive", "Table2": "results", "Table3": "results"}}

Reply with ONLY the JSON object, no other text."""

    response = call_llm(prompt, max_tokens=2000)
    result = response.content if hasattr(response, 'content') else str(response)
    
    # Parse the JSON response
    try:
        # Clean up response (remove markdown code blocks if present)
        result = result.strip()
        if result.startswith('```'):
            result = result.split('\n', 1)[1]
            if result.endswith('```'):
                result = result.rsplit('```', 1)[0]
        result = result.strip()
        
        classifications = json.loads(result)
        
        # Validate and normalize
        valid_classes = {}
        for table_id, classification in classifications.items():
            if classification.lower() in ['results', 'descriptive']:
                valid_classes[table_id] = classification.lower()
            else:
                valid_classes[table_id] = 'results'  # Default to extracting
        
        return valid_classes
        
    except (json.JSONDecodeError, AttributeError) as e:
        logger.warning(f"Failed to parse LLM classification response: {e}")
        # Fallback: classify all as results
        return {t['table_id']: 'results' for t in table_inventory}


def classify_table_llm(caption: str, html_preview: str) -> str:
    """
    LLM-based table classification for ambiguous cases (single table).
    Used as fallback when two-pass classification isn't available.
    """
    prompt = f"""You are classifying tables from an academic impact evaluation paper.

TASK: Does this table contain TREATMENT EFFECTS (regression coefficients with standard errors)?

Classification:
- "results": Contains regression coefficients, treatment effects, impact estimates with standard errors in parentheses like "0.15*** (0.05)"
- "descriptive": Contains summary statistics, means, balance tests, variable definitions, sample characteristics

IMPORTANT: A table mentioning "treatment" is NOT necessarily a treatment effect table.
"Number of treatment villages" = descriptive (sample sizes)
"Treatment effects on consumption" = results (regression coefficients)

Caption: {caption if caption else "[No caption]"}

Table HTML preview:
{html_preview[:800]}

Reply with ONLY one word: results or descriptive"""

    response = call_llm(prompt, max_tokens=10)
    result = response.content if hasattr(response, 'content') else str(response)
    
    if result.lower() in ['results', 'descriptive']:
        return result.lower()
    return 'results'  # Default to extracting
