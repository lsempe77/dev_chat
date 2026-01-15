"""
Extraction V3 - Comprehensive extraction with evidence quotes and thorough reporting

Following EXTRACTION_VALIDATION_FRAMEWORK.md:
- STAGE 1: Primary extraction with {value, confidence, evidence_quote}
- STAGE 2: Self-verification (provenance check)
- STAGE 3: Schema validation
- STAGE 4: Cross-source validation (DOI/metadata)
- STAGE 5: Uncertainty flagging

Extracts:
- Tier 1: study_design, country, year, author
- Tier 2: 7 intervention components (binary) with evidence quotes
- Tier 3: Outcomes with raw statistics for Cohen's d calculation
- Tier 4: program_name, targeting_women
"""

import os
import re
import json
import boto3
import asyncio
import numpy as np
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict, field
from datetime import datetime
from dotenv import load_dotenv
import httpx
import pandas as pd

load_dotenv()

OPENROUTER_API_KEY = os.environ.get('OPENROUTER_API_KEY')
MODEL = "anthropic/claude-3.5-sonnet"

# ============================================================================
# DATA CLASSES - Following framework schema
# ============================================================================

@dataclass
class ExtractedVariable:
    """Each extracted variable has value, confidence, and evidence."""
    value: Any
    confidence: float  # 0-1
    evidence_quote: Optional[str] = None
    needs_review: bool = False


@dataclass
class OutcomeRaw:
    """Raw outcome data for Cohen's d computation."""
    outcome_name: str
    outcome_category: str  # Income, Assets, Savings, Expenditure, Poverty
    coefficient: Optional[float] = None
    standard_error: Optional[float] = None
    t_statistic: Optional[float] = None
    n_treatment: Optional[int] = None
    n_control: Optional[int] = None
    n_total: Optional[int] = None
    mean_treatment: Optional[float] = None
    mean_control: Optional[float] = None
    sd_treatment: Optional[float] = None
    sd_control: Optional[float] = None
    evidence_table: Optional[str] = None
    confidence: float = 0.5
    # Computed fields
    computed_d: Optional[float] = None
    computation_method: Optional[str] = None


@dataclass
class StudyExtractionV3:
    """Complete extraction for one study."""
    study_id: str
    
    # Tier 1: Basic metadata
    study_design: ExtractedVariable = None
    country: ExtractedVariable = None
    year: ExtractedVariable = None
    author: ExtractedVariable = None
    
    # Tier 2: Intervention components
    consumption_support: ExtractedVariable = None
    health_comp: ExtractedVariable = None
    asset_transfer: ExtractedVariable = None
    skills_comp: ExtractedVariable = None
    savings_comp: ExtractedVariable = None
    coaching_comp: ExtractedVariable = None
    social_comp: ExtractedVariable = None
    
    # Tier 3: Outcomes
    outcomes: List[OutcomeRaw] = field(default_factory=list)
    
    # Tier 4: Program metadata
    program_name: ExtractedVariable = None
    targeting_women: ExtractedVariable = None
    
    # Metadata
    extraction_timestamp: str = None
    extraction_version: str = "v3"
    raw_document_length: int = 0


# ============================================================================
# SCHEMA VALIDATION
# ============================================================================

VALID_STUDY_DESIGNS = {"RCT", "Quasi-Experimental", "Observational", "Unknown"}
VALID_OUTCOME_CATEGORIES = {"Income", "Assets", "Savings", "Expenditure", "Poverty"}

# Common country name variations
COUNTRY_VARIATIONS = {
    "burkina": "Burkina Faso",
    "burkina faso": "Burkina Faso",
    "phillipines": "Philippines",
    "philipines": "Philippines",
    "south sudan": "South Sudan",
    "bangladesh": "Bangladesh",
    "india": "India",
    "niger": "Niger",
    "ethiopia": "Ethiopia",
    "ghana": "Ghana",
    "yemen": "Yemen",
    "egypt": "Egypt",
    "uganda": "Uganda",
    "peru": "Peru",
    "honduras": "Honduras",
    "afghanistan": "Afghanistan",
    "pakistan": "Pakistan",
    "malawi": "Malawi",
    "zambia": "Zambia",
    "paraguay": "Paraguay",
    "nicaragua": "Nicaragua",
    "rwanda": "Rwanda",
    "burundi": "Burundi",
    "vietnam": "Vietnam",
    "somalia": "Somalia",
    "chad": "Chad",
}


def validate_study_design(value: str) -> Tuple[str, bool]:
    """Validate and normalize study design."""
    if not value:
        return "Unknown", False
    
    value_lower = value.lower()
    if "rct" in value_lower or "randomized" in value_lower:
        return "RCT", True
    elif "quasi" in value_lower:
        return "Quasi-Experimental", True
    elif "observational" in value_lower:
        return "Observational", True
    return value, False


def validate_country(value: str) -> Tuple[str, bool]:
    """Validate and normalize country name."""
    if not value:
        return "", False
    
    value_lower = value.lower().strip()
    if value_lower in COUNTRY_VARIATIONS:
        return COUNTRY_VARIATIONS[value_lower], True
    
    # Try to match partial
    for key, normalized in COUNTRY_VARIATIONS.items():
        if key in value_lower or value_lower in key:
            return normalized, True
    
    return value, False


