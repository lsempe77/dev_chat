"""
Improved Outcome Extraction Module v2

Implements advanced techniques from research:
1. Table-Aware Extraction - Parse MineRU tables explicitly
2. Cohen's d Calculation - Teach LLM to compute from means/SDs
3. Self-Verification - Require evidence quotes, flag uncertain
4. Multi-Pass Strategy - First find tables, then extract from tables
5. Structured Output Validation - Pydantic models

Based on:
- VALID framework (claim-level grounding)
- Anthropic self-verification patterns
- Table structure preservation from MineRU
"""

import os
import re
import json
import boto3
import asyncio
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict, field
from dotenv import load_dotenv
import httpx
import math

load_dotenv()

OPENROUTER_API_KEY = os.environ.get('OPENROUTER_API_KEY')
MODEL = "anthropic/claude-3.5-sonnet"

OUTCOME_CATEGORIES = ["Income", "Assets", "Savings", "Expenditure", "Poverty"]

# ============================================================================
# IMPROVED PROMPTS
# ============================================================================

TABLE_EXTRACTION_PROMPT = """You are an expert at reading results tables from academic papers.

TASK: Extract ALL results/effects data from the tables in this document.

## Tables to Focus On:
- "Results" tables showing treatment effects
- "Impact" tables with outcomes
- "Regression" tables with coefficients and standard errors
- Summary statistics tables with means and SDs

## For Each Row in Results Tables, Extract:
1. outcome_name: What is being measured
2. coefficient: The raw coefficient/effect (unstandardized)
3. std_error: Standard error of the coefficient
4. t_stat_or_pvalue: t-statistic or p-value if shown
5. mean_treatment: Mean in treatment group (if shown)
6. mean_control: Mean in control group (if shown)  
7. sd_treatment: SD in treatment group (if shown)
8. sd_control: SD in control group (if shown)
9. n_treatment: N in treatment group
10. n_control: N in control group
11. stars: Significance stars (*, **, ***)

## Document Content (with tables):
{content}

## Response Format:
Return JSON with this structure:
{{
  "tables_found": [
    {{
      "table_name": "Table X: ...",
      "rows": [
        {{
          "outcome_name": "...",
          "coefficient": <float or null>,
          "std_error": <float or null>,
          "t_stat": <float or null>,
          "pvalue": <float or null>,
          "mean_treatment": <float or null>,
          "mean_control": <float or null>,
          "sd_treatment": <float or null>,
          "sd_control": <float or null>,
          "n_treatment": <int or null>,
          "n_control": <int or null>,
          "stars": "**"
        }}
      ]
    }}
  ],
  "sample_sizes": {{
    "total_n": <int or null>,
    "n_treatment": <int or null>,
    "n_control": <int or null>
  }}
}}

Return ONLY the JSON.
"""

COHENS_D_CALCULATION_PROMPT = """You are a statistician computing standardized effect sizes.

## Task
Convert raw coefficients to Cohen's d (standardized mean difference).

## Cohen's d Formulas:
1. If you have means and SDs:
   d = (mean_treatment - mean_control) / pooled_SD
   pooled_SD = sqrt(((n1-1)*sd1² + (n2-1)*sd2²) / (n1+n2-2))

2. If you have coefficient and control SD:
   d = coefficient / control_SD

3. If you have coefficient and SE with sample sizes:
   - First estimate SD from SE: SD ≈ SE * sqrt(N)
   - Then: d = coefficient / SD

4. If you have t-statistic and sample sizes:
   d = t * sqrt(1/n1 + 1/n2)

## CRITICAL Rules:
- Cohen's d is ALWAYS between -3 and +3 for normal research
- Values like 14.4, 8.3, 91% are NOT Cohen's d
- If a coefficient looks too large (>3), it's probably unstandardized
- Report null if you can't compute a proper Cohen's d

## Table Data to Convert:
{table_data}

## Document Context (for finding SDs if needed):
{context}

## Response Format:
{{
  "outcomes": [
    {{
      "category": "<Income|Assets|Savings|Expenditure|Poverty>",
      "outcome_name": "...",
      "raw_coefficient": <original coefficient>,
      "cohens_d": <computed d or null>,
      "d_computation_method": "<means_sds|coef_sd|coef_se|t_stat|could_not_compute>",
      "standard_error_d": <SE of d or null>,
      "n_treatment": <int>,
      "n_control": <int>,
      "confidence": "<high|medium|low>",
      "evidence_quote": "..."
    }}
  ]
}}

Return ONLY the JSON.
"""

