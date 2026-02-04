"""
Pipeline V2 SOTA: Production-Ready Extraction for Impact Evaluation Papers

Features:
- Stage 1: Metadata extraction (direct from MineRU JSON)
- Stage 2: Table extraction (BeautifulSoup + rules-based filtering)
- Stage 3: LLM classification for ambiguous tables
- Stage 4: Context enrichment (LLM for outcome definitions)

Usage:
    python pipeline.py                    # Extract study 121058356
    python pipeline.py --study_id 12345   # Extract specific study
    python pipeline.py --all              # Extract all studies
"""

import json
import re
import os
import sys
import argparse
from typing import Optional, List, Dict, Any
from bs4 import BeautifulSoup
import pandas as pd
import boto3
from dotenv import load_dotenv
from openai import OpenAI

# Load environment variables
load_dotenv()

# Add src to path for settings
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from src.config.settings import Settings
from src.extraction.significance import SignificanceParser, parse_significance
from src.extraction.schemas import (
    ExtractedEstimate, CoreNumericFields, StudyMetadata, 
    OutcomeMetadata, InterventionMetadata, SourceLocation,
    ExtractionMode, EXTRACTION_FIELDS
)

# Import table extractors from modular components
from extraction_pipeline.parsing.ocr import fix_ocr_spacing
from extraction_pipeline.parsing.cells import parse_cell_comprehensive
from extraction_pipeline.extraction.extractors import (
    detect_table_orientation,
    extract_treatments_in_cols_table,
    extract_outcomes_in_rows_se_split,
    extract_comparison_format_table,
    extract_transposed_table,
    extract_results_table,
)

# Initialize settings
settings = Settings()

# Initialize significance parser (reuse across all tables)
significance_parser = SignificanceParser(use_llm_fallback=False)  # Rules-only for speed

# ============================================================================
# CONFIGURATION
# ============================================================================

DEFAULT_STUDY_ID = "121058356"
OUTPUT_DIR = "extraction_pipeline/outputs"

# LLM Configuration (via OpenRouter)
LLM_MODEL = "anthropic/claude-3.5-haiku"  # Cost-effective, fast model

# ============================================================================
# LLM CLIENT (via OpenRouter)
# ============================================================================

def get_openrouter_client():
    """Get OpenRouter client (uses OpenAI-compatible API)."""
    api_key = os.environ.get('OPENROUTER_API_KEY', settings.openrouter_api_key)
    return OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key
    )


def call_llm(prompt: str, max_tokens: int = 100) -> str:
    """Call LLM via OpenRouter."""
    try:
        client = get_openrouter_client()
        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=max_tokens
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"    [LLM ERROR] {e}")
        return ""

# ============================================================================
# R2 STORAGE
# ============================================================================

def get_r2_client():
    """Get R2 storage client."""
    return boto3.client(
        's3',
        endpoint_url=f"https://{os.environ['CLOUDFLARE_ACCOUNT_ID']}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ['R2_ACCESS_KEY_ID'],
        aws_secret_access_key=os.environ['R2_SECRET_ACCESS_KEY']
    )


def load_mineru_json(study_id: str) -> Optional[dict]:
    """Load MineRU JSON from R2 storage."""
    try:
        client = get_r2_client()
        prefix = "rags/0816e8d3-ab23-417c-bf3f-e45531411c73/outputs/json/"
        
        # List objects to find the file matching this study_id
        response = client.list_objects_v2(Bucket='devchat-pdfs', Prefix=prefix, MaxKeys=200)
        
        # Find file containing this study_id
        matching_key = None
        for obj in response.get('Contents', []):
            key = obj['Key']
            # Match study_id in filename (handles both numeric IDs and named studies)
            if f"_{study_id}." in key or f"_{study_id}_" in key:
                matching_key = key
                break
        
        if not matching_key:
            print(f"  [ERROR] No JSON found for study {study_id}")
            return None
            
        response = client.get_object(Bucket='devchat-pdfs', Key=matching_key)
        return json.loads(response['Body'].read().decode('utf-8'))
    except Exception as e:
        print(f"  [ERROR] Failed to load study {study_id}: {e}")
        return None

# ============================================================================
# STAGE 1: METADATA EXTRACTION
# ============================================================================

def extract_metadata(doc: dict, study_id: str) -> dict:
    """Extract paper metadata directly from MineRU JSON."""
    return {
        'study_id': study_id,
        'title': doc.get('title', ''),
        'authors': doc.get('authors', []),
        'year': doc.get('year', ''),
        'abstract': doc.get('abstract', ''),
        'page_count': doc.get('page_count', 0),
        'source_key': doc.get('source_key', '')
    }


def extract_metadata_llm(doc: dict, study_id: str) -> dict:
    """
    Extract comprehensive paper metadata using LLM.
    Fills gaps not captured by MineRU parsing.
    """
    # Get first ~4000 chars (title page + abstract + intro)
    content = doc.get('content', '')[:4000]
    abstract = doc.get('abstract', '')
    
    prompt = f"""Extract metadata from this academic paper. Return ONLY a JSON object with these fields.
If a field cannot be determined, use null.

PAPER TEXT:
{content}

ABSTRACT:
{abstract}

Return JSON with:
{{
  "authors": "Author1, Author2, Author3",
  "year": 2021,
  "country": "Niger",
  "countries_list": ["Niger"],
  "study_design": "RCT",
  "is_experimental": true,
  "intervention_name": "Multi-faceted graduation program",
  "follow_up_months": 18,
  "sample_description": "Female beneficiaries of cash transfer program"
}}

JSON only, no explanation:"""

    result = call_llm(prompt, max_tokens=300)
    
    # Parse JSON response
    try:
        import json as json_module
        # Clean up response (remove markdown code blocks if present)
        result = result.strip()
        if result.startswith('```'):
            result = result.split('```')[1]
            if result.startswith('json'):
                result = result[4:]
        result = result.strip()
        
        parsed = json_module.loads(result)
    except:
        parsed = {}
    
    # Merge with MineRU metadata (MineRU takes precedence for title, year if present)
    return {
        'study_id': study_id,
        'title': doc.get('title', ''),
        'authors': parsed.get('authors', '') or ', '.join(doc.get('authors', [])),
        'year': doc.get('year') or parsed.get('year'),
        'abstract': doc.get('abstract', ''),
        'page_count': doc.get('page_count', 0),
        'source_key': doc.get('source_key', ''),
        # NEW FIELDS from LLM
        'country': parsed.get('country'),
        'countries_list': parsed.get('countries_list', []),
        'study_design': parsed.get('study_design'),
        'is_experimental': parsed.get('is_experimental'),
        'intervention_name': parsed.get('intervention_name'),
        'follow_up_months': parsed.get('follow_up_months'),
        'sample_description': parsed.get('sample_description'),
    }