def validate_sample_size(n: int) -> bool:
    """Check if sample size is plausible."""
    return n is not None and 1 <= n <= 1_000_000


def validate_effect_size(d: float) -> bool:
    """Check if Cohen's d is in reasonable range."""
    return d is not None and -5 <= d <= 5


def validate_year(year: int) -> bool:
    """Check if publication year is plausible."""
    return year is not None and 1990 <= year <= 2026


# ============================================================================
# COHEN'S D COMPUTATION - VERIFIED EXACT FORMULA
# ============================================================================

def compute_cohens_d(outcome: OutcomeRaw) -> Tuple[Optional[float], str]:
    """
    Compute Cohen's d from extracted values.
    Returns (d, method_used) or (None, "insufficient_data")
    
    VERIFIED EXACT (from ground truth reverse-engineering):
    d = t * sqrt(1/n1 + 1/n2) where t = coef/se
    """
    coef = outcome.coefficient
    se = outcome.standard_error
    n1 = outcome.n_treatment
    n2 = outcome.n_control
    n_total = outcome.n_total
    t = outcome.t_statistic
    
    # Method 1: From t-statistic directly (if available)
    if t is not None and n1 is not None and n2 is not None:
        d = t * np.sqrt(1/n1 + 1/n2)
        if validate_effect_size(d):
            return d, "t_stat_with_n"
    
    # Method 2: FORMULA 5 - coef/se with treatment/control sample sizes (VERIFIED EXACT)
    if all(x is not None for x in [coef, se, n1, n2]) and se != 0:
        t_calc = coef / se
        d = t_calc * np.sqrt(1/n1 + 1/n2)
        if validate_effect_size(d):
            return d, "formula_5_exact"
    
    # Method 3: FORMULA 6 - When only N_total available (assume 50/50 split)
    if all(x is not None for x in [coef, se, n_total]) and se != 0:
        n1_est = n_total / 2
        n2_est = n_total / 2
        t_calc = coef / se
        d = t_calc * np.sqrt(1/n1_est + 1/n2_est)
        if validate_effect_size(d):
            return d, "formula_6_approx"
    
    # Method 4: From means and SDs (classic formula)
    m1 = outcome.mean_treatment
    m2 = outcome.mean_control
    s1 = outcome.sd_treatment
    s2 = outcome.sd_control
    
    if all(x is not None for x in [m1, m2, s1, s2, n1, n2]) and s1 > 0 and s2 > 0:
        pooled_sd = np.sqrt(((n1-1)*s1**2 + (n2-1)*s2**2) / (n1+n2-2))
        if pooled_sd > 0:
            d = (m1 - m2) / pooled_sd
            if validate_effect_size(d):
                return d, "means_sds_pooled"
    
    return None, "insufficient_data"


# ============================================================================
# EXTRACTION PROMPTS - WITH EVIDENCE QUOTES
# ============================================================================

METADATA_EXTRACTION_PROMPT = """You are extracting structured data from an academic study.

## Task
Extract metadata and intervention components from this research paper. 
For EACH field, provide:
- value: The extracted value
- confidence: 0-1 how confident you are
- evidence_quote: Copy the EXACT text from the document supporting this extraction

## Document Content:
{content}

## Fields to Extract:

### Tier 1: Basic Metadata
1. study_design: One of [RCT, Quasi-Experimental, Observational]
2. country: Country/countries where study was conducted
3. year: Publication year
4. author: First author's last name

### Tier 2: Intervention Components (1=present, 0=absent)
Extract each with evidence quote:

5. consumption_support: Cash or in-kind support to stabilize food security
   Examples: cash transfers, food rations, consumption stipends
   
6. health_comp: Health services or health education component
   Examples: health training, clinic referrals, health checkups
   
7. asset_transfer: Livestock, tools, or seed capital for income-generation
   Examples: goats, chickens, agricultural tools, business capital
   
8. skills_comp: Skills or vocational training
   Examples: business training, technical skills, financial literacy
   
9. savings_comp: Savings group or savings account component
   Examples: village savings groups, savings accounts, mandatory savings
   
10. coaching_comp: Mentoring, coaching, or regular home visits
    Examples: weekly visits by case managers, life skills coaching
    
11. social_comp: Social integration, community activities, social support
    Examples: community sensitization, social network building, group meetings

### Tier 4: Program Metadata
12. program_name: Full name of the intervention program
13. targeting_women: 1 if specifically targets women, 0 otherwise

## Response Format (JSON):
{{
  "study_design": {{"value": "RCT", "confidence": 0.95, "evidence_quote": "We conducted a randomized controlled trial..."}},
  "country": {{"value": "Bangladesh", "confidence": 0.99, "evidence_quote": "The study was conducted in rural Bangladesh..."}},
  "year": {{"value": 2021, "confidence": 0.95, "evidence_quote": ""}},
  "author": {{"value": "Bandiera", "confidence": 0.99, "evidence_quote": ""}},
  "consumption_support": {{"value": 1, "confidence": 0.85, "evidence_quote": "Participants received monthly cash transfers of..."}},
  "health_comp": {{"value": 0, "confidence": 0.7, "evidence_quote": ""}},
  "asset_transfer": {{"value": 1, "confidence": 0.9, "evidence_quote": "Each household received two goats and..."}},
  "skills_comp": {{"value": 1, "confidence": 0.95, "evidence_quote": "Beneficiaries attended weekly business training sessions..."}},
  "savings_comp": {{"value": 1, "confidence": 0.8, "evidence_quote": "Participants were enrolled in village savings groups..."}},
  "coaching_comp": {{"value": 1, "confidence": 0.9, "evidence_quote": "Field officers conducted weekly home visits..."}},
  "social_comp": {{"value": 0, "confidence": 0.6, "evidence_quote": ""}},
  "program_name": {{"value": "Targeting the Ultra-Poor (TUP)", "confidence": 0.95, "evidence_quote": "The Targeting the Ultra-Poor (TUP) program..."}},
  "targeting_women": {{"value": 1, "confidence": 0.9, "evidence_quote": "The program specifically targeted women heads of household..."}}
}}

IMPORTANT: 
- Set confidence < 0.7 if unsure
- Leave evidence_quote empty ("") if you cannot find supporting text
- For binary fields, use 1 or 0 (not true/false)

Return ONLY the JSON."""


