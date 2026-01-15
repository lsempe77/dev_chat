"""
Baseline Extraction Test - Run extraction on all 43 studies
Compares LLM extraction against ground truth to measure baseline accuracy.
"""
import os
import re
import json
import boto3
import asyncio
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from dotenv import load_dotenv
import httpx

load_dotenv()

# Configuration
OPENROUTER_API_KEY = os.environ.get('OPENROUTER_API_KEY')
MODEL = "anthropic/claude-3.5-sonnet"  # or use a cheaper model for testing


@dataclass
class ExtractionResult:
    """Result of extracting data from a document."""
    study_id: str
    extracted: Dict
    ground_truth: Dict
    accuracy: Dict  # Per-field accuracy


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


EXTRACTION_PROMPT = """You are an expert at extracting structured data from academic papers about poverty graduation programs.

Extract the following information from this document. If a field cannot be determined from the text, use null.

Fields to extract:
1. study_design: Either "RCT" (randomized controlled trial) or "Quasi-Experimental" (non-randomized)
2. country: The country where the study was conducted
3. year: Publication year
4. program_name: Name of the poverty graduation program evaluated
5. health_comp: 1 if program includes health component, 0 if not, null if unclear
6. skills_comp: 1 if program includes skills training, 0 if not, null if unclear
7. savings_comp: 1 if program includes savings component, 0 if not, null if unclear
8. coaching_comp: 1 if program includes coaching/mentoring, 0 if not, null if unclear
9. social_comp: 1 if program includes social/community component, 0 if not, null if unclear
10. targeting_women: 1 if program specifically targets women, 0 if not, null if unclear

Document content:
{content}

Respond ONLY with a valid JSON object containing these fields. Example:
{{"study_design": "RCT", "country": "Bangladesh", "year": 2019, "program_name": "BRAC TUP", "health_comp": 1, "skills_comp": 1, "savings_comp": 1, "coaching_comp": 1, "social_comp": 0, "targeting_women": 1}}
"""