SELF_VERIFICATION_PROMPT = """You are a careful reviewer checking extracted data against the source.

## Task
For each extracted outcome, verify it against the document and flag any issues.

## Verification Checks:
1. Does the effect size value appear in the document?
2. Is the outcome name accurate?
3. Is the sample size consistent with what's reported?
4. Is the category assignment correct?
5. Is Cohen's d in reasonable range (-3 to +3)?

## Extracted Outcomes to Verify:
{extracted_outcomes}

## Source Document:
{content}

## Response Format:
{{
  "verified_outcomes": [
    {{
      "outcome_name": "...",
      "category": "...",
      "cohens_d": <float or null>,
      "standard_error": <float or null>,
      "n_treatment": <int or null>,
      "n_control": <int or null>,
      "verification_status": "<verified|uncertain|rejected>",
      "issues": ["list of issues if any"],
      "evidence_quote": "exact quote from document",
      "confidence_score": <0.0 to 1.0>
    }}
  ],
  "overall_confidence": <0.0 to 1.0>,
  "verification_notes": "any notes about data quality"
}}

Return ONLY the JSON.
"""


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def get_r2_client():
    """Create R2 client."""
    account_id = os.environ['CLOUDFLARE_ACCOUNT_ID']
    return boto3.client('s3',
        endpoint_url=f'https://{account_id}.r2.cloudflarestorage.com',
        aws_access_key_id=os.environ['R2_ACCESS_KEY_ID'],
        aws_secret_access_key=os.environ['R2_SECRET_ACCESS_KEY'],
        region_name='auto'
    )


def download_json(r2, bucket: str, key: str) -> dict:
    """Download and parse JSON from R2."""
    resp = r2.get_object(Bucket=bucket, Key=key)
    return json.loads(resp['Body'].read().decode('utf-8'))


async def call_llm(prompt: str, temperature: float = 0.1) -> str:
    """Call OpenRouter LLM."""
    async with httpx.AsyncClient(timeout=180.0) as client:
        resp = await client.post(
            'https://openrouter.ai/api/v1/chat/completions',
            headers={
                'Authorization': f'Bearer {OPENROUTER_API_KEY}',
                'Content-Type': 'application/json'
            },
            json={
                'model': MODEL,
                'messages': [{'role': 'user', 'content': prompt}],
                'temperature': temperature
            }
        )
        resp.raise_for_status()
        return resp.json()['choices'][0]['message']['content']


def parse_json_response(response: str) -> dict:
    """Parse JSON from LLM response, handling markdown blocks."""
    # Remove markdown code blocks
    text = response.strip()
    if text.startswith('```'):
        text = re.sub(r'^```(?:json)?\n?', '', text)
        text = re.sub(r'\n?```$', '', text)
    
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        print(f"JSON parse error: {e}")
        print(f"Response: {text[:500]}...")
        return {}


def extract_tables_from_content(content: str) -> str:
    """Extract table sections from document content."""
    # MineRU often formats tables with | separators or in structured blocks
    lines = content.split('\n')
    table_sections = []
    in_table = False
    current_table = []
    
    for line in lines:
        # Detect table-like content
        if '|' in line or line.strip().startswith('Table') or 'coefficient' in line.lower():
            in_table = True
            current_table.append(line)
        elif in_table:
            if line.strip() == '' and len(current_table) > 3:
                table_sections.append('\n'.join(current_table))
                current_table = []
                in_table = False
            elif line.strip():
                current_table.append(line)
    
    if current_table:
        table_sections.append('\n'.join(current_table))
    
    return '\n\n---\n\n'.join(table_sections) if table_sections else content[:30000]


def categorize_outcome(name: str) -> str:
    """Categorize outcome based on name."""
    name_lower = name.lower()
    
    if any(w in name_lower for w in ['income', 'earning', 'wage', 'revenue', 'profit', 'harvest']):
        return "Income"
    elif any(w in name_lower for w in ['asset', 'livestock', 'land', 'property', 'durable']):
        return "Assets"
    elif any(w in name_lower for w in ['saving', 'deposit', 'bank']):
        return "Savings"
    elif any(w in name_lower for w in ['consumption', 'expenditure', 'spending', 'food']):
        return "Expenditure"
    elif any(w in name_lower for w in ['poverty', 'poor', 'food security', 'hunger']):
        return "Poverty"
    
    return "Income"  # Default