OUTCOMES_EXTRACTION_PROMPT = """You are extracting quantitative outcome data from an academic study.

## Task
Find ALL results tables and extract raw statistical values. DO NOT calculate Cohen's d - just extract the raw numbers.

## Document Content:
{content}

## For Each Outcome in Results Tables, Extract:
1. outcome_name: What is being measured (e.g., "Total household assets (USD)")
2. outcome_category: One of [Income, Assets, Savings, Expenditure, Poverty]
3. coefficient: Treatment effect coefficient (unstandardized)
4. standard_error: Standard error of the coefficient
5. t_statistic: t-stat if shown (often coefficient/SE)
6. n_treatment: Sample size in treatment group
7. n_control: Sample size in control group  
8. n_total: Total sample size (if treatment/control not split)
9. mean_treatment: Mean in treatment group (if available)
10. mean_control: Mean in control group (if available)
11. sd_treatment: Standard deviation in treatment (if available)
12. sd_control: Standard deviation in control (if available)
13. evidence_table: Name of the table where this was found
14. confidence: 0-1 how confident in this extraction

## Response Format (JSON):
{{
  "outcomes": [
    {{
      "outcome_name": "Total household assets value (USD)",
      "outcome_category": "Assets",
      "coefficient": 150.5,
      "standard_error": 45.2,
      "t_statistic": 3.33,
      "n_treatment": 1200,
      "n_control": 1150,
      "n_total": 2350,
      "mean_treatment": null,
      "mean_control": null,
      "sd_treatment": null,
      "sd_control": null,
      "evidence_table": "Table 3: Impact on Assets",
      "confidence": 0.85
    }}
  ],
  "sample_sizes": {{
    "n_treatment": 1200,
    "n_control": 1150,
    "n_total": 2350,
    "note": "Sample sizes from Table 1"
  }}
}}

IMPORTANT:
- Extract ALL outcomes from ALL results tables
- Use null for missing values, not 0
- Include sample sizes even if only total N is available
- Extract from the most relevant follow-up period (usually endline)

Return ONLY the JSON."""


# ============================================================================
# LLM CALLS
# ============================================================================

async def call_llm(prompt: str, max_tokens: int = 4096, retries: int = 3) -> Dict:
    """Call OpenRouter API with Claude 3.5 Sonnet."""
    for attempt in range(retries):
        try:
            async with httpx.AsyncClient(timeout=300.0) as client:  # 5 minute timeout
                response = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": MODEL,
                        "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": max_tokens,
                        "temperature": 0
                    }
                )
                response.raise_for_status()
                content = response.json()["choices"][0]["message"]["content"]
                
                # Parse JSON from response
                json_match = re.search(r'\{[\s\S]*\}', content)
                if json_match:
                    return json.loads(json_match.group())
                return {}
        except Exception as e:
            if attempt < retries - 1:
                print(f"    Retry {attempt + 1}/{retries} after error: {str(e)[:100]}")
                await asyncio.sleep(5 * (attempt + 1))  # Exponential backoff
            else:
                print(f"    Failed after {retries} attempts: {str(e)[:100]}")
                return {}


# ============================================================================
# MAIN EXTRACTION FUNCTION
# ============================================================================