async def extract_from_document(content: str, max_chars: int = 50000) -> Dict:
    """Run extraction on document content using LLM."""
    # Truncate content if too long
    if len(content) > max_chars:
        content = content[:max_chars] + "\n\n[Content truncated...]"
    
    prompt = EXTRACTION_PROMPT.format(content=content)
    
    async with httpx.AsyncClient(timeout=120) as client:
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
            json_match = re.search(r'\{[^{}]*\}', text, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            return json.loads(text)
        except json.JSONDecodeError:
            print(f"Failed to parse JSON: {text[:200]}")
            return {}


def calculate_accuracy(extracted: Dict, ground_truth: Dict) -> Dict:
    """Calculate per-field accuracy."""
    accuracy = {}
    
    # Study design (exact match)
    ext_design = extracted.get('study_design', '').upper() if extracted.get('study_design') else None
    gt_design = ground_truth.get('study_design', '').upper() if ground_truth.get('study_design') else None
    
    # Normalize
    if ext_design and 'RCT' in ext_design:
        ext_design = 'RCT'
    elif ext_design and 'QUASI' in ext_design:
        ext_design = 'QUASI-EXPERIMENTAL'
    
    if gt_design and 'RCT' in gt_design:
        gt_design = 'RCT'
    elif gt_design and 'QUASI' in gt_design:
        gt_design = 'QUASI-EXPERIMENTAL'
    
    accuracy['study_design'] = 1 if ext_design == gt_design else 0
    
    # Country (fuzzy match)
    ext_country = (extracted.get('country') or '').lower().strip()
    gt_country = (ground_truth.get('country') or '').lower().strip()
    accuracy['country'] = 1 if ext_country == gt_country else 0
    
    # Binary components
    for field in ['health_comp', 'skills_comp', 'savings_comp', 'coaching_comp', 'social_comp', 'targeting_women']:
        ext_val = extracted.get(field)
        gt_val = ground_truth.get(field)
        
        if gt_val is None:
            accuracy[field] = None  # Skip if no ground truth
        elif ext_val is None:
            accuracy[field] = 0  # Wrong if we didn't extract but GT exists
        else:
            accuracy[field] = 1 if int(ext_val) == int(gt_val) else 0
    
    return accuracy


async def run_baseline_test(studies: List[dict], r2, bucket: str) -> List[ExtractionResult]:
    """Run extraction on all studies and calculate accuracy."""
    results = []
    
    for i, study in enumerate(studies):
        study_id = study['study_id']
        ground_truth = study['ground_truth']
        r2_key = study['r2_key']
        
        print(f"[{i+1}/{len(studies)}] Processing {study_id}: {ground_truth['author']}...")
        
        try:
            # Download document
            doc = download_json(r2, bucket, r2_key)
            content = doc.get('content', '')
            
            if not content:
                print(f"  WARNING: No content for {study_id}")
                continue
            
            # Run extraction
            extracted = await extract_from_document(content)
            
            # Calculate accuracy
            accuracy = calculate_accuracy(extracted, ground_truth)
            
            result = ExtractionResult(
                study_id=study_id,
                extracted=extracted,
                ground_truth=ground_truth,
                accuracy=accuracy
            )
            results.append(result)
            
            # Print per-study results
            design_ok = "✓" if accuracy.get('study_design') == 1 else "✗"
            country_ok = "✓" if accuracy.get('country') == 1 else "✗"
            print(f"  Design: {design_ok} ({extracted.get('study_design')} vs {ground_truth.get('study_design')})")
            print(f"  Country: {country_ok} ({extracted.get('country')} vs {ground_truth.get('country')})")
            
        except Exception as e:
            print(f"  ERROR: {e}")
    
    return results


def calculate_overall_accuracy(results: List[ExtractionResult]) -> Dict:
    """Calculate overall accuracy across all studies."""
    totals = {}
    counts = {}
    
    for result in results:
        for field, value in result.accuracy.items():
            if value is not None:
                totals[field] = totals.get(field, 0) + value
                counts[field] = counts.get(field, 0) + 1
    
    accuracy = {}
    for field in totals:
        accuracy[field] = totals[field] / counts[field] if counts[field] > 0 else 0
    
    return accuracy


async def main():
    project_root = Path(__file__).parent.parent
    bucket = os.environ.get('R2_BUCKET_NAME', 'devchat-pdfs')
    
    print("=" * 60)
    print("BASELINE EXTRACTION TEST - ALL 43 STUDIES")
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
    
    # Run extraction on all studies
    results = await run_baseline_test(studies, r2, bucket)
    
    # Calculate overall accuracy
    print()
    print("=" * 60)
    print("BASELINE RESULTS")
    print("=" * 60)
    
    accuracy = calculate_overall_accuracy(results)
    
    print(f"\nOverall Accuracy ({len(results)} studies):")
    print(f"  study_design:    {accuracy.get('study_design', 0)*100:.1f}%")
    print(f"  country:         {accuracy.get('country', 0)*100:.1f}%")
    print(f"  health_comp:     {accuracy.get('health_comp', 0)*100:.1f}%")
    print(f"  skills_comp:     {accuracy.get('skills_comp', 0)*100:.1f}%")
    print(f"  savings_comp:    {accuracy.get('savings_comp', 0)*100:.1f}%")
    print(f"  coaching_comp:   {accuracy.get('coaching_comp', 0)*100:.1f}%")
    print(f"  social_comp:     {accuracy.get('social_comp', 0)*100:.1f}%")
    print(f"  targeting_women: {accuracy.get('targeting_women', 0)*100:.1f}%")
    
    # Save results
    output = {
        'model': MODEL,
        'num_studies': len(results),
        'overall_accuracy': accuracy,
        'results': [asdict(r) for r in results]
    }
    
    output_path = project_root / 'evaluation' / 'baseline_extraction_results.json'
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    
    print(f"\nResults saved to {output_path}")


if __name__ == '__main__':
    asyncio.run(main())