# ============================================================================
# EFFECT SIZE CALCULATIONS
# ============================================================================

def calculate_effect_sizes(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate standardized effect sizes from extracted data.
    
    Calculates:
    - Cohen's d: standardized mean difference
    - Hedges' g: bias-corrected SMD
    - Variance and SE of effect size
    
    Requires: coefficient, control_sd, sample_size (or n_treatment + n_control)
    """
    import math
    
    df = df.copy()
    
    # Initialize columns
    df['cohens_d'] = None
    df['hedges_g'] = None
    df['effect_variance'] = None
    df['effect_se'] = None
    
    for idx, row in df.iterrows():
        coef = row.get('coefficient')
        ctrl_sd = row.get('control_sd')
        n_total = row.get('sample_size')
        n_treat = row.get('n_treatment')
        n_ctrl = row.get('n_control')
        
        # Skip if missing key values
        if coef is None or ctrl_sd is None or ctrl_sd == 0:
            continue
        
        # Calculate Cohen's d
        d = coef / ctrl_sd
        df.at[idx, 'cohens_d'] = d
        
        # Get sample sizes
        if n_treat and n_ctrl:
            n1, n2 = n_treat, n_ctrl
        elif n_total:
            # Assume equal split if only total provided
            n1 = n2 = n_total / 2
        else:
            continue
        
        # Calculate variance of d
        # var(d) = (n1 + n2) / (n1 * n2) + d^2 / (2 * (n1 + n2))
        var_d = (n1 + n2) / (n1 * n2) + (d ** 2) / (2 * (n1 + n2))
        df.at[idx, 'effect_variance'] = var_d
        
        # Hedges' g correction factor (J)
        # J = 1 - 3 / (4 * (n1 + n2 - 2) - 1)
        df_total = n1 + n2 - 2
        if df_total > 0:
            j = 1 - 3 / (4 * df_total - 1)
            g = d * j
            df.at[idx, 'hedges_g'] = g
            
            # SE of g
            se_g = math.sqrt(var_d) * j
            df.at[idx, 'effect_se'] = se_g
    
    return df


def classify_outcomes(df: pd.DataFrame, domain: str = 'graduation') -> pd.DataFrame:
    """
    Classify outcomes into categories using LLM.
    Uses domain-specific category list from DOMAIN_CONFIGS.
    Processes in batches to handle many outcomes.
    """
    if df.empty:
        return df
    
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

        result = call_llm(prompt, max_tokens=1500)
        
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

    result = call_llm(prompt, max_tokens=2000)
    
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


def row_to_extracted_estimate(row: dict, metadata: dict = None) -> ExtractedEstimate:
    """
    Convert a flat pipeline result dict to an ExtractedEstimate Pydantic object.
    
    This enables schema validation and downstream integrations that expect
    the structured ExtractedEstimate format.
    
    Args:
        row: Single result row from extract_results_table()
        metadata: Optional study metadata dict from extract_metadata()
        
    Returns:
        ExtractedEstimate object with validated fields
    """
    # Map study metadata
    study_meta = StudyMetadata(
        study_id=row.get('study_id', ''),
        title=metadata.get('title', '') if metadata else '',
        authors=metadata.get('authors', []) if metadata else [],
        year=metadata.get('year') if metadata else None,
        country=metadata.get('country') if metadata else None,
        intervention_type=metadata.get('intervention_type') if metadata else None
    )
    
    # Map outcome metadata
    outcome_meta = OutcomeMetadata(
        outcome_name=row.get('outcome_name', ''),
        outcome_definition=row.get('outcome_definition'),
        outcome_category=row.get('outcome_category'),
        outcome_timepoint=row.get('outcome_timepoint'),
        outcome_unit=row.get('outcome_unit')
    )
    
    # Map intervention metadata
    intervention_meta = InterventionMetadata(
        treatment_arm=row.get('treatment_arm', ''),
        comparison_group=row.get('control_group'),
        intervention_description=row.get('intervention_description')
    )
    
    # Map source location
    source = SourceLocation(
        table_number=row.get('table_number'),
        table_caption=row.get('table_caption'),
        page_number=row.get('page_number'),
        section=row.get('section'),
        figure_number=row.get('figure_number'),
        literal_text=row.get('literal_cell_text')
    )
    
    # Create the full ExtractedEstimate
    return ExtractedEstimate(
        study=study_meta,
        outcome=outcome_meta,
        intervention=intervention_meta,
        source=source,
        # Core numeric fields
        point_estimate=row.get('coefficient'),
        standard_error=row.get('standard_error'),
        p_value=row.get('p_value'),
        p_value_text=row.get('p_value_text'),
        significance_indicator=row.get('significance'),
        sample_size=row.get('sample_size'),
        control_mean=row.get('control_mean'),
        control_sd=row.get('control_sd'),
        # Extraction provenance
        extraction_mode=ExtractionMode.FULL,
        confidence_score=None  # Could be added based on SE coverage etc.
    )


def convert_to_schema(df: pd.DataFrame, metadata: dict = None) -> List[ExtractedEstimate]:
    """
    Convert entire DataFrame of pipeline results to ExtractedEstimate objects.
    
    Useful for:
    - Schema validation of pipeline output
    - Integration with downstream systems expecting structured format
    - Exporting to JSON with proper typing
    
    Args:
        df: DataFrame from extract_all_tables()
        metadata: Study metadata dict from extract_metadata()
        
    Returns:
        List of validated ExtractedEstimate objects
    """
    estimates = []
    for _, row in df.iterrows():
        try:
            estimate = row_to_extracted_estimate(row.to_dict(), metadata)
            estimates.append(estimate)
        except Exception as e:
            print(f"    [WARN] Row conversion failed: {e}")
    return estimates

# ============================================================================
# STAGE 2: TABLE CLASSIFICATION
# ============================================================================

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

    result = call_llm(prompt, max_tokens=2000)
    
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

    result = call_llm(prompt, max_tokens=10)
    if result.lower() in ['results', 'descriptive']:
        return result.lower()
    return 'results'  # Default to extracting


def classify_table(caption: str, html: str, use_llm: bool = True) -> str:
    """
    Classify table using rules first, then LLM for ambiguous cases.
    """
    # First try rules-based (now includes HTML analysis)
    rules_result = classify_table_rules(caption, html)
    
    if rules_result in ['figure', 'descriptive', 'results']:
        return rules_result
    
    # For 'unknown', use LLM if enabled
    if use_llm and rules_result == 'unknown':
        return classify_table_llm(caption, html)
    
    return 'results'  # Default to extracting

# ============================================================================
# STAGE 3: TABLE PARSING (BeautifulSoup)
# ============================================================================

def extract_sample_sizes_from_table(table: dict, outcome_names: List[str]) -> Dict[str, Dict[str, int]]:
    """
    Extract N_treatment, N_control, and N_clusters from table rows.
    
    Returns dict with structure:
    {
        'section_name': {
            'outcome_name': {
                'n_treatment': int,
                'n_control': int,
                'n_total': int,
                'n_clusters': int
            }
        }
    }
    """
    html = table.get('table_body', '')
    soup = BeautifulSoup(html, 'html.parser')
    rows = soup.find_all('tr')
    
    sample_sizes = {}
    current_section = None
    
    # Patterns for identifying sample size rows
    n_treat_patterns = [
        r'n\s*treatment', r'n\s*treated', r'obs\.?\s*treatment', 
        r'treatment\s*n', r'treated\s*n', r'treatment\s*obs',
        r'n_t', r'n1'
    ]
    n_ctrl_patterns = [
        r'n\s*control', r'obs\.?\s*control', r'control\s*n',
        r'control\s*obs', r'comparison\s*n', r'n_c', r'n0'
    ]
    n_total_patterns = [
        r'observation', r'n\s*$', r'^n$', r'sample\s*size',
        r'total\s*n', r'n\s*total'
    ]
    cluster_patterns = [
        r'cluster', r'school', r'village', r'community', 
        r'household', r'group', r'site'
    ]
    
    for row in rows:
        cells = row.find_all('td')
        if not cells:
            continue
        
        first_cell = cells[0].get_text(strip=True)
        first_cell_lower = first_cell.lower()
        
        # Track section
        if 'followup' in first_cell_lower or 'follow-up' in first_cell_lower:
            current_section = first_cell
            if current_section not in sample_sizes:
                sample_sizes[current_section] = {}
            continue
        
        # Ensure current section is initialized
        if current_section is None:
            current_section = 'default'
        if current_section not in sample_sizes:
            sample_sizes[current_section] = {}
        
        # Check row type
        row_type = None
        for pattern in n_treat_patterns:
            if re.search(pattern, first_cell_lower, re.IGNORECASE):
                row_type = 'n_treatment'
                break
        if not row_type:
            for pattern in n_ctrl_patterns:
                if re.search(pattern, first_cell_lower, re.IGNORECASE):
                    row_type = 'n_control'
                    break
        if not row_type:
            for pattern in n_total_patterns:
                if re.search(pattern, first_cell_lower, re.IGNORECASE):
                    row_type = 'n_total'
                    break
        if not row_type:
            for pattern in cluster_patterns:
                if re.search(pattern, first_cell_lower, re.IGNORECASE):
                    row_type = 'n_clusters'
                    break
        
        if row_type:
            for i, cell in enumerate(cells[1:]):
                if i >= len(outcome_names):
                    break
                outcome = outcome_names[i]
                if outcome not in sample_sizes[current_section]:
                    sample_sizes[current_section][outcome] = {}
                
                # Extract number from cell
                nums = re.findall(r'\d+', cell.get_text(strip=True).replace(',', ''))
                if nums:
                    sample_sizes[current_section][outcome][row_type] = int(nums[0])
    
    return sample_sizes


def extract_sample_sizes_from_prose(doc: dict) -> Dict[str, Any]:
    """
    Extract sample sizes from prose text when not available in tables.
    Uses LLM to identify sample size information.
    """
    prose = doc.get('content', '')[:15000]
    
    prompt = f"""Extract sample sizes from this research paper text.

TEXT:
{prose}

Find and return:
1. N_treatment - number of individuals/units in treatment group
2. N_control - number of individuals/units in control group  
3. N_total - total sample size
4. N_clusters - number of clusters (schools, villages, etc.) if cluster-randomized

Return in this format exactly:
n_treatment: NUMBER or UNKNOWN
n_control: NUMBER or UNKNOWN
n_total: NUMBER or UNKNOWN
n_clusters: NUMBER or UNKNOWN

Only return numbers you're confident about. Say UNKNOWN if not found or unclear."""

    result = call_llm(prompt, max_tokens=200)
    
    extracted = {
        'n_treatment': None,
        'n_control': None,
        'n_total': None,
        'n_clusters': None
    }
    
    for line in result.split('\n'):
        line_lower = line.lower().strip()
        if ':' in line_lower:
            key, value = line_lower.split(':', 1)
            value = value.strip()
            if value != 'unknown':
                nums = re.findall(r'\d+', value.replace(',', ''))
                if nums:
                    if 'treatment' in key or 'n_t' in key:
                        extracted['n_treatment'] = int(nums[0])
                    elif 'control' in key or 'n_c' in key:
                        extracted['n_control'] = int(nums[0])
                    elif 'total' in key:
                        extracted['n_total'] = int(nums[0])
                    elif 'cluster' in key:
                        extracted['n_clusters'] = int(nums[0])
    
    return extracted


def extract_effects_from_prose(doc: dict, study_id: str) -> List[Dict[str, Any]]:
    """
    Extract treatment effects mentioned in prose text.
    
    Used when:
    1. No tables are available (MineRU failure, figures-only papers)
    2. Tables extracted but want to validate/enrich
    3. Key outcomes mentioned only in abstract/conclusion
    
    Extracts patterns like:
    - "increased by X% (SE=Y, p<Z)"
    - "coefficient of X (Y standard errors)"
    - "significant effect of X percentage points"
    - "reduced by X units (95% CI: [A, B])"
    
    Returns:
    - List of effect dictionaries with standardized fields
    """
    content = doc.get('content', '')
    
    # Focus on results-rich sections
    # Try to find Results, Discussion, Abstract sections
    sections_to_search = []
    
    # Look for section markers
    results_pattern = r'(?:^|\n)(?:#+\s*)?(?:results?|findings?|impacts?|effects?)[\s:]*\n(.*?)(?=\n(?:#+\s*)?(?:discussion|conclusion|reference|appendix)|$)'
    abstract_pattern = r'(?:^|\n)(?:#+\s*)?abstract[\s:]*\n(.*?)(?=\n(?:#+\s*)?(?:introduction|background|keywords)|$)'
    conclusion_pattern = r'(?:^|\n)(?:#+\s*)?(?:conclusion|discussion)[\s:]*\n(.*?)(?=\n(?:#+\s*)?(?:reference|appendix|acknowledgment)|$)'
    
    for pattern, section_name in [(abstract_pattern, 'abstract'), 
                                   (results_pattern, 'results'),
                                   (conclusion_pattern, 'conclusion')]:
        match = re.search(pattern, content, re.IGNORECASE | re.DOTALL)
        if match:
            sections_to_search.append((section_name, match.group(1)[:10000]))
    
    # If no sections found, use first 20k chars
    if not sections_to_search:
        sections_to_search.append(('full_text', content[:20000]))
    
    # Combine sections for LLM
    combined_text = "\n\n".join([f"[{name.upper()}]\n{text[:5000]}" for name, text in sections_to_search])
    
    prompt = f"""Extract ALL treatment effect estimates from this research paper text.

TEXT:
{combined_text[:12000]}

For each effect mentioned, extract:
1. outcome_name: What was measured (e.g., "income", "test scores", "employment rate")
2. treatment_arm: Which treatment group (e.g., "treatment", "cash transfer", "training program") 
3. coefficient: The point estimate (number)
4. standard_error: SE if mentioned (number)
5. p_value: P-value if mentioned (number like 0.05)
6. significance: Stars or significance level (*, **, ***, or "significant at X%")
7. ci_lower: Lower confidence interval bound if mentioned
8. ci_upper: Upper confidence interval bound if mentioned
9. effect_type: "percentage_points", "percent_change", "absolute_units", "standard_deviations"
10. source_sentence: The exact sentence containing this effect

Return as JSON array. Example:
[
  {{
    "outcome_name": "monthly income",
    "treatment_arm": "cash transfer",
    "coefficient": 150.5,
    "standard_error": 45.2,
    "p_value": 0.001,
    "significance": "***",
    "ci_lower": 61.9,
    "ci_upper": 239.1,
    "effect_type": "absolute_units",
    "source_sentence": "Cash transfers increased monthly income by $150.50 (SE=45.2, p<0.001)"
  }}
]

Only include effects with numeric coefficients. Return empty array [] if no effects found.
Return ONLY the JSON array, no other text."""

    result = call_llm(prompt, max_tokens=2000)
    
    # Parse LLM response
    effects = []
    try:
        # Clean up response - find JSON array
        json_match = re.search(r'\[.*\]', result, re.DOTALL)
        if json_match:
            parsed = json.loads(json_match.group())
            if isinstance(parsed, list):
                for effect in parsed:
                    # Get coefficient directly (LLM returns numeric or None)
                    coef = effect.get('coefficient')
                    if coef is not None:
                        try:
                            coef = float(coef)
                        except (ValueError, TypeError):
                            coef = None
                    
                    # Get SE directly
                    se = effect.get('standard_error')
                    if se is not None:
                        try:
                            se = float(se)
                        except (ValueError, TypeError):
                            se = None
                    
                    # Standardize to our schema
                    row = {
                        'study_id': study_id,
                        'table_number': None,
                        'table_caption': 'Extracted from prose',
                        'page_number': None,
                        'section': effect.get('source_sentence', '')[:100],
                        'treatment_arm': effect.get('treatment_arm', 'treatment'),
                        'outcome_name': effect.get('outcome_name', ''),
                        'coefficient': coef,
                        'standard_error': se,
                        'significance': effect.get('significance'),
                        'p_value': effect.get('p_value'),
                        'p_value_text': f"p={effect.get('p_value')}" if effect.get('p_value') else None,
                        'ci_lower': effect.get('ci_lower'),
                        'ci_upper': effect.get('ci_upper'),
                        't_statistic': None,
                        'sample_size': None,
                        'n_treatment': None,
                        'n_control': None,
                        'n_clusters': None,
                        'control_mean': None,
                        'control_sd': None,
                        'literal_cell_text': effect.get('source_sentence', ''),
                        'extraction_source': 'prose'  # Mark as prose-extracted
                    }
                    # Only include if we have a coefficient
                    if row['coefficient'] is not None:
                        effects.append(row)
    except (json.JSONDecodeError, TypeError) as e:
        print(f"  [WARN] Failed to parse prose effects: {e}")
    
    return effects


def extract_effects_from_figures(doc: dict, study_id: str) -> List[Dict[str, Any]]:
    """
    Extract treatment effects from figure captions and surrounding text.
    
    Used when:
    1. Paper has results in figures/charts instead of tables
    2. Learning briefs, policy briefs with graphical results
    3. Papers where MineRU extracted figures but no tables
    
    Approach:
    1. Find all figure references and captions in the markdown
    2. Extract surrounding context (text before/after each figure)
    3. Use LLM to extract any quantitative effects mentioned
    
    Returns:
    - List of effect dictionaries with standardized fields
    """
    content = doc.get('content', '')
    
    # Find figure references: ![](image_path) or ![alt](image_path)
    # And their surrounding context
    figure_contexts = []
    
    # Pattern for markdown images with figure captions
    # Captures: image reference + following caption + notes
    fig_pattern = r'!\[[^\]]*\]\([^)]+\)\s*\n?(Figure\s*\d*[a-z]?[:\.]?\s*[^\n]+(?:\n(?![#\n]|\!\[)[^\n]+)*)'
    
    matches = list(re.finditer(fig_pattern, content, re.IGNORECASE))
    
    if not matches:
        # Try alternative: just find "Figure X:" patterns
        fig_pattern2 = r'(Figure\s*\d+[a-z]?[:\.]?\s*[^\n]+(?:\n(?![#\n]|\!\[)[^\n]+){0,10})'
        matches = list(re.finditer(fig_pattern2, content, re.IGNORECASE))
    
    for match in matches:
        # Get context: 500 chars before and after
        start = max(0, match.start() - 500)
        end = min(len(content), match.end() + 500)
        context = content[start:end]
        figure_contexts.append(context)
    
    if not figure_contexts:
        return []
    
    # Combine figure contexts
    combined_figures = "\n\n---FIGURE---\n\n".join(figure_contexts[:10])  # Limit to 10 figures
    
    prompt = f"""Extract treatment effect estimates from these figure descriptions and captions.

These are figures from an impact evaluation paper. The figures show treatment effects graphically.
Extract any quantitative information about effects that is mentioned in the captions, notes, or surrounding text.

FIGURE CONTEXTS:
{combined_figures[:10000]}

For each effect mentioned, extract:
1. outcome_name: What outcome was measured
2. treatment_arm: Which treatment (e.g., "poultry package", "cash transfer")
3. coefficient: The point estimate if given as a number
4. standard_error: SE if mentioned
5. p_value: P-value if mentioned (e.g., 0.05, 0.01)
6. significance: Significance level (*, **, ***, "significant", "not significant")
7. ci_lower: Lower CI bound if mentioned
8. ci_upper: Upper CI bound if mentioned  
9. effect_direction: "positive", "negative", "null" (based on description if no number)
10. effect_description: Brief description of the effect (e.g., "18 percentage point increase")
11. figure_reference: Which figure this is from (e.g., "Figure 2")

Return as JSON array. Include effects even if only qualitative (e.g., "significant positive effect").
For qualitative effects without numbers, set coefficient to null but include effect_direction and effect_description.

Example:
[
  {{
    "outcome_name": "poultry ownership",
    "treatment_arm": "poultry package",
    "coefficient": 0.40,
    "standard_error": null,
    "p_value": 0.01,
    "significance": "***",
    "ci_lower": null,
    "ci_upper": null,
    "effect_direction": "positive",
    "effect_description": "40 percentage point increase in poultry ownership",
    "figure_reference": "Figure 2"
  }},
  {{
    "outcome_name": "wage employment",
    "treatment_arm": "cash transfer", 
    "coefficient": null,
    "standard_error": null,
    "p_value": null,
    "significance": "not significant",
    "ci_lower": null,
    "ci_upper": null,
    "effect_direction": "null",
    "effect_description": "no significant effect on wage employment",
    "figure_reference": "Figure 4"
  }}
]

Return ONLY the JSON array."""

    result = call_llm(prompt, max_tokens=2500)
    
    # Parse LLM response
    effects = []
    try:
        json_match = re.search(r'\[.*\]', result, re.DOTALL)
        if json_match:
            parsed = json.loads(json_match.group())
            if isinstance(parsed, list):
                for effect in parsed:
                    # Get coefficient directly (LLM returns numeric or None)
                    coef = effect.get('coefficient')
                    if coef is not None:
                        try:
                            coef = float(coef)
                        except (ValueError, TypeError):
                            coef = None
                    
                    # Get SE directly
                    se = effect.get('standard_error')
                    if se is not None:
                        try:
                            se = float(se)
                        except (ValueError, TypeError):
                            se = None
                    
                    row = {
                        'study_id': study_id,
                        'table_number': None,
                        'table_caption': f"From {effect.get('figure_reference', 'figure')}",
                        'page_number': None,
                        'section': effect.get('effect_description', '')[:100],
                        'treatment_arm': effect.get('treatment_arm', 'treatment'),
                        'outcome_name': effect.get('outcome_name', ''),
                        'coefficient': coef,
                        'standard_error': se,
                        'significance': effect.get('significance'),
                        'p_value': effect.get('p_value'),
                        'p_value_text': f"p={effect.get('p_value')}" if effect.get('p_value') else None,
                        'ci_lower': effect.get('ci_lower'),
                        'ci_upper': effect.get('ci_upper'),
                        't_statistic': None,
                        'sample_size': None,
                        'n_treatment': None,
                        'n_control': None,
                        'n_clusters': None,
                        'control_mean': None,
                        'control_sd': None,
                        'literal_cell_text': effect.get('effect_description', ''),
                        'extraction_source': 'figure',  # Mark as figure-extracted
                        'effect_direction': effect.get('effect_direction')
                    }
                    # Include even qualitative effects (coefficient can be null)
                    if row['outcome_name']:
                        effects.append(row)
    except (json.JSONDecodeError, TypeError) as e:
        print(f"  [WARN] Failed to parse figure effects: {e}")
    
    return effects



# ============================================================================
# STAGE 4: CONTEXT ENRICHMENT (LLM)
# ============================================================================

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

    result = call_llm(prompt, max_tokens=1000)
    
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

# ============================================================================
# MAIN PIPELINE
# ============================================================================

def extract_all_tables(doc: dict, study_id: str, use_llm: bool = True) -> pd.DataFrame:
    """
    Extract data from all results tables in the document.
    
    Uses two-pass classification when LLM is enabled:
    1. First pass: Build inventory of all tables with captions
    2. Second pass: LLM classifies ALL tables at once (context-aware)
    3. Third pass: Extract only from tables classified as "results"
    """
    tables = doc.get('tables', [])
    all_results = []
    
    print(f"\n  Found {len(tables)} tables in document")
    
    if not tables:
        return pd.DataFrame()
    
    # ========== PASS 1: Build table inventory ==========
    table_inventory = []
    for i, table in enumerate(tables):
        caption_raw = ' '.join(table.get('table_caption', []))
        caption = fix_ocr_spacing(caption_raw)
        html = table.get('table_body', '')
        
        # Get a preview of table content (first 200 chars, cleaned)
        soup = BeautifulSoup(html, 'html.parser')
        preview = soup.get_text(separator=' ', strip=True)[:200]
        
        table_id = f"Table{i+1}"
        table_inventory.append({
            'table_id': table_id,
            'index': i,
            'caption': caption,
            'preview': preview,
            'html': html
        })
    
    # ========== PASS 2: Classify all tables at once ==========
    if use_llm and len(table_inventory) > 0:
        print(f"\n  [SMART CLASSIFICATION] Analyzing {len(table_inventory)} tables...")
        table_classifications = classify_all_tables_llm(table_inventory)
        
        # Show classification summary
        results_tables = [t for t, c in table_classifications.items() if c == 'results']
        descriptive_tables = [t for t, c in table_classifications.items() if c == 'descriptive']
        print(f"    → Results tables: {len(results_tables)} ({', '.join(results_tables[:5])}{'...' if len(results_tables) > 5 else ''})")
        print(f"    → Descriptive tables: {len(descriptive_tables)} (skipped)")
    else:
        # Fallback: use rules-based classification
        table_classifications = {}
        for inv in table_inventory:
            table_classifications[inv['table_id']] = classify_table(inv['caption'], inv['html'], use_llm=False)
    
    # ========== PASS 3: Extract from results tables ==========
    tables_extracted = 0
    tables_skipped = 0
    tables_transposed = 0
    
    for inv in table_inventory:
        i = inv['index']
        table = tables[i]
        caption = inv['caption']
        html = inv['html']
        table_id = inv['table_id']
        
        # Use pre-computed classification
        table_type = table_classifications.get(table_id, 'results')
        
        if table_type == 'results':
            # Detect table orientation
            soup = BeautifulSoup(html, 'html.parser')
            rows = soup.find_all('tr')
            orientation = detect_table_orientation(rows)
            
            if orientation == 'rows':
                # Use transposed table parser (outcomes in rows, stats in columns)
                results = extract_transposed_table(table, study_id)
                if results:
                    all_results.extend(results)
                    print(f"    Table {i}: {caption[:50]}... → {len(results)} rows (transposed)")
                    tables_extracted += 1
                    tables_transposed += 1
                else:
                    # Fall back to standard parser
                    results = extract_results_table(table, study_id)
                    if results:
                        all_results.extend(results)
                        print(f"    Table {i}: {caption[:50]}... → {len(results)} rows")
                        tables_extracted += 1
            elif orientation == 'treatments_in_cols':
                # Use treatment-columns parser (outcomes in rows, treatment groups in columns)
                results = extract_treatments_in_cols_table(table, study_id)
                if results:
                    all_results.extend(results)
                    print(f"    Table {i}: {caption[:50]}... → {len(results)} rows (treatments-in-cols)")
                    tables_extracted += 1
                    tables_transposed += 1
                else:
                    # Fall back to standard parser
                    results = extract_results_table(table, study_id)
                    if results:
                        all_results.extend(results)
                        print(f"    Table {i}: {caption[:50]}... → {len(results)} rows")
                        tables_extracted += 1
            elif orientation == 'outcomes_in_rows_se_split':
                # Use SE-split parser (outcomes in rows, SE in separate rows, European numbers)
                results = extract_outcomes_in_rows_se_split(table, study_id)
                if results:
                    all_results.extend(results)
                    print(f"    Table {i}: {caption[:50]}... → {len(results)} rows (SE-split)")
                    tables_extracted += 1
                    tables_transposed += 1
                else:
                    # Fall back to standard parser
                    results = extract_results_table(table, study_id)
                    if results:
                        all_results.extend(results)
                        print(f"    Table {i}: {caption[:50]}... → {len(results)} rows")
                        tables_extracted += 1
            elif orientation == 'comparison_format':
                # Use comparison format parser (outcomes in rows, impact estimates like [A-B] in columns)
                results = extract_comparison_format_table(table, study_id)
                if results:
                    all_results.extend(results)
                    print(f"    Table {i}: {caption[:50]}... → {len(results)} rows (comparison)")
                    tables_extracted += 1
                    tables_transposed += 1
                else:
                    # Fall back to standard parser
                    results = extract_results_table(table, study_id)
                    if results:
                        all_results.extend(results)
                        print(f"    Table {i}: {caption[:50]}... → {len(results)} rows")
                        tables_extracted += 1
            else:
                # Standard outcomes-in-columns parser
                results = extract_results_table(table, study_id)
                if results:
                    all_results.extend(results)
                    print(f"    Table {i}: {caption[:50]}... → {len(results)} rows")
                    tables_extracted += 1
        else:
            tables_skipped += 1
    
    transposed_note = f", {tables_transposed} transposed" if tables_transposed else ""
    print(f"\n  Tables: {tables_extracted} extracted{transposed_note}, {tables_skipped} skipped")
    
    df = pd.DataFrame(all_results)
    
    # P1: Filter suspicious treatment arms and outcome names
    if not df.empty:
        initial_count = len(df)
        
        # Suspicious patterns that indicate metadata rows, not treatment effects
        suspicious_patterns = [
            r'^test\s*:',           # "Test: T1 = T2"
            r'^mean\s+of',          # "Mean of dependent variable"  
            r'^\d+$',               # Pure numbers like "200"
            r'^n\s*=',              # "N = 1234"
            r'^r[\s-]*squared',     # "R-squared"
            r'^observation',        # "Observations"
            r'^control\s+(mean|sd|n)', # Control statistics
            r'^p[\s-]*value',       # "P-value"
            r'^standard\s+error',   # Standard error row
            r'^\*+$',               # Just stars
            r'^note',               # Notes
            r'^source',             # Source
        ]
        
        def is_suspicious(row):
            """Check if row looks like metadata, not a treatment effect."""
            arm = str(row.get('treatment_arm', '')).lower().strip()
            outcome = str(row.get('outcome_name', '')).lower().strip()
            
            for pattern in suspicious_patterns:
                if re.search(pattern, arm, re.IGNORECASE):
                    return True
                if re.search(pattern, outcome, re.IGNORECASE):
                    return True
            
            # Also filter rows where outcome_name is very short or numeric
            if len(outcome) < 3 or outcome.replace('.', '').isdigit():
                return True
                
            return False
        
        # Apply filter
        df['_suspicious'] = df.apply(is_suspicious, axis=1)
        filtered_count = df['_suspicious'].sum()
        df = df[~df['_suspicious']].drop(columns=['_suspicious'])
        
        if filtered_count > 0:
            print(f"  Filtered {filtered_count} suspicious rows (P1 validation)")
    
    return df


def run_pipeline(study_id: str, use_llm: bool = True, enrich: bool = True) -> tuple:
    """Run the full extraction pipeline for a single study."""
    
    print("=" * 70)
    print(f"PIPELINE V2 SOTA: Extracting study {study_id}")
    print("=" * 70)
    
    # Create output directory
    study_output_dir = f"{OUTPUT_DIR}/{study_id}"
    os.makedirs(study_output_dir, exist_ok=True)
    
    # Stage 0: Load data
    print("\n[STAGE 0] Loading MineRU JSON from R2...")
    doc = load_mineru_json(study_id)
    if not doc:
        return None, pd.DataFrame()
    print(f"  ✓ Loaded: {len(doc.get('tables', []))} tables, {len(doc.get('content', ''))} chars")
    
    # Stage 1: Metadata (with LLM enrichment for author, country, etc.)
    print("\n[STAGE 1] Extracting metadata...")
    if use_llm:
        metadata = extract_metadata_llm(doc, study_id)
        print(f"  ✓ Title: {metadata['title'][:60]}...")
        print(f"  ✓ Authors: {metadata.get('authors', 'N/A')[:50]}...")
        print(f"  ✓ Year: {metadata['year']}")
        print(f"  ✓ Country: {metadata.get('country', 'N/A')}")
        print(f"  ✓ Study Design: {metadata.get('study_design', 'N/A')}")
        print(f"  ✓ Follow-up: {metadata.get('follow_up_months', 'N/A')} months")
    else:
        metadata = extract_metadata(doc, study_id)
        print(f"  ✓ Title: {metadata['title'][:60]}...")
        print(f"  ✓ Year: {metadata['year']}")
    
    with open(f"{study_output_dir}/metadata.json", 'w') as f:
        json.dump(metadata, f, indent=2)
    
    # Stage 2 & 3: Table extraction with classification
    print("\n[STAGE 2] Extracting tables (BeautifulSoup + LLM classification)...")
    df = extract_all_tables(doc, study_id, use_llm=use_llm)
    
    # STAGE 2b: Prose extraction fallback when tables yield nothing
    if df.empty and use_llm:
        print("\n[STAGE 2b] No table data - attempting prose extraction...")
        prose_effects = extract_effects_from_prose(doc, study_id)
        if prose_effects:
            df = pd.DataFrame(prose_effects)
            print(f"  ✓ Extracted {len(df)} effects from prose text")
        else:
            print("  ✗ No effects found in prose either")
    
    # STAGE 2c: Figure extraction fallback when prose also yields nothing
    if df.empty and use_llm:
        print("\n[STAGE 2c] No prose data - attempting figure caption extraction...")
        figure_effects = extract_effects_from_figures(doc, study_id)
        if figure_effects:
            df = pd.DataFrame(figure_effects)
            print(f"  ✓ Extracted {len(df)} effects from figure captions")
        else:
            print("  ✗ No effects found in figures either")
    
    if not df.empty:
        # Add study-level metadata to each row
        df['authors'] = metadata.get('authors', '')
        df['year'] = metadata.get('year')
        df['country'] = metadata.get('country')
        df['study_design'] = metadata.get('study_design')
        df['is_experimental'] = metadata.get('is_experimental')
        df['follow_up_months'] = metadata.get('follow_up_months')
        df['intervention_name'] = metadata.get('intervention_name')
        
        print(f"\n  ✓ Total rows: {len(df)}")
        print(f"  ✓ Unique outcomes: {df['outcome_name'].nunique()}")
        print(f"  ✓ Tables with data: {df['table_number'].nunique()}")
        print(f"  ✓ Coefficient coverage: {100*df['coefficient'].notna().mean():.1f}%")
        print(f"  ✓ SE coverage: {100*df['standard_error'].notna().mean():.1f}%")
        if 'ci_lower' in df.columns:
            print(f"  ✓ CI coverage: {100*df['ci_lower'].notna().mean():.1f}%")
        
        # Fallback: extract sample sizes from prose if missing from tables
        if use_llm and df['n_treatment'].isna().all():
            print("\n[STAGE 3b] Extracting sample sizes from prose...")
            prose_samples = extract_sample_sizes_from_prose(doc)
            if prose_samples.get('n_treatment'):
                df['n_treatment'] = df['n_treatment'].fillna(prose_samples['n_treatment'])
                print(f"  ✓ N treatment from prose: {prose_samples['n_treatment']}")
            if prose_samples.get('n_control'):
                df['n_control'] = df['n_control'].fillna(prose_samples['n_control'])
                print(f"  ✓ N control from prose: {prose_samples['n_control']}")
            if prose_samples.get('n_clusters'):
                df['n_clusters'] = df['n_clusters'].fillna(prose_samples['n_clusters'])
                print(f"  ✓ N clusters from prose: {prose_samples['n_clusters']}")
    
    # Stage 4: Context enrichment (optional)
    if enrich and not df.empty:
        print("\n[STAGE 4] Enriching with LLM context...")
        df = enrich_with_context(df, doc)
        
        # Classify outcomes into categories
        print("\n[STAGE 5] Classifying outcomes...")
        df = classify_outcomes(df, domain='graduation')
        cat_coverage = df['outcome_category'].notna().mean() * 100
        print(f"  ✓ Outcome category coverage: {cat_coverage:.1f}%")
    
    # Stage 6: Calculate effect sizes
    if not df.empty:
        print("\n[STAGE 6] Calculating effect sizes...")
        df = calculate_effect_sizes(df)
        d_coverage = df['cohens_d'].notna().mean() * 100
        g_coverage = df['hedges_g'].notna().mean() * 100
        print(f"  ✓ Cohen's d coverage: {d_coverage:.1f}%")
        print(f"  ✓ Hedges' g coverage: {g_coverage:.1f}%")
    
    # Stage 7: Classify analysis types (subgroups, spillovers, etc.)
    if enrich and not df.empty:
        print("\n[STAGE 7] Classifying analysis types (reasoning LLM)...")
        df = classify_analysis_type(df)
        main_pct = df['is_main_effect'].sum() / len(df) * 100
        subgroup_pct = df['is_subgroup'].sum() / len(df) * 100
        spillover_pct = df['is_spillover'].sum() / len(df) * 100
        print(f"  ✓ Main effects: {main_pct:.1f}% of rows")
        print(f"  ✓ Subgroup analyses: {subgroup_pct:.1f}% of rows")
        if subgroup_pct > 0:
            subgroups = df[df['is_subgroup']]['subgroup_variable'].dropna().unique()
            print(f"    Subgroup variables: {', '.join(str(s) for s in subgroups[:5])}")
        print(f"  ✓ Spillover effects: {spillover_pct:.1f}% of rows")
        if spillover_pct > 0:
            spill_types = df[df['is_spillover']]['spillover_type'].dropna().unique()
            print(f"    Spillover types: {', '.join(str(s) for s in spill_types)}")
    
    # Save results
    if not df.empty:
        df.to_csv(f"{study_output_dir}/extracted_data.csv", index=False)
        df.to_json(f"{study_output_dir}/extracted_data.json", orient='records', indent=2)
        print(f"\n  ✓ Saved to {study_output_dir}/")
    
    # Summary
    print("\n" + "=" * 70)
    print("EXTRACTION COMPLETE")
    print("=" * 70)
    
    # Print field coverage summary
    if not df.empty:
        print("\nFIELD COVERAGE:")
        key_fields = ['coefficient', 'standard_error', 'p_value', 'ci_lower', 'ci_upper',
                      'sample_size', 'n_treatment', 'n_control', 'n_clusters',
                      'control_mean', 'control_sd', 't_statistic',
                      'cohens_d', 'hedges_g', 'effect_variance', 'effect_se',
                      'outcome_category', 'authors', 'year', 'country', 'study_design',
                      'follow_up_months', 'is_experimental']
        for field in key_fields:
            if field in df.columns:
                cov = df[field].notna().mean() * 100
                print(f"  {field:20}: {cov:5.1f}%")
        
        # Analysis type summary
        print("\nANALYSIS TYPE CLASSIFICATION:")
        if 'is_main_effect' in df.columns:
            print(f"  Main effects:      {df['is_main_effect'].sum():4} rows ({100*df['is_main_effect'].mean():.1f}%)")
            print(f"  Subgroup analyses: {df['is_subgroup'].sum():4} rows ({100*df['is_subgroup'].mean():.1f}%)")
            print(f"  Spillover effects: {df['is_spillover'].sum():4} rows ({100*df['is_spillover'].mean():.1f}%)")
            print(f"  Cost outcomes:     {df['is_cost_outcome'].sum():4} rows ({100*df['is_cost_outcome'].mean():.1f}%)")
            print(f"  Mechanism/mediator:{df['is_mechanism'].sum():4} rows ({100*df['is_mechanism'].mean():.1f}%)")
    
    return metadata, df


def main():
    parser = argparse.ArgumentParser(description='Extract impact evaluation data from papers')
    parser.add_argument('--study_id', type=str, default=DEFAULT_STUDY_ID, help='Study ID to extract')
    parser.add_argument('--no-llm', action='store_true', help='Disable LLM classification')
    parser.add_argument('--no-enrich', action='store_true', help='Disable LLM enrichment')
    
    args = parser.parse_args()
    
    metadata, df = run_pipeline(
        study_id=args.study_id,
        use_llm=not args.no_llm,
        enrich=not args.no_enrich
    )
    
    if not df.empty:
        print(f"\nSample output:")
        print(df[['table_number', 'treatment_arm', 'outcome_name', 'coefficient', 'standard_error']].head(10).to_string())


if __name__ == "__main__":
    main()