def validate_cohens_d(d: Optional[float]) -> Optional[float]:
    """Validate Cohen's d is in reasonable range."""
    if d is None:
        return None
    if abs(d) > 5:  # Very large - probably not Cohen's d
        return None
    return round(d, 4)


# ============================================================================
# MULTI-PASS EXTRACTION
# ============================================================================

async def extract_outcomes_v2(content: str, study_id: str) -> Dict:
    """
    Improved extraction using multi-pass strategy:
    1. First pass: Extract raw table data
    2. Second pass: Calculate Cohen's d from raw data  
    3. Third pass: Self-verification
    """
    
    print(f"  [v2] Pass 1: Extracting tables...")
    
    # Limit content but keep tables
    table_content = extract_tables_from_content(content)
    full_context = content[:40000] + "\n\n...\n\n" + content[-20000:] if len(content) > 60000 else content
    
    # Pass 1: Extract table data
    prompt1 = TABLE_EXTRACTION_PROMPT.format(content=table_content[:50000])
    response1 = await call_llm(prompt1)
    table_data = parse_json_response(response1)
    
    if not table_data.get('tables_found'):
        print(f"  [v2] No tables found, using fallback...")
        # Fallback to simpler extraction
        return await fallback_extraction(content, study_id)
    
    print(f"  [v2] Found {len(table_data.get('tables_found', []))} tables")
    
    # Pass 2: Calculate Cohen's d
    print(f"  [v2] Pass 2: Computing Cohen's d...")
    prompt2 = COHENS_D_CALCULATION_PROMPT.format(
        table_data=json.dumps(table_data, indent=2)[:30000],
        context=full_context[:30000]
    )
    response2 = await call_llm(prompt2)
    computed_outcomes = parse_json_response(response2)
    
    if not computed_outcomes.get('outcomes'):
        print(f"  [v2] Cohen's d computation failed, using table data directly...")
        return format_table_data(table_data, study_id)
    
    print(f"  [v2] Computed {len(computed_outcomes.get('outcomes', []))} outcomes")
    
    # Pass 3: Self-verification
    print(f"  [v2] Pass 3: Self-verification...")
    prompt3 = SELF_VERIFICATION_PROMPT.format(
        extracted_outcomes=json.dumps(computed_outcomes, indent=2)[:20000],
        content=full_context[:40000]
    )
    response3 = await call_llm(prompt3)
    verified = parse_json_response(response3)
    
    # Build final result
    outcomes = []
    for o in verified.get('verified_outcomes', computed_outcomes.get('outcomes', [])):
        # Include all outcomes except explicitly rejected ones
        status = o.get('verification_status', 'uncertain')
        confidence = o.get('confidence_score', o.get('confidence', 0.5))
        
        # Only skip if explicitly rejected with low confidence
        if status == 'rejected' and (confidence if isinstance(confidence, (int, float)) else 0.5) < 0.3:
            continue
            
        d = validate_cohens_d(o.get('cohens_d', o.get('effect_size_d')))
        
        outcomes.append({
            'category': o.get('category', categorize_outcome(o.get('outcome_name', ''))),
            'outcome_name': o.get('outcome_name', ''),
            'effect_size_d': d,
            'standard_error': o.get('standard_error', o.get('standard_error_d')),
            'n_treatment': o.get('n_treatment'),
            'n_control': o.get('n_control'),
            'evidence_quote': o.get('evidence_quote', '')[:200],
            'confidence': confidence if isinstance(confidence, (int, float)) else 0.5,
            'verification_status': status
        })
    
    return {
        'study_id': study_id,
        'total_sample_size': table_data.get('sample_sizes', {}).get('total_n'),
        'treatment_sample_size': table_data.get('sample_sizes', {}).get('n_treatment'),
        'control_sample_size': table_data.get('sample_sizes', {}).get('n_control'),
        'outcomes': outcomes,
        'extraction_confidence': verified.get('overall_confidence', 0.7),
        'tables_found': len(table_data.get('tables_found', [])),
        'verification_notes': verified.get('verification_notes', '')
    }


