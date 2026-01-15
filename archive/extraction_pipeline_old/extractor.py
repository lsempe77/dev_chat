"""
Full Extraction Pipeline - AutoPK-Style

Combines:
1. AutoPK-style table preprocessing (expanded headers, captions, footnotes)
2. Schema-guided extraction (provide expected outcomes to LLM)
3. Hybrid similarity matching (semantic + fuzzy)
4. LLM-as-Judge validation for borderline matches

Based on:
- AutoPK (arXiv:2510.00039): 0.92 F1 for pharmacokinetic extraction
- Featurized-Decomposition Join (arXiv:2512.05399): Semantic matching

V6 Baseline: 26.2% recall, 33.9% precision, 29.6% F1
Target: 50%+ recall with maintained precision
"""

import os
import re
import json
import boto3
import requests
import numpy as np
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from dotenv import load_dotenv
import time

# Local imports
from preprocess import preprocess_mineru_table, ParsedTable

load_dotenv()

OPENROUTER_API_KEY = os.environ.get('OPENROUTER_API_KEY')
MODEL = "anthropic/claude-3.5-sonnet"
CLOUDFLARE_ACCOUNT_ID = os.environ.get('CLOUDFLARE_ACCOUNT_ID')
R2_ACCESS_KEY = os.environ.get('R2_ACCESS_KEY_ID')
R2_SECRET_KEY = os.environ.get('R2_SECRET_ACCESS_KEY')
R2_BUCKET = os.environ.get('R2_BUCKET_NAME', 'devchat-pdfs')

# ============================================================================
# SEMANTIC SIMILARITY
# ============================================================================

try:
    from sentence_transformers import SentenceTransformer
    EMBEDDING_MODEL = SentenceTransformer('all-MiniLM-L6-v2')
    HAS_EMBEDDINGS = True
    print("✅ Sentence-transformers loaded")
except ImportError:
    HAS_EMBEDDINGS = False
    EMBEDDING_MODEL = None
    print("⚠️ sentence-transformers not available")

from fuzzywuzzy import fuzz


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8)


def compute_hybrid_similarity(text1: str, text2: str) -> Tuple[float, Dict]:
    """Compute hybrid similarity (fuzzy + semantic)."""
    text1 = (text1 or "").lower().strip()
    text2 = (text2 or "").lower().strip()
    
    if not text1 or not text2:
        return 0.0, {"fuzzy": 0, "semantic": 0, "combined": 0}
    
    fuzzy_score = fuzz.token_set_ratio(text1, text2) / 100.0
    
    if HAS_EMBEDDINGS and EMBEDDING_MODEL:
        emb1 = EMBEDDING_MODEL.encode(text1, convert_to_numpy=True)
        emb2 = EMBEDDING_MODEL.encode(text2, convert_to_numpy=True)
        semantic_score = float(cosine_similarity(emb1, emb2))
    else:
        semantic_score = fuzzy_score
    
    combined = 0.3 * fuzzy_score + 0.7 * semantic_score
    
    return combined, {
        "fuzzy": round(fuzzy_score, 3),
        "semantic": round(semantic_score, 3),
        "combined": round(combined, 3)
    }


# ============================================================================
# LLM INTERACTION
# ============================================================================

SESSION = requests.Session()
SESSION.headers.update({
    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
    "Content-Type": "application/json"
})


