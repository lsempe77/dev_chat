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
    - Robustness checks
    - Intent-to-treat vs treatment-on-treated
    
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
    df['is_robustness'] = False
    df['estimand_type'] = 'ITT'  # Default to Intent-to-Treat
    
    # Get unique table contexts to classify
    table_contexts = df.groupby(['table_number', 'table_caption', 'section']).first().reset_index()
    
    if len(table_contexts) == 0:
        return df
    
    # Build context strings for LLM - include treatment_arm info for better subgroup detection
    contexts_for_llm = []
    for _, row in table_contexts.iterrows():
        # Get unique treatment arms for this table
        mask = (df['table_number'] == row['table_number']) & (df['table_caption'] == row['table_caption'])
        treatment_arms = df.loc[mask, 'treatment_arm'].dropna().unique().tolist()[:10]
        
        ctx = f"Table: {row.get('table_number', 'Unknown')}\n"
        ctx += f"Caption: {row.get('table_caption', '')}\n"
        ctx += f"Section: {row.get('section', '')}\n"
        ctx += f"Treatment arms found: {', '.join(str(a) for a in treatment_arms) if treatment_arms else 'Not specified'}"
        contexts_for_llm.append(ctx)

    prompt = f"""You are an expert at analyzing impact evaluation research papers.

For each table below, classify the analysis type. Think step-by-step about each classification.

=== CLASSIFICATION CATEGORIES ===

1. **MAIN EFFECT**: Primary treatment effect on full sample
   - Examples: "Treatment impact on consumption", "Program effects on income"
   
2. **SUBGROUP ANALYSIS**: Heterogeneous treatment effects by characteristics
   - MUST identify the subgroup_variable (the dimension of heterogeneity)
   - Common subgroup variables:
     * Demographics: gender, age, age_group, marital_status, household_head_gender
     * Geography: region, district, urban_rural, province, state
     * Baseline characteristics: baseline_assets, baseline_income, poverty_level, asset_quartile
     * Timing: cohort, wave, follow_up_period, enrollment_year
     * Program intensity: treatment_dose, compliance_level, exposure_duration
     * Education: education_level, literacy, schooling_years
     * Occupation: employment_status, occupation_type, farming_status
   - Signs: "by gender", "heterogeneous effects", "× Female", "interaction terms"
   
3. **SPILLOVER ANALYSIS**: Effects on non-beneficiaries
   - Types: within_household, within_village, within_community, general_equilibrium, peer_effects
   - Signs: "spillover", "indirect effects", "non-beneficiaries", "neighbors"
   
4. **COST OUTCOMES**: Program costs and cost-effectiveness
   - Signs: "cost per", "cost-benefit", "cost-effectiveness", "$", "return on investment"
   
5. **MECHANISM/MEDIATOR**: Intermediate outcomes explaining causal pathways
   - Signs: "mechanism", "pathway", "mediator", "channel", "knowledge", "behavior change"
   
6. **ROBUSTNESS CHECK**: Alternative specifications, sensitivity analysis
   - Signs: "robustness", "alternative", "sensitivity", "excluding", "placebo"
   
7. **ESTIMAND TYPE**: What causal estimand is being reported
   - ITT (Intent-to-Treat): Effect of being assigned to treatment
   - TOT (Treatment-on-Treated): Effect on those who actually received treatment
   - LATE (Local Average Treatment Effect): IV estimate for compliers
   - Signs: "ITT", "TOT", "LATE", "IV", "2SLS", "compliers", "treatment on treated"

=== TABLES TO CLASSIFY ===
{chr(10).join(f'---{chr(10)}[{i}]{chr(10)}{ctx}' for i, ctx in enumerate(contexts_for_llm))}

=== RESPONSE FORMAT ===
Return one line per table in this EXACT format:
[index]|main_effect:yes/no|subgroup:yes/no|subgroup_var:VARIABLE_NAME_OR_none|spillover:yes/no|spillover_type:TYPE_OR_none|cost:yes/no|mechanism:yes/no|robustness:yes/no|estimand:ITT/TOT/LATE

For subgroup_var, use a standardized variable name from the list above (e.g., "gender", "asset_quartile", "region").
If multiple subgroup variables, use the primary one.

=== EXAMPLES ===
[0]|main_effect:yes|subgroup:no|subgroup_var:none|spillover:no|spillover_type:none|cost:no|mechanism:no|robustness:no|estimand:ITT
[1]|main_effect:no|subgroup:yes|subgroup_var:gender|spillover:no|spillover_type:none|cost:no|mechanism:no|robustness:no|estimand:ITT
[2]|main_effect:no|subgroup:yes|subgroup_var:asset_quartile|spillover:no|spillover_type:none|cost:no|mechanism:no|robustness:no|estimand:ITT
[3]|main_effect:no|subgroup:no|subgroup_var:none|spillover:yes|spillover_type:within_village|cost:no|mechanism:no|robustness:no|estimand:ITT
[4]|main_effect:no|subgroup:no|subgroup_var:none|spillover:no|spillover_type:none|cost:yes|mechanism:no|robustness:no|estimand:ITT
[5]|main_effect:no|subgroup:no|subgroup_var:none|spillover:no|spillover_type:none|cost:no|mechanism:yes|robustness:no|estimand:ITT
[6]|main_effect:no|subgroup:no|subgroup_var:none|spillover:no|spillover_type:none|cost:no|mechanism:no|robustness:yes|estimand:ITT
[7]|main_effect:yes|subgroup:no|subgroup_var:none|spillover:no|spillover_type:none|cost:no|mechanism:no|robustness:no|estimand:TOT"""

    response = call_llm(prompt, max_tokens=2500)
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
            
            # Normalize subgroup variable
            subgroup_var = parsed.get('subgroup_var', 'none')
            if subgroup_var in ['none', 'null', '']:
                subgroup_var = None
            else:
                # Standardize common variations
                subgroup_var_map = {
                    'sex': 'gender',
                    'male/female': 'gender', 
                    'men/women': 'gender',
                    'location': 'region',
                    'geographic': 'region',
                    'area': 'urban_rural',
                    'rural/urban': 'urban_rural',
                    'wealth': 'asset_quartile',
                    'income_level': 'baseline_income',
                    'poor/non-poor': 'poverty_level',
                    'time': 'follow_up_period',
                    'period': 'follow_up_period',
                    'wave': 'follow_up_period',
                    'age_category': 'age_group',
                    'young/old': 'age_group',
                }
                if subgroup_var and isinstance(subgroup_var, str):
                    subgroup_var = subgroup_var_map.get(subgroup_var, subgroup_var)
            
            # Normalize spillover type
            spillover_type = parsed.get('spillover_type', 'none')
            if spillover_type in ['none', 'null', '']:
                spillover_type = None
            
            # Normalize estimand type
            estimand = parsed.get('estimand', 'itt').upper()
            if estimand not in ['ITT', 'TOT', 'LATE', 'ATE', 'ATT', 'ATET']:
                estimand = 'ITT'
            
            classifications[idx] = {
                'is_main_effect': parsed.get('main_effect', 'yes') == 'yes',
                'is_subgroup': parsed.get('subgroup', 'no') == 'yes',
                'subgroup_variable': subgroup_var,
                'is_spillover': parsed.get('spillover', 'no') == 'yes',
                'spillover_type': spillover_type,
                'is_cost_outcome': parsed.get('cost', 'no') == 'yes',
                'is_mechanism': parsed.get('mechanism', 'no') == 'yes',
                'is_robustness': parsed.get('robustness', 'no') == 'yes',
                'estimand_type': estimand,
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
