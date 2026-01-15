"""
Outcome Extraction Module

Extracts detailed outcome data from poverty graduation studies:
- Effect sizes (Cohen's d)
- Standard errors
- Sample sizes (treatment/control)
- Outcome categories and names
- Follow-up periods

Ground Truth Schema (from 8WR QEX Combined.xlsx):
- Outcome category: Income, Assets, Savings, Expenditure, Poverty
- Outcome name: Specific outcome measure
- d: Cohen's d effect size
- se(g): Standard error of effect size
- N treatment: Treatment group sample size
- N control: Control group sample size
- followup_months: Months after intervention
- Treatment: Treatment arm name
"""

import os
import re
import json
import boto3
import asyncio
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict, field
from dotenv import load_dotenv
import httpx

load_dotenv()

OPENROUTER_API_KEY = os.environ.get('OPENROUTER_API_KEY')
MODEL = "anthropic/claude-3.5-sonnet"

# Valid outcome categories from ground truth
OUTCOME_CATEGORIES = ["Income", "Assets", "Savings", "Expenditure", "Poverty"]


@dataclass
class ExtractedOutcome:
    """Single outcome extracted from a study."""
    category: str  # Income, Assets, Savings, Expenditure, Poverty
    outcome_name: str  # Specific measure name
    effect_size_d: Optional[float] = None  # Cohen's d
    standard_error: Optional[float] = None  # SE of effect size
    n_treatment: Optional[int] = None  # Treatment sample size
    n_control: Optional[int] = None  # Control sample size
    followup_months: Optional[int] = None  # Months after intervention
    treatment_arm: Optional[str] = None  # Name of treatment arm
    evidence_quote: Optional[str] = None  # Quote from paper supporting extraction


@dataclass
class OutcomeExtractionResult:
    """All outcomes extracted from a study."""
    study_id: str
    total_sample_size: Optional[int] = None  # Overall N
    treatment_sample_size: Optional[int] = None  # Overall treatment N
    control_sample_size: Optional[int] = None  # Overall control N
    outcomes: List[ExtractedOutcome] = field(default_factory=list)
    extraction_confidence: float = 0.0  # 0-1 confidence score


OUTCOME_EXTRACTION_PROMPT = """You are an expert at extracting quantitative results from academic impact evaluation papers.

Your task is to extract ALL reported outcomes with their effect sizes from this poverty graduation program evaluation.

## Outcome Categories to Extract:
1. **Income**: Wages, earnings, harvest value, revenue, profits
2. **Assets**: Livestock, household assets, business assets, land
3. **Savings**: Formal savings, informal savings, total savings
4. **Expenditure**: Consumption, food expenditure, total spending
5. **Poverty**: Poverty headcount, poverty gap, food security indices

## For EACH outcome, extract:
- category: One of [Income, Assets, Savings, Expenditure, Poverty]
- outcome_name: Specific name of the outcome measure
- effect_size_d: Cohen's d or standardized effect size (if reported)
- standard_error: SE of the effect size (if reported)
- n_treatment: Sample size in treatment group
- n_control: Sample size in control group
- followup_months: Months after intervention when measured
- evidence_quote: Brief quote from paper (max 100 chars) supporting this extraction

## Also extract overall sample sizes:
- total_sample_size: Total N across all groups
- treatment_sample_size: Total N in treatment
- control_sample_size: Total N in control

## Important:
- Look in tables, especially "Results" or "Impact" sections
- Effect sizes may be reported as:
  - Cohen's d
  - Standardized mean difference (SMD)
  - Beta coefficients (if standardized)
  - Sometimes need to calculate from means and SDs
- If effect size not directly reported, use null
- Include ALL outcomes, not just primary ones
- If multiple follow-up periods, extract each separately

## Document Content:
{content}

## Response Format:
Return a JSON object with this exact structure:
{{
  "total_sample_size": <int or null>,
  "treatment_sample_size": <int or null>,
  "control_sample_size": <int or null>,
  "outcomes": [
    {{
      "category": "<Income|Assets|Savings|Expenditure|Poverty>",
      "outcome_name": "<specific outcome name>",
      "effect_size_d": <float or null>,
      "standard_error": <float or null>,
      "n_treatment": <int or null>,
      "n_control": <int or null>,
      "followup_months": <int or null>,
      "evidence_quote": "<brief quote>"
    }}
  ],
  "extraction_confidence": <0.0 to 1.0>
}}

Return ONLY the JSON, no other text.
"""


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


async def extract_outcomes(content: str, max_chars: int = 80000) -> Dict:
    """Extract outcomes from document content using LLM."""
    # Truncate if too long (outcomes often in later sections)
    if len(content) > max_chars:
        # Keep first and last portions (abstract + results)
        content = content[:40000] + "\n\n[...middle content truncated...]\n\n" + content[-40000:]
    
    prompt = OUTCOME_EXTRACTION_PROMPT.format(content=content)
    
    async with httpx.AsyncClient(timeout=180) as client:
        response = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0,
                "max_tokens": 4000,  # Outcomes can be lengthy
            }
        )
        
        if response.status_code != 200:
            print(f"API error: {response.status_code} - {response.text}")
            return {}
        
        result = response.json()
        text = result['choices'][0]['message']['content']
        
        # Parse JSON from response
        try:
            # Try to find JSON in the response
            json_match = re.search(r'\{[\s\S]*\}', text)
            if json_match:
                return json.loads(json_match.group())
            return json.loads(text)
        except json.JSONDecodeError as e:
            print(f"Failed to parse JSON: {e}")
            print(f"Response: {text[:500]}")
            return {}