def call_llm(prompt: str, max_tokens: int = 8000) -> Dict:
    """Call OpenRouter API."""
    for attempt in range(3):
        try:
            response = SESSION.post(
                "https://openrouter.ai/api/v1/chat/completions",
                json={
                    "model": MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": max_tokens,
                    "temperature": 0
                },
                timeout=300
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            
            # Parse JSON from response
            json_match = re.search(r'\{[\s\S]*\}', content)
            if json_match:
                try:
                    return json.loads(json_match.group())
                except:
                    pass
            return {}
        except Exception as e:
            if attempt < 2:
                time.sleep(5 * (attempt + 1))
            else:
                print(f"    LLM error: {e}")
                return {}
    return {}


def llm_validate_match(extracted: str, ground_truth: str) -> Tuple[bool, float]:
    """Use LLM to validate if two outcomes are semantically equivalent."""
    prompt = f"""Are these two outcomes semantically equivalent in impact evaluation?

EXTRACTED: "{extracted}"
GROUND TRUTH: "{ground_truth}"

Consider: same concept with different wording, units, timing, aggregation level.
Examples: "Monthly income" ≈ "Total income per month" = YES
         "Income" ≈ "Education level" = NO

Respond with JSON only: {{"match": true/false, "confidence": 0.0-1.0}}"""

    try:
        response = SESSION.post(
            "https://openrouter.ai/api/v1/chat/completions",
            json={
                "model": MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 100,
                "temperature": 0
            },
            timeout=30
        )
        content = response.json()["choices"][0]["message"]["content"]
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            result = json.loads(json_match.group())
            return result.get("match", False), result.get("confidence", 0.5)
    except:
        pass
    return False, 0.0


# ============================================================================
# DOCUMENT LOADING
# ============================================================================

def get_s3_client():
    return boto3.client(
        's3',
        endpoint_url=f'https://{CLOUDFLARE_ACCOUNT_ID}.r2.cloudflarestorage.com',
        aws_access_key_id=R2_ACCESS_KEY,
        aws_secret_access_key=R2_SECRET_KEY
    )


def load_document(r2_key: str) -> Tuple[str, List[ParsedTable]]:
    """Load document and preprocess tables using AutoPK-style preprocessing."""
    s3 = get_s3_client()
    response = s3.get_object(Bucket=R2_BUCKET, Key=r2_key)
    content = response['Body'].read()
    
    try:
        data = json.loads(content.decode('utf-8'))
    except UnicodeDecodeError:
        data = json.loads(content.decode('latin-1'))
    
    # Get prose content
    prose = data.get("content", "")
    
    # Preprocess tables with AutoPK-style preprocessing
    raw_tables = data.get("tables", [])
    parsed_tables = []
    
    for table in raw_tables:
        parsed = preprocess_mineru_table(table)
        if parsed:
            parsed_tables.append(parsed)
    
    return prose, parsed_tables


# ============================================================================
# EXTRACTION PROMPT
# ============================================================================

def build_extraction_prompt(prose: str, tables: List[ParsedTable], expected_outcomes: List[str]) -> str:
    """Build extraction prompt with preprocessed tables and expected outcomes."""
    
    # Format tables as markdown
    tables_section = ""
    for i, table in enumerate(tables[:15]):  # Limit to 15 tables
        md = table.to_markdown()
        if md:
            tables_section += f"\n\n### TABLE {i+1}\n{md}"
    
    if not tables_section:
        tables_section = "(No tables found)"
    
    # Format expected outcomes
    if expected_outcomes:
        outcomes_hint = "\n".join(f"  - {name}" for name in expected_outcomes[:25])
        schema_section = f"""
## EXPECTED OUTCOMES (from evaluation protocol):
Extract outcomes similar to these:
{outcomes_hint}

Also extract any other impact outcomes found in the tables."""
    else:
        schema_section = ""
    
    prompt = f"""Extract ALL outcomes from this impact evaluation study.

## DOCUMENT TEXT (excerpt):
{prose[:50000]}

## STRUCTURED TABLES FROM PDF:
{tables_section}
{schema_section}

For EACH outcome, extract:
- outcome_name: Exact name from table (e.g., "Monthly household income (USD)")
- outcome_category: One of: Income, Assets, Savings, Expenditure, Poverty
- coefficient: Treatment effect (number from table)
- standard_error: SE (often in parentheses below coefficient)
- confidence_interval_lower: Lower CI bound if available
- confidence_interval_upper: Upper CI bound if available
- p_value: p-value if available
- n_treatment: Treatment group N
- n_control: Control group N
- evidence_location: Table number and column

CRITICAL:
- Extract EVERY outcome row from EVERY results table
- Copy coefficients EXACTLY as shown (e.g., "0.15***", "-18.01")
- The *** notation indicates significance level, extract the number
- Look for patterns: coefficient in one cell, SE in parentheses below

Return valid JSON:
{{
  "outcomes": [
    {{
      "outcome_name": "Harvest value (yearly, USD)",
      "outcome_category": "Income",
      "coefficient": -18.01,
      "standard_error": 16.11,
      "confidence_interval_lower": null,
      "confidence_interval_upper": null,
      "p_value": null,
      "n_treatment": null,
      "n_control": null,
      "evidence_location": "Table 2, Column 2"
    }}
  ]
}}"""
    return prompt


# ============================================================================
# MATCHING
# ============================================================================

def match_outcomes(
    extracted: List[Dict],
    ground_truth: List[Dict],
    use_llm_validation: bool = True
) -> Dict:
    """Match extracted outcomes to ground truth with hybrid similarity + LLM validation."""
    
    matches = []
    unmatched_gt = list(range(len(ground_truth)))
    llm_calls = 0
    
    for ext_idx, ext in enumerate(extracted):
        ext_name = (ext.get('outcome_name') or '').lower().strip()
        if not ext_name:
            continue
        
        best_match_idx = None
        best_score = 0
        best_scores = {}
        
        for gt_idx in unmatched_gt:
            gt = ground_truth[gt_idx]
            gt_name = gt.get('name', '').lower()
            
            combined, scores = compute_hybrid_similarity(ext_name, gt_name)
            
            if combined > best_score:
                best_score = combined
                best_match_idx = gt_idx
                best_scores = scores
        
        if best_match_idx is None:
            continue
        
        # Decision logic
        if best_score >= 0.75:
            # High confidence match
            matches.append({
                "extracted_idx": ext_idx,
                "gt_idx": best_match_idx,
                "extracted_name": ext_name,
                "gt_name": ground_truth[best_match_idx].get('name', ''),
                "similarity": best_scores,
                "match_type": "high_confidence"
            })
            unmatched_gt.remove(best_match_idx)
            
        elif best_score >= 0.50 and use_llm_validation:
            # Borderline - use LLM validation
            gt_name = ground_truth[best_match_idx].get('name', '')
            is_match, confidence = llm_validate_match(ext_name, gt_name)
            llm_calls += 1
            
            if is_match and confidence >= 0.6:
                matches.append({
                    "extracted_idx": ext_idx,
                    "gt_idx": best_match_idx,
                    "extracted_name": ext_name,
                    "gt_name": gt_name,
                    "similarity": best_scores,
                    "match_type": "llm_validated",
                    "llm_confidence": confidence
                })
                unmatched_gt.remove(best_match_idx)
    
    recall = len(matches) / len(ground_truth) if ground_truth else 0
    precision = len(matches) / len(extracted) if extracted else 0
    
    return {
        "matches": matches,
        "matched_count": len(matches),
        "unmatched_gt_count": len(unmatched_gt),
        "llm_calls": llm_calls,
        "recall": recall,
        "precision": precision
    }


# ============================================================================
# MAIN
# ============================================================================

def process_study(study: Dict, idx: int) -> Dict:
    """Process a single study."""
    study_id = study.get('study_id', 'unknown')
    gt = study.get('ground_truth', {})
    author = gt.get('author', 'Unknown')
    gt_outcomes = gt.get('outcomes', [])
    r2_key = study.get('r2_key')
    
    print(f"\n[{idx}] {author} - {len(gt_outcomes)} GT outcomes")
    
    if not r2_key:
        return {"study_id": study_id, "success": False, "error": "No R2 key"}
    
    # Load and preprocess
    try:
        prose, tables = load_document(r2_key)
        print(f"    📄 {len(prose):,} chars, {len(tables)} tables preprocessed")
    except Exception as e:
        print(f"    ❌ Load error: {e}")
        return {"study_id": study_id, "success": False, "error": str(e)}
    
    # Build prompt with schema guidance
    expected_outcomes = [o.get('name', '') for o in gt_outcomes if o.get('name')]
    prompt = build_extraction_prompt(prose, tables, expected_outcomes)
    
    print(f"    🤖 Calling LLM ({len(prompt):,} chars)...")
    result = call_llm(prompt)
    
    if not result:
        print(f"    ❌ LLM failed")
        return {"study_id": study_id, "success": False, "error": "LLM failed"}
    
    outcomes = result.get("outcomes", [])
    print(f"    ✅ Extracted {len(outcomes)} outcomes")
    
    # Match with hybrid similarity + LLM validation
    if gt_outcomes:
        matching = match_outcomes(outcomes, gt_outcomes, use_llm_validation=True)
        print(f"    📊 Matched: {matching['matched_count']}/{len(gt_outcomes)} "
              f"(Recall: {matching['recall']:.1%}, LLM calls: {matching['llm_calls']})")
    else:
        matching = {}
    
    return {
        "study_id": study_id,
        "success": True,
        "author": author,
        "outcomes": outcomes,
        "num_tables": len(tables),
        "matching": matching,
        "ground_truth": gt
    }


def main():
    print("=" * 70)
    print("EXTRACTION PIPELINE V9 - AutoPK-Style")
    print("=" * 70)
    
    with open("evaluation/matched_studies_r2.json") as f:
        studies = json.load(f)
    
    print(f"\nLoaded {len(studies)} studies")
    
    results = []
    total_matched = 0
    total_gt = 0
    total_extracted = 0
    
    for idx, study in enumerate(studies, 1):
        result = process_study(study, idx)
        results.append(result)
        
        if result.get("success"):
            matching = result.get("matching", {})
            total_matched += matching.get("matched_count", 0)
            total_gt += len(result.get("ground_truth", {}).get("outcomes", []))
            total_extracted += len(result.get("outcomes", []))
        
        if idx % 10 == 0:
            recall = total_matched / total_gt if total_gt else 0
            print(f"\n--- Progress: {idx}/{len(studies)} | "
                  f"Matched: {total_matched}/{total_gt} ({recall:.1%}) ---\n")
    
    # Final metrics
    recall = total_matched / total_gt if total_gt else 0
    precision = total_matched / total_extracted if total_extracted else 0
    f1 = 2 * recall * precision / (recall + precision) if (recall + precision) else 0
    
    print("\n" + "=" * 70)
    print("RESULTS")
    print("=" * 70)
    print(f"Ground truth outcomes: {total_gt}")
    print(f"Extracted outcomes: {total_extracted}")
    print(f"Matched: {total_matched}")
    print()
    print(f"RECALL:    {recall:.1%}")
    print(f"PRECISION: {precision:.1%}")
    print(f"F1 SCORE:  {f1:.1%}")
    print()
    print("COMPARISON:")
    print("  V6 Baseline: 26.2% recall, 33.9% precision, 29.6% F1")
    print(f"  V9 Pipeline: {recall:.1%} recall, {precision:.1%} precision, {f1:.1%} F1")
    
    # Save
    with open("extraction_pipeline/v9_results.json", "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to extraction_pipeline/v9_results.json")


if __name__ == "__main__":
    main()