async def extract_study_v3(study_id: str, content: str) -> StudyExtractionV3:
    """
    Complete V3 extraction for one study.
    
    Implements:
    - Stage 1: Primary extraction with evidence quotes
    - Stage 2: Built into prompts (evidence_quote requirement)
    - Stage 3: Schema validation
    - Stage 5: Uncertainty flagging (confidence < 0.7)
    """
    extraction = StudyExtractionV3(
        study_id=study_id,
        extraction_timestamp=datetime.now().isoformat(),
        raw_document_length=len(content)
    )
    
    # NO TRUNCATION - use full paper to capture results tables at end
    # max_content_len = 80000
    # if len(content) > max_content_len:
    #     content = content[:max_content_len] + "\n\n[CONTENT TRUNCATED]"
    
    # --- STAGE 1: Metadata Extraction ---
    print(f"  [1/2] Extracting metadata for {study_id}...")
    metadata_prompt = METADATA_EXTRACTION_PROMPT.format(content=content)
    metadata = await call_llm(metadata_prompt)
    
    # Parse metadata fields with validation
    def parse_field(data: Dict, field_name: str) -> ExtractedVariable:
        field_data = data.get(field_name, {})
        if isinstance(field_data, dict):
            value = field_data.get('value')
            confidence = field_data.get('confidence', 0.5)
            evidence = field_data.get('evidence_quote', '')
        else:
            value = field_data
            confidence = 0.5
            evidence = ''
        
        needs_review = confidence < 0.7 or evidence == ''
        return ExtractedVariable(
            value=value,
            confidence=confidence,
            evidence_quote=evidence,
            needs_review=needs_review
        )
    
    # Tier 1: Basic metadata with validation
    extraction.study_design = parse_field(metadata, 'study_design')
    if extraction.study_design.value:
        normalized, valid = validate_study_design(extraction.study_design.value)
        extraction.study_design.value = normalized
        if not valid:
            extraction.study_design.needs_review = True
    
    extraction.country = parse_field(metadata, 'country')
    if extraction.country.value:
        normalized, valid = validate_country(extraction.country.value)
        extraction.country.value = normalized
    
    extraction.year = parse_field(metadata, 'year')
    if extraction.year.value:
        if not validate_year(extraction.year.value):
            extraction.year.needs_review = True
    
    extraction.author = parse_field(metadata, 'author')
    
    # Tier 2: Intervention components
    extraction.consumption_support = parse_field(metadata, 'consumption_support')
    extraction.health_comp = parse_field(metadata, 'health_comp')
    extraction.asset_transfer = parse_field(metadata, 'asset_transfer')
    extraction.skills_comp = parse_field(metadata, 'skills_comp')
    extraction.savings_comp = parse_field(metadata, 'savings_comp')
    extraction.coaching_comp = parse_field(metadata, 'coaching_comp')
    extraction.social_comp = parse_field(metadata, 'social_comp')
    
    # Tier 4: Program metadata
    extraction.program_name = parse_field(metadata, 'program_name')
    extraction.targeting_women = parse_field(metadata, 'targeting_women')
    
    # --- STAGE 1b: Outcomes Extraction ---
    print(f"  [2/2] Extracting outcomes for {study_id}...")
    outcomes_prompt = OUTCOMES_EXTRACTION_PROMPT.format(content=content)
    outcomes_data = await call_llm(outcomes_prompt)
    
    # Get study-level sample sizes for fallback
    sample_sizes = outcomes_data.get('sample_sizes', {})
    study_n_treatment = sample_sizes.get('n_treatment')
    study_n_control = sample_sizes.get('n_control')
    study_n_total = sample_sizes.get('n_total')
    
    # Parse outcomes and compute Cohen's d
    raw_outcomes = outcomes_data.get('outcomes', [])
    for o in raw_outcomes:
        outcome = OutcomeRaw(
            outcome_name=o.get('outcome_name', ''),
            outcome_category=o.get('outcome_category', 'Unknown'),
            coefficient=o.get('coefficient'),
            standard_error=o.get('standard_error'),
            t_statistic=o.get('t_statistic'),
            n_treatment=o.get('n_treatment') or study_n_treatment,
            n_control=o.get('n_control') or study_n_control,
            n_total=o.get('n_total') or study_n_total,
            mean_treatment=o.get('mean_treatment'),
            mean_control=o.get('mean_control'),
            sd_treatment=o.get('sd_treatment'),
            sd_control=o.get('sd_control'),
            evidence_table=o.get('evidence_table'),
            confidence=o.get('confidence', 0.5)
        )
        
        # Validate outcome category
        if outcome.outcome_category not in VALID_OUTCOME_CATEGORIES:
            # Try to fix common issues
            cat_lower = outcome.outcome_category.lower()
            for valid_cat in VALID_OUTCOME_CATEGORIES:
                if valid_cat.lower() in cat_lower or cat_lower in valid_cat.lower():
                    outcome.outcome_category = valid_cat
                    break
        
        # Compute Cohen's d
        d, method = compute_cohens_d(outcome)
        outcome.computed_d = d
        outcome.computation_method = method
        
        extraction.outcomes.append(outcome)
    
    return extraction


# ============================================================================
# R2 CLIENT AND DOCUMENT LOADING
# ============================================================================

def get_r2_client():
    """Get Cloudflare R2 client."""
    account_id = os.environ.get('CLOUDFLARE_ACCOUNT_ID')
    return boto3.client(
        's3',
        endpoint_url=f'https://{account_id}.r2.cloudflarestorage.com',
        aws_access_key_id=os.environ.get('R2_ACCESS_KEY_ID'),
        aws_secret_access_key=os.environ.get('R2_SECRET_ACCESS_KEY'),
        region_name='auto'
    )


async def load_document_content(study_data: Dict, r2_client, bucket: str) -> Optional[str]:
    """Load markdown content from R2 using the r2_key from matched studies."""
    r2_key = study_data.get('r2_key')
    study_id = study_data.get('study_id')
    
    if not r2_key:
        print(f"  Warning: No r2_key for {study_id}")
        return None
    
    try:
        response = r2_client.get_object(Bucket=bucket, Key=r2_key)
        data = json.loads(response['Body'].read().decode('utf-8'))
        # The key is 'content' based on our earlier analysis
        content = data.get('content', data.get('md_content', ''))
        return content
    except Exception as e:
        print(f"  Warning: Could not load content for {study_id}: {e}")
        return None