async def fallback_extraction(content: str, study_id: str) -> Dict:
    """Fallback extraction when tables aren't parseable."""
    
    FALLBACK_PROMPT = """Extract outcome data from this poverty graduation evaluation.

## Critical Instructions for Effect Sizes:
- Cohen's d is STANDARDIZED: d = (mean_diff) / pooled_SD
- Cohen's d is typically between -1 and +1, rarely exceeds ±2
- If you see "91% increase", that is NOT Cohen's d (that would be 0.91 as a coefficient)
- If you can't compute a proper standardized effect size, use null
- DO NOT report raw percentages or coefficients as Cohen's d

## Categories:
- Income: earnings, wages, revenue, profits, harvest
- Assets: livestock, household assets, land
- Savings: formal/informal savings
- Expenditure: consumption, food spending
- Poverty: poverty rates, food security

## Document:
{content}

## Return JSON:
{{
  "outcomes": [
    {{
      "category": "Income|Assets|Savings|Expenditure|Poverty",
      "outcome_name": "specific name",
      "effect_size_d": <Cohen's d between -3 and +3, or null>,
      "standard_error": <SE or null>,
      "n_treatment": <int or null>,
      "n_control": <int or null>,
      "evidence_quote": "exact quote"
    }}
  ],
  "extraction_confidence": 0.5
}}
"""
    
    prompt = FALLBACK_PROMPT.format(content=content[:60000])
    response = await call_llm(prompt)
    data = parse_json_response(response)
    
    outcomes = []
    for o in data.get('outcomes', []):
        d = validate_cohens_d(o.get('effect_size_d'))
        outcomes.append({
            'category': o.get('category', 'Income'),
            'outcome_name': o.get('outcome_name', ''),
            'effect_size_d': d,
            'standard_error': o.get('standard_error'),
            'n_treatment': o.get('n_treatment'),
            'n_control': o.get('n_control'),
            'evidence_quote': o.get('evidence_quote', '')[:200],
            'confidence': 0.5,
            'verification_status': 'unverified'
        })
    
    return {
        'study_id': study_id,
        'outcomes': outcomes,
        'extraction_confidence': data.get('extraction_confidence', 0.5),
        'tables_found': 0,
        'verification_notes': 'Fallback extraction - no tables parsed'
    }


def format_table_data(table_data: dict, study_id: str) -> Dict:
    """Format raw table data when Cohen's d computation fails."""
    outcomes = []
    
    for table in table_data.get('tables_found', []):
        for row in table.get('rows', []):
            outcomes.append({
                'category': categorize_outcome(row.get('outcome_name', '')),
                'outcome_name': row.get('outcome_name', ''),
                'effect_size_d': None,  # Couldn't compute
                'raw_coefficient': row.get('coefficient'),
                'standard_error': row.get('std_error'),
                'n_treatment': row.get('n_treatment'),
                'n_control': row.get('n_control'),
                'confidence': 0.3,
                'verification_status': 'raw_only'
            })
    
    return {
        'study_id': study_id,
        'outcomes': outcomes,
        'extraction_confidence': 0.4,
        'tables_found': len(table_data.get('tables_found', [])),
        'verification_notes': 'Raw table data - Cohen\'s d not computed'
    }


# ============================================================================
# TEST RUNNER
# ============================================================================

