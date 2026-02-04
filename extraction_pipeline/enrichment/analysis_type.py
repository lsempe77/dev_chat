"""
Analysis Type Classification
============================

Classify analysis types: main effects, subgroups, spillovers, etc.
"""

import re
import pandas as pd
from ..core.llm_client import call_llm


def classify_analysis_type(df: pd.DataFrame) -> pd.DataFrame:
    """
    Use LLM reasoning to classify each extracted row's analysis type.
    
    Detects:
    - Main effects vs subgroup analyses (heterogeneous treatment effects)
    - Spillover effects (effects on non-beneficiaries)
    - Cost-related outcomes
    - Mechanism/mediator analyses
    
    Uses table caption, section header, outcome name, and treatment arm
    to make intelligent classifications.
    """
    if df.empty:
        return df
    
    df = df.copy()
    
    # Initialize columns
    df['is_main_effect'] = True
    df['is_subgroup'] = False
    df['subgroup_variable'] = None
    df['is_spillover'] = False
    df['spillover_type'] = None
    df['is_cost_outcome'] = False
    df['is_mechanism'] = False
    
    # Get unique table contexts to classify
    table_contexts = df.groupby(['table_number', 'table_caption', 'section']).first().reset_index()
    
    if len(table_contexts) == 0:
        return df
    
    # Build context strings for LLM
    contexts_for_llm = []
    for _, row in table_contexts.iterrows():
        ctx = f"Table: {row.get('table_number', 'Unknown')}\n"
        ctx += f"Caption: {row.get('table_caption', '')}\n"
        ctx += f"Section: {row.get('section', '')}"
        contexts_for_llm.append(ctx)
    
    prompt = f"""You are an expert at analyzing impact evaluation research papers.

For each table below, classify the analysis type. Think step-by-step:

1. Is this a MAIN EFFECT (primary treatment effect on full sample)?
2. Is this a SUBGROUP analysis (heterogeneous effects by gender, age, region, baseline characteristics)?
   - If yes, what is the subgroup variable?
3. Is this a SPILLOVER analysis (effects on non-beneficiaries, neighbors, comparison group)?
   - If yes, what type? (within-household, within-village, general equilibrium)
4. Does this analyze COST outcomes (program costs, cost-effectiveness, cost-benefit)?
5. Is this a MECHANISM/MEDIATOR analysis (intermediate outcomes explaining how treatment works)?

TABLES TO CLASSIFY:
{chr(10).join(f'---{chr(10)}[{i}]{chr(10)}{ctx}' for i, ctx in enumerate(contexts_for_llm))}

Return one line per table in this EXACT format:
[index]|main_effect:yes/no|subgroup:yes/no|subgroup_var:VARIABLE_OR_NONE|spillover:yes/no|spillover_type:TYPE_OR_NONE|cost:yes/no|mechanism:yes/no

Example outputs:
[0]|main_effect:yes|subgroup:no|subgroup_var:none|spillover:no|spillover_type:none|cost:no|mechanism:no
[1]|main_effect:no|subgroup:yes|subgroup_var:gender|spillover:no|spillover_type:none|cost:no|mechanism:no
[2]|main_effect:no|subgroup:no|subgroup_var:none|spillover:yes|spillover_type:within-village|cost:no|mechanism:no"""

    response = call_llm(prompt, max_tokens=2000)
    result = response.content if hasattr(response, 'content') else str(response)
    
    # Parse LLM response
    classifications = {}
    for line in result.split('\n'):
        line = line.strip()
        if not line.startswith('['):
            continue
        try:
            idx_match = re.match(r'\[(\d+)\](.+)', line)
            if not idx_match:
                continue
            idx = int(idx_match.group(1))
            rest = idx_match.group(2)
            
            parts = rest.split('|')
            parsed = {}
            for part in parts:
                if ':' in part:
                    key, val = part.split(':', 1)
                    key = key.strip().lower()
                    val = val.strip().lower()
                    parsed[key] = val
            
            classifications[idx] = {
                'is_main_effect': parsed.get('main_effect', 'yes') == 'yes',
                'is_subgroup': parsed.get('subgroup', 'no') == 'yes',
                'subgroup_variable': parsed.get('subgroup_var', 'none') if parsed.get('subgroup_var', 'none') != 'none' else None,
                'is_spillover': parsed.get('spillover', 'no') == 'yes',
                'spillover_type': parsed.get('spillover_type', 'none') if parsed.get('spillover_type', 'none') != 'none' else None,
                'is_cost_outcome': parsed.get('cost', 'no') == 'yes',
                'is_mechanism': parsed.get('mechanism', 'no') == 'yes',
            }
        except Exception as e:
            print(f"    [WARN] Failed to parse analysis classification: {e}")
            continue
    
    # Apply classifications to dataframe
    for idx, row in table_contexts.iterrows():
        if idx in classifications:
            cls = classifications[idx]
            mask = (
                (df['table_number'] == row['table_number']) & 
                (df['table_caption'] == row['table_caption'])
            )
            for col, val in cls.items():
                df.loc[mask, col] = val
    
    return df