def calculate_outcome_accuracy(extracted: Dict, ground_truth: Dict) -> Dict:
    """Calculate accuracy metrics for outcome extraction."""
    gt_outcomes = ground_truth.get('outcomes', [])
    ext_outcomes = extracted.get('outcomes', [])
    
    metrics = {
        'gt_outcome_count': len(gt_outcomes),
        'extracted_outcome_count': len(ext_outcomes),
        'category_matches': 0,
        'effect_size_correlation': None,  # Would need to match outcomes first
    }
    
    # Count category distribution
    gt_categories = {}
    for o in gt_outcomes:
        cat = o.get('category', 'Unknown')
        gt_categories[cat] = gt_categories.get(cat, 0) + 1
    
    ext_categories = {}
    for o in ext_outcomes:
        cat = o.get('category', 'Unknown')
        ext_categories[cat] = ext_categories.get(cat, 0) + 1
    
    metrics['gt_categories'] = gt_categories
    metrics['extracted_categories'] = ext_categories
    
    # Category coverage (did we find at least one of each category?)
    gt_cats = set(gt_categories.keys())
    ext_cats = set(ext_categories.keys())
    metrics['category_recall'] = len(gt_cats & ext_cats) / len(gt_cats) if gt_cats else 0
    
    return metrics


async def run_outcome_extraction_test(studies: List[dict], r2, bucket: str, limit: int = None) -> List[Dict]:
    """Run outcome extraction on studies."""
    results = []
    
    studies_to_process = studies[:limit] if limit else studies
    
    for i, study in enumerate(studies_to_process):
        study_id = study['study_id']
        ground_truth = study['ground_truth']
        r2_key = study['r2_key']
        
        print(f"[{i+1}/{len(studies_to_process)}] Extracting outcomes: {study_id} ({ground_truth['author']})...")
        
        try:
            # Download document
            doc = download_json(r2, bucket, r2_key)
            content = doc.get('content', '')
            
            if not content:
                print(f"  WARNING: No content for {study_id}")
                continue
            
            # Run extraction
            extracted = await extract_outcomes(content)
            
            # Calculate metrics
            metrics = calculate_outcome_accuracy(extracted, ground_truth)
            
            # Print summary
            print(f"  Ground truth: {metrics['gt_outcome_count']} outcomes")
            print(f"  Extracted: {metrics['extracted_outcome_count']} outcomes")
            print(f"  Category recall: {metrics['category_recall']*100:.0f}%")
            
            results.append({
                'study_id': study_id,
                'ground_truth': ground_truth,
                'extracted': extracted,
                'metrics': metrics
            })
            
        except Exception as e:
            print(f"  ERROR: {e}")
            import traceback
            traceback.print_exc()
    
    return results


def summarize_results(results: List[Dict]) -> Dict:
    """Summarize outcome extraction results."""
    total_gt_outcomes = sum(r['metrics']['gt_outcome_count'] for r in results)
    total_ext_outcomes = sum(r['metrics']['extracted_outcome_count'] for r in results)
    avg_category_recall = sum(r['metrics']['category_recall'] for r in results) / len(results) if results else 0
    
    return {
        'num_studies': len(results),
        'total_gt_outcomes': total_gt_outcomes,
        'total_extracted_outcomes': total_ext_outcomes,
        'avg_outcomes_per_study_gt': total_gt_outcomes / len(results) if results else 0,
        'avg_outcomes_per_study_ext': total_ext_outcomes / len(results) if results else 0,
        'avg_category_recall': avg_category_recall,
    }


async def main():
    project_root = Path(__file__).parent.parent
    bucket = os.environ.get('R2_BUCKET_NAME', 'devchat-pdfs')
    
    print("=" * 60)
    print("OUTCOME EXTRACTION TEST")
    print("=" * 60)
    print()
    
    # Load matched studies
    matched_path = project_root / 'evaluation' / 'matched_studies_r2.json'
    with open(matched_path) as f:
        studies = json.load(f)
    
    print(f"Loaded {len(studies)} matched studies")
    print(f"Using model: {MODEL}")
    print()
    
    # Connect to R2
    r2 = get_r2_client()
    
    # Run on all studies
    results = await run_outcome_extraction_test(studies, r2, bucket)
    
    # Summarize
    print()
    print("=" * 60)
    print("OUTCOME EXTRACTION SUMMARY")
    print("=" * 60)
    
    summary = summarize_results(results)
    print(f"\nStudies processed: {summary['num_studies']}")
    print(f"Ground truth outcomes: {summary['total_gt_outcomes']}")
    print(f"Extracted outcomes: {summary['total_extracted_outcomes']}")
    print(f"Avg outcomes/study (GT): {summary['avg_outcomes_per_study_gt']:.1f}")
    print(f"Avg outcomes/study (Ext): {summary['avg_outcomes_per_study_ext']:.1f}")
    print(f"Avg category recall: {summary['avg_category_recall']*100:.1f}%")
    
    # Save results
    output = {
        'model': MODEL,
        'summary': summary,
        'results': results
    }
    
    output_path = project_root / 'evaluation' / 'outcome_extraction_results.json'
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    
    print(f"\nResults saved to {output_path}")


if __name__ == '__main__':
    asyncio.run(main())
