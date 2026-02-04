"""
Context Enrichment
==================

Use LLM to enrich extracted data with outcome definitions.
"""

import pandas as pd
from ..core.llm_client import call_llm


def enrich_with_context(df: pd.DataFrame, doc: dict) -> pd.DataFrame:
    """Use LLM to enrich extracted data with outcome definitions."""
    if df.empty:
        return df
    
    # Get unique outcomes
    outcomes = df['outcome_name'].unique().tolist()[:15]  # Limit to 15
    prose = doc.get('content', '')[:20000]  # First 20k chars
    
    prompt = f"""Given this paper excerpt and list of outcome variables, provide brief definitions.

OUTCOME VARIABLES:
{chr(10).join(f'- {o}' for o in outcomes)}

PAPER TEXT:
{prose[:15000]}

For each outcome, provide a one-sentence definition based on the paper.
Format each line as: outcome_name|definition

Only include outcomes you can find definitions for in the text."""

    response = call_llm(prompt, max_tokens=1000)
    result = response.content if hasattr(response, 'content') else str(response)
    
    definitions = {}
    for line in result.split('\n'):
        if '|' in line:
            parts = line.split('|', 1)
            if len(parts) == 2:
                definitions[parts[0].strip()] = parts[1].strip()
    
    # Add definitions to dataframe
    df['outcome_definition'] = df['outcome_name'].map(
        lambda x: next((v for k, v in definitions.items() if k.lower() in x.lower()), None)
    )
    
    print(f"    Added definitions for {len(definitions)} outcomes")
    
    return df