# ============================================================================
# GROUND TRUTH LOADING
# ============================================================================

def load_ground_truth() -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Load ground truth from Excel files."""
    outcomes_gt = pd.read_excel('8WR QEX Combined.xlsx')
    # Try different encodings for CSV
    try:
        metadata_gt = pd.read_csv('master_UPG.csv', encoding='utf-8')
    except UnicodeDecodeError:
        try:
            metadata_gt = pd.read_csv('master_UPG.csv', encoding='latin-1')
        except:
            metadata_gt = pd.read_csv('master_UPG.csv', encoding='cp1252')
    return outcomes_gt, metadata_gt


def get_ground_truth_for_study(study_data: Dict, outcomes_gt: pd.DataFrame) -> Dict:
    """Get ground truth values for a specific study from matched_studies data and Excel."""
    gt = {}
    study_id = study_data.get('study_id')
    study_id_int = int(study_id)
    
    # Get basic metadata from the matched_studies data (already contains GT)
    matched_gt = study_data.get('ground_truth', {})
    gt['study_design'] = matched_gt.get('study_design')
    gt['country'] = matched_gt.get('country')
    gt['year'] = matched_gt.get('year')
    gt['program_name'] = matched_gt.get('program_name')
    gt['targeting_women'] = matched_gt.get('targeting_women')
    
    # Get intervention components from matched_studies
    gt['health_comp'] = matched_gt.get('health_comp')
    gt['skills_comp'] = matched_gt.get('skills_comp')
    gt['savings_comp'] = matched_gt.get('savings_comp')
    gt['coaching_comp'] = matched_gt.get('coaching_comp')
    gt['social_comp'] = matched_gt.get('social_comp')
    gt['consumption_support'] = matched_gt.get('consumption_support')
    gt['asset_transfer'] = matched_gt.get('asset_transfer')
    
    # Get outcomes from matched_studies (already has effect sizes)
    gt['outcomes'] = matched_gt.get('outcomes', [])
    
    return gt


# ============================================================================
# COMPARISON AND REPORTING
# ============================================================================

def compare_extraction_to_gt(extraction: StudyExtractionV3, gt: Dict) -> Dict:
    """Compare extraction results to ground truth."""
    comparison = {
        'study_id': extraction.study_id,
        'metadata': {},
        'components': {},
        'outcomes': {},
    }
    
    # Compare metadata
    metadata_fields = ['study_design', 'country', 'year', 'program_name', 'targeting_women']
    for field in metadata_fields:
        ext_var = getattr(extraction, field, None)
        ext_val = ext_var.value if ext_var else None
        gt_val = gt.get(field)
        
        if field == 'study_design':
            # Normalize comparison
            match = (ext_val == gt_val) if gt_val else None
        elif field == 'country':
            # Fuzzy match for country
            ext_lower = str(ext_val).lower() if ext_val else ''
            gt_lower = str(gt_val).lower() if gt_val else ''
            match = (ext_lower in gt_lower or gt_lower in ext_lower) if gt_val else None
        elif field == 'year':
            match = (ext_val == gt_val) if gt_val else None
        elif field == 'targeting_women':
            match = (int(ext_val or 0) == int(gt_val or 0)) if gt_val is not None else None
        else:
            match = None  # Can't compare text fields
        
        comparison['metadata'][field] = {
            'extracted': ext_val,
            'ground_truth': gt_val,
            'match': match,
            'confidence': ext_var.confidence if ext_var else None,
            'has_evidence': bool(ext_var.evidence_quote) if ext_var else False,
            'needs_review': ext_var.needs_review if ext_var else True,
        }
    
    # Compare intervention components
    component_fields = [
        'consumption_support', 'health_comp', 'asset_transfer', 
        'skills_comp', 'savings_comp', 'coaching_comp', 'social_comp'
    ]
    for field in component_fields:
        ext_var = getattr(extraction, field, None)
        ext_val = int(ext_var.value or 0) if ext_var and ext_var.value is not None else None
        gt_val = gt.get(field)
        gt_val_int = int(gt_val) if gt_val is not None and not pd.isna(gt_val) else None
        
        match = (ext_val == gt_val_int) if gt_val_int is not None and ext_val is not None else None
        
        comparison['components'][field] = {
            'extracted': ext_val,
            'ground_truth': gt_val_int,
            'match': match,
            'confidence': ext_var.confidence if ext_var else None,
            'has_evidence': bool(ext_var.evidence_quote) if ext_var else False,
            'needs_review': ext_var.needs_review if ext_var else True,
        }
    
    # Compare outcomes
    gt_outcomes = gt.get('outcomes', [])
    ext_outcomes = extraction.outcomes
    
    # Match by outcome category
    gt_by_cat = {}
    for o in gt_outcomes:
        cat = o.get('category', o.get('outcome_category', 'Unknown'))
        if cat not in gt_by_cat:
            gt_by_cat[cat] = []
        gt_by_cat[cat].append(o)
    
    ext_by_cat = {}
    for o in ext_outcomes:
        cat = o.outcome_category
        if cat not in ext_by_cat:
            ext_by_cat[cat] = []
        ext_by_cat[cat].append(o)
    
    # Category recall
    gt_categories = set(gt_by_cat.keys())
    ext_categories = set(ext_by_cat.keys())
    category_recall = len(gt_categories & ext_categories) / len(gt_categories) if gt_categories else 0
    
    comparison['outcomes'] = {
        'gt_count': len(gt_outcomes),
        'extracted_count': len(ext_outcomes),
        'category_recall': category_recall,
        'gt_categories': list(gt_categories),
        'ext_categories': list(ext_categories),
        'effect_size_comparisons': [],
    }
    
    # Compare effect sizes where possible
    for cat in gt_categories & ext_categories:
        for gt_o in gt_by_cat[cat]:
            # Handle both 'd' and 'effect_size_d' field names from different data sources
            gt_d = gt_o.get('d') or gt_o.get('effect_size_d')
            if gt_d is None or (isinstance(gt_d, float) and np.isnan(gt_d)):
                continue
            
            # Find matching extracted outcome
            for ext_o in ext_by_cat[cat]:
                if ext_o.computed_d is not None:
                    error = abs(ext_o.computed_d - gt_d)
                    comparison['outcomes']['effect_size_comparisons'].append({
                        'outcome_name': ext_o.outcome_name,
                        'category': cat,
                        'gt_d': gt_d,
                        'computed_d': ext_o.computed_d,
                        'error': error,
                        'method': ext_o.computation_method,
                        'accurate_01': error < 0.1,
                        'accurate_02': error < 0.2,
                    })
                    break  # Only match once per GT outcome
    
    return comparison


def format_extraction_report(extraction: StudyExtractionV3, comparison: Dict) -> str:
    """Generate detailed report for one study."""
    lines = []
    lines.append(f"\n{'='*80}")
    lines.append(f"STUDY: {extraction.study_id}")
    lines.append(f"{'='*80}")
    
    lines.append(f"\n--- TIER 1: BASIC METADATA ---")
    for field in ['study_design', 'country', 'year', 'author']:
        ext_var = getattr(extraction, field, None)
        if ext_var:
            comp = comparison['metadata'].get(field, {})
            match_str = "✓" if comp.get('match') else ("✗" if comp.get('match') is False else "?")
            evidence_str = "[+quote]" if ext_var.evidence_quote else "[no quote]"
            review_str = "[REVIEW]" if ext_var.needs_review else ""
            lines.append(f"  {field}: {ext_var.value} (conf={ext_var.confidence:.2f}) {evidence_str} {match_str} {review_str}")
            if ext_var.evidence_quote:
                quote = ext_var.evidence_quote[:100] + "..." if len(ext_var.evidence_quote) > 100 else ext_var.evidence_quote
                lines.append(f"    Quote: \"{quote}\"")
            if comp.get('ground_truth'):
                lines.append(f"    GT: {comp['ground_truth']}")
    
    lines.append(f"\n--- TIER 2: INTERVENTION COMPONENTS ---")
    for field in ['consumption_support', 'health_comp', 'asset_transfer', 'skills_comp', 
                  'savings_comp', 'coaching_comp', 'social_comp']:
        ext_var = getattr(extraction, field, None)
        if ext_var:
            comp = comparison['components'].get(field, {})
            match_str = "✓" if comp.get('match') else ("✗" if comp.get('match') is False else "?")
            evidence_str = "[+quote]" if ext_var.evidence_quote else "[no quote]"
            review_str = "[REVIEW]" if ext_var.needs_review else ""
            lines.append(f"  {field}: {ext_var.value} (conf={ext_var.confidence:.2f}) {evidence_str} {match_str} {review_str}")
            if ext_var.evidence_quote:
                quote = ext_var.evidence_quote[:80] + "..." if len(ext_var.evidence_quote) > 80 else ext_var.evidence_quote
                lines.append(f"    Quote: \"{quote}\"")
    
    lines.append(f"\n--- TIER 4: PROGRAM METADATA ---")
    for field in ['program_name', 'targeting_women']:
        ext_var = getattr(extraction, field, None)
        if ext_var:
            comp = comparison['metadata'].get(field, {})
            match_str = "✓" if comp.get('match') else ("✗" if comp.get('match') is False else "?")
            evidence_str = "[+quote]" if ext_var.evidence_quote else "[no quote]"
            lines.append(f"  {field}: {ext_var.value} (conf={ext_var.confidence:.2f}) {evidence_str} {match_str}")
    
    lines.append(f"\n--- TIER 3: OUTCOMES ({len(extraction.outcomes)} extracted) ---")
    outcome_comp = comparison['outcomes']
    lines.append(f"  GT outcomes: {outcome_comp['gt_count']}")
    lines.append(f"  Category recall: {outcome_comp['category_recall']*100:.1f}%")
    
    # Group by category
    by_cat = {}
    for o in extraction.outcomes:
        cat = o.outcome_category
        if cat not in by_cat:
            by_cat[cat] = []
        by_cat[cat].append(o)
    
    for cat in sorted(by_cat.keys()):
        lines.append(f"\n  [{cat}] ({len(by_cat[cat])} outcomes)")
        for o in by_cat[cat][:5]:  # Show first 5 per category
            d_str = f"d={o.computed_d:.4f}" if o.computed_d is not None else "d=None"
            method_str = f"({o.computation_method})" if o.computation_method else ""
            lines.append(f"    - {o.outcome_name[:50]}: coef={o.coefficient}, SE={o.standard_error}, {d_str} {method_str}")
        if len(by_cat[cat]) > 5:
            lines.append(f"    ... and {len(by_cat[cat])-5} more")
    
    # Effect size accuracy
    es_comps = outcome_comp.get('effect_size_comparisons', [])
    if es_comps:
        lines.append(f"\n  Effect Size Accuracy:")
        accurate_01 = sum(1 for c in es_comps if c['accurate_01'])
        accurate_02 = sum(1 for c in es_comps if c['accurate_02'])
        lines.append(f"    <0.1 error: {accurate_01}/{len(es_comps)} = {accurate_01/len(es_comps)*100:.1f}%")
        lines.append(f"    <0.2 error: {accurate_02}/{len(es_comps)} = {accurate_02/len(es_comps)*100:.1f}%")
        errors = [c['error'] for c in es_comps]
        lines.append(f"    Mean error: {np.mean(errors):.4f}")
        lines.append(f"    Max error: {max(errors):.4f}")
    
    return "\n".join(lines)


# ============================================================================
# MAIN EXECUTION
# ============================================================================

async def run_v3_extraction_full():
    """Run V3 extraction on all 43 matched studies with thorough reporting."""
    print("=" * 80)
    print("EXTRACTION V3 - Full Evaluation Run")
    print("=" * 80)
    
    # Load matched studies
    with open('evaluation/matched_studies_r2.json') as f:
        studies = json.load(f)
    
    print(f"\nLoaded {len(studies)} matched studies")
    
    # Load ground truth
    print("Loading ground truth...")
    outcomes_gt, metadata_gt = load_ground_truth()
    print(f"  Outcomes GT: {len(outcomes_gt)} rows")
    print(f"  Metadata GT: {len(metadata_gt)} rows")
    
    # Get R2 client
    bucket = os.environ.get('R2_BUCKET_NAME', 'devchat-pdfs')
    r2 = get_r2_client()
    
    # Run extraction
    all_extractions = []
    all_comparisons = []
    
    for i, study_data in enumerate(studies):
        study_id = study_data.get('study_id')
        print(f"\n[{i+1}/{len(studies)}] Processing {study_id}...")
        
        # Load document content
        content = await load_document_content(study_data, r2, bucket)
        if not content:
            print(f"  Skipping - no content available")
            continue
        
        # Run extraction
        try:
            extraction = await extract_study_v3(study_id, content)
            all_extractions.append(extraction)
            
            # Get ground truth and compare (use the matched_studies data which already has GT)
            gt = get_ground_truth_for_study(study_data, outcomes_gt)
            comparison = compare_extraction_to_gt(extraction, gt)
            all_comparisons.append(comparison)
            
            # Print brief summary
            meta_matches = sum(1 for v in comparison['metadata'].values() if v.get('match') == True)
            meta_total = sum(1 for v in comparison['metadata'].values() if v.get('match') is not None)
            comp_matches = sum(1 for v in comparison['components'].values() if v.get('match') == True)
            comp_total = sum(1 for v in comparison['components'].values() if v.get('match') is not None)
            print(f"  Metadata: {meta_matches}/{meta_total} | Components: {comp_matches}/{comp_total} | Outcomes: {len(extraction.outcomes)}")
            
        except Exception as e:
            print(f"  Error: {e}")
            import traceback
            traceback.print_exc()
    
    # Generate comprehensive report
    print("\n" + "=" * 80)
    print("GENERATING COMPREHENSIVE REPORT")
    print("=" * 80)
    
    report_lines = []
    report_lines.append("# Extraction V3 - Comprehensive Results Report")
    report_lines.append(f"\nDate: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    report_lines.append(f"Studies processed: {len(all_extractions)}")
    report_lines.append(f"Model: {MODEL}")
    
    # Aggregate metadata accuracy
    report_lines.append("\n## 1. METADATA ACCURACY")
    report_lines.append("\n| Field | Correct | Total | Accuracy | Has Evidence |")
    report_lines.append("|-------|---------|-------|----------|--------------|")
    
    for field in ['study_design', 'country', 'year', 'targeting_women']:
        matches = sum(1 for c in all_comparisons if c['metadata'].get(field, {}).get('match') == True)
        total = sum(1 for c in all_comparisons if c['metadata'].get(field, {}).get('match') is not None)
        has_evidence = sum(1 for c in all_comparisons if c['metadata'].get(field, {}).get('has_evidence'))
        acc = matches / total * 100 if total > 0 else 0
        report_lines.append(f"| {field} | {matches} | {total} | {acc:.1f}% | {has_evidence} |")
    
    # Aggregate component accuracy
    report_lines.append("\n## 2. INTERVENTION COMPONENT ACCURACY")
    report_lines.append("\n| Component | Correct | Total | Accuracy | Has Evidence |")
    report_lines.append("|-----------|---------|-------|----------|--------------|")
    
    for field in ['consumption_support', 'health_comp', 'asset_transfer', 'skills_comp', 
                  'savings_comp', 'coaching_comp', 'social_comp']:
        matches = sum(1 for c in all_comparisons if c['components'].get(field, {}).get('match') == True)
        total = sum(1 for c in all_comparisons if c['components'].get(field, {}).get('match') is not None)
        has_evidence = sum(1 for c in all_comparisons if c['components'].get(field, {}).get('has_evidence'))
        acc = matches / total * 100 if total > 0 else 0
        report_lines.append(f"| {field} | {matches} | {total} | {acc:.1f}% | {has_evidence} |")
    
    # Aggregate outcome accuracy
    report_lines.append("\n## 3. OUTCOME EXTRACTION ACCURACY")
    
    total_gt_outcomes = sum(c['outcomes']['gt_count'] for c in all_comparisons)
    total_ext_outcomes = sum(c['outcomes']['extracted_count'] for c in all_comparisons)
    avg_category_recall = np.mean([c['outcomes']['category_recall'] for c in all_comparisons])
    
    report_lines.append(f"\n- Total GT outcomes: {total_gt_outcomes}")
    report_lines.append(f"- Total extracted outcomes: {total_ext_outcomes}")
    report_lines.append(f"- Average category recall: {avg_category_recall*100:.1f}%")
    
    # Effect size accuracy
    all_es_comps = []
    for c in all_comparisons:
        all_es_comps.extend(c['outcomes'].get('effect_size_comparisons', []))
    
    if all_es_comps:
        report_lines.append("\n### Effect Size (Cohen's d) Accuracy")
        report_lines.append(f"\n- Total comparisons: {len(all_es_comps)}")
        
        accurate_01 = sum(1 for c in all_es_comps if c['accurate_01'])
        accurate_02 = sum(1 for c in all_es_comps if c['accurate_02'])
        errors = [c['error'] for c in all_es_comps]
        
        report_lines.append(f"- Accurate (<0.1 error): {accurate_01}/{len(all_es_comps)} = {accurate_01/len(all_es_comps)*100:.1f}%")
        report_lines.append(f"- Accurate (<0.2 error): {accurate_02}/{len(all_es_comps)} = {accurate_02/len(all_es_comps)*100:.1f}%")
        report_lines.append(f"- Mean error: {np.mean(errors):.4f}")
        report_lines.append(f"- Median error: {np.median(errors):.4f}")
        report_lines.append(f"- Max error: {max(errors):.4f}")
        
        # Breakdown by computation method
        report_lines.append("\n### By Computation Method")
        by_method = {}
        for c in all_es_comps:
            method = c.get('method', 'unknown')
            if method not in by_method:
                by_method[method] = []
            by_method[method].append(c)
        
        report_lines.append("\n| Method | Count | <0.1 Acc | Mean Error |")
        report_lines.append("|--------|-------|----------|------------|")
        for method, comps in sorted(by_method.items()):
            acc_01 = sum(1 for c in comps if c['accurate_01']) / len(comps) * 100
            mean_err = np.mean([c['error'] for c in comps])
            report_lines.append(f"| {method} | {len(comps)} | {acc_01:.1f}% | {mean_err:.4f} |")
    
    # Per-study details
    report_lines.append("\n## 4. PER-STUDY DETAILS")
    
    for extraction, comparison in zip(all_extractions, all_comparisons):
        report_lines.append(format_extraction_report(extraction, comparison))
    
    # Save report
    report_text = "\n".join(report_lines)
    report_path = Path('evaluation/v3_extraction_report.md')
    report_path.write_text(report_text)
    print(f"\nReport saved to {report_path}")
    
    # Save raw results
    results_path = Path('evaluation/v3_extraction_results.json')
    results_data = {
        'model': MODEL,
        'version': 'v3',
        'timestamp': datetime.now().isoformat(),
        'num_studies': len(all_extractions),
        'extractions': [asdict(e) for e in all_extractions],
        'comparisons': all_comparisons,
    }
    with open(results_path, 'w') as f:
        json.dump(results_data, f, indent=2, default=str)
    print(f"Results saved to {results_path}")
    
    # Print summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"\nStudies processed: {len(all_extractions)}")
    print(f"\nMetadata Accuracy:")
    for field in ['study_design', 'country', 'year', 'targeting_women']:
        matches = sum(1 for c in all_comparisons if c['metadata'].get(field, {}).get('match') == True)
        total = sum(1 for c in all_comparisons if c['metadata'].get(field, {}).get('match') is not None)
        print(f"  {field}: {matches}/{total} = {matches/total*100:.1f}%" if total > 0 else f"  {field}: N/A")
    
    print(f"\nComponent Accuracy:")
    for field in ['health_comp', 'skills_comp', 'savings_comp', 'coaching_comp', 'social_comp']:
        matches = sum(1 for c in all_comparisons if c['components'].get(field, {}).get('match') == True)
        total = sum(1 for c in all_comparisons if c['components'].get(field, {}).get('match') is not None)
        print(f"  {field}: {matches}/{total} = {matches/total*100:.1f}%" if total > 0 else f"  {field}: N/A")
    
    print(f"\nOutcome Accuracy:")
    print(f"  Category recall: {avg_category_recall*100:.1f}%")
    if all_es_comps:
        print(f"  Effect size <0.1 error: {accurate_01}/{len(all_es_comps)} = {accurate_01/len(all_es_comps)*100:.1f}%")
        print(f"  Mean error: {np.mean(errors):.4f}")
    
    return all_extractions, all_comparisons


if __name__ == "__main__":
    asyncio.run(run_v3_extraction_full())