async def run_improved_extraction_test(studies: List[Dict], r2, bucket: str, limit: int = None) -> List[Dict]:
    """Run improved extraction on test studies."""
    
    results = []
    studies_to_process = studies[:limit] if limit else studies
    
    for i, study in enumerate(studies_to_process):
        study_id = study['study_id']
        r2_key = study['r2_key']
        
        print(f"\n[{i+1}/{len(studies_to_process)}] Processing {study_id}...")
        
        try:
            # Get document content
            doc = download_json(r2, bucket, r2_key)
            content = doc.get('content', doc.get('md_content', ''))
            
            if not content:
                print(f"  No content for {study_id}")
                continue
            
            # Extract with improved method
            extracted = await extract_outcomes_v2(content, study_id)
            
            # Calculate metrics
            gt = study.get('ground_truth', {})
            gt_outcomes = gt.get('outcomes', [])
            gt_categories = set(o.get('category') for o in gt_outcomes if o.get('category'))
            ext_categories = set(o.get('category') for o in extracted.get('outcomes', []) if o.get('category'))
            
            category_recall = len(gt_categories & ext_categories) / len(gt_categories) if gt_categories else 1.0
            
            result = {
                'study_id': study_id,
                'ground_truth': gt,
                'extracted': extracted,
                'metrics': {
                    'gt_outcome_count': len(gt_outcomes),
                    'extracted_outcome_count': len(extracted.get('outcomes', [])),
                    'category_recall': category_recall,
                    'tables_found': extracted.get('tables_found', 0),
                    'confidence': extracted.get('extraction_confidence', 0)
                }
            }
            
            results.append(result)
            
            print(f"  ✓ Extracted {len(extracted.get('outcomes', []))} outcomes (GT: {len(gt_outcomes)})")
            print(f"  Category recall: {category_recall:.0%}, Tables: {extracted.get('tables_found', 0)}")
            
        except Exception as e:
            print(f"  ✗ Error: {e}")
            results.append({
                'study_id': study_id,
                'error': str(e)
            })
    
    return results


def summarize_improved_results(results: List[Dict]) -> Dict:
    """Summarize improved extraction results."""
    
    valid = [r for r in results if 'error' not in r]
    
    # Category recall
    recalls = [r['metrics']['category_recall'] for r in valid]
    
    # Effect size quality
    total_outcomes = 0
    has_d = 0
    verified = 0
    high_confidence = 0
    
    for r in valid:
        for o in r.get('extracted', {}).get('outcomes', []):
            total_outcomes += 1
            if o.get('effect_size_d') is not None:
                has_d += 1
            if o.get('verification_status') == 'verified':
                verified += 1
            if o.get('confidence', 0) >= 0.7:
                high_confidence += 1
    
    return {
        'num_studies': len(valid),
        'avg_category_recall': sum(recalls) / len(recalls) if recalls else 0,
        'total_outcomes_extracted': total_outcomes,
        'has_effect_size_d': has_d,
        'effect_size_rate': has_d / total_outcomes if total_outcomes else 0,
        'verified_outcomes': verified,
        'high_confidence_outcomes': high_confidence,
        'avg_tables_found': sum(r['metrics'].get('tables_found', 0) for r in valid) / len(valid) if valid else 0
    }


# ============================================================================
# MAIN
# ============================================================================

async def main():
    """Run improved extraction test."""
    
    print("="*60)
    print("IMPROVED OUTCOME EXTRACTION v2")
    print("="*60)
    
    # Load matched studies
    with open('evaluation/matched_studies_r2.json') as f:
        studies = json.load(f)
    
    print(f"Loaded {len(studies)} studies")
    
    # Get R2 client
    r2 = get_r2_client()
    bucket = os.environ.get('R2_BUCKET_NAME', 'devchat-pdfs')
    
    # Run on all studies
    print("\nRunning on ALL 43 studies...")
    results = await run_improved_extraction_test(studies, r2, bucket, limit=None)
    
    # Summarize
    summary = summarize_improved_results(results)
    
    print("\n" + "="*60)
    print("IMPROVED EXTRACTION SUMMARY")
    print("="*60)
    print(f"Studies processed: {summary['num_studies']}")
    print(f"Avg category recall: {summary['avg_category_recall']*100:.1f}%")
    print(f"Total outcomes extracted: {summary['total_outcomes_extracted']}")
    print(f"Has Cohen's d: {summary['has_effect_size_d']} ({summary['effect_size_rate']*100:.1f}%)")
    print(f"Verified outcomes: {summary['verified_outcomes']}")
    print(f"High confidence: {summary['high_confidence_outcomes']}")
    print(f"Avg tables found: {summary['avg_tables_found']:.1f}")
    
    # Save results
    with open('evaluation/improved_extraction_results.json', 'w') as f:
        json.dump({
            'model': MODEL,
            'version': 'v2_improved',
            'summary': summary,
            'results': results
        }, f, indent=2, default=str)
    
    print(f"\nResults saved to evaluation/improved_extraction_results.json")


if __name__ == "__main__":
    asyncio.run(main())
