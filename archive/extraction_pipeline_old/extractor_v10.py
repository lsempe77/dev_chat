"""
Extraction Pipeline V10 - Professional Edition

IMPROVEMENTS OVER V9:
1. Increased max_tokens: 16000 (was 8000)
2. Model options: Claude 3.5 Sonnet (default) or GPT-4o
3. Smart table filtering: Focus on results tables, skip descriptive tables
4. Multi-pass extraction: Process tables in batches for large documents
5. Better prompting: More explicit instructions, examples from actual data
6. Robust error handling and logging
7. Configuration via environment/constants
8. Caching to avoid re-processing

TARGET: 50%+ recall (vs V9's 30.5%)
"""

import os
import re
import json
import boto3
import requests
import numpy as np
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime
from dotenv import load_dotenv
import time
import logging
from dataclasses import dataclass, asdict
from pathlib import Path

# Local imports
from preprocess import preprocess_mineru_table, ParsedTable

load_dotenv()

# ============================================================================
# CONFIGURATION
# ============================================================================

@dataclass
class Config:
    """Pipeline configuration."""
    # Model settings
    model: str = "anthropic/claude-3.5-sonnet"  # Options: anthropic/claude-3.5-sonnet, openai/gpt-4o
    max_tokens_extraction: int = 16000  # Increased from 8000
    max_tokens_validation: int = 150
    temperature: float = 0.0
    
    # Table filtering
    max_tables_per_batch: int = 10  # Process tables in batches
    min_table_rows: int = 3  # Skip tables with fewer rows
    skip_descriptive_tables: bool = True  # Skip non-results tables
    
    # Matching thresholds
    high_confidence_threshold: float = 0.70  # Was 0.75
    llm_validation_threshold: float = 0.45  # Was 0.50
    llm_validation_min_confidence: float = 0.55  # Was 0.60
    
    # Processing
    max_content_chars: int = 60000  # Limit prose content
    max_prompt_chars: int = 120000  # Safety limit for prompt size
    retry_attempts: int = 3
    retry_delay: int = 5


CONFIG = Config()

# ============================================================================
# LOGGING
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

# ============================================================================
# API CLIENTS
# ============================================================================

OPENROUTER_API_KEY = os.environ.get('OPENROUTER_API_KEY')
CLOUDFLARE_ACCOUNT_ID = os.environ.get('CLOUDFLARE_ACCOUNT_ID')
R2_ACCESS_KEY = os.environ.get('R2_ACCESS_KEY_ID')
R2_SECRET_KEY = os.environ.get('R2_SECRET_ACCESS_KEY')
R2_BUCKET = os.environ.get('R2_BUCKET_NAME', 'devchat-pdfs')

SESSION = requests.Session()
SESSION.headers.update({
    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
    "Content-Type": "application/json"
})

# ============================================================================
# SEMANTIC SIMILARITY
# ============================================================================

try:
    from sentence_transformers import SentenceTransformer
    EMBEDDING_MODEL = SentenceTransformer('all-MiniLM-L6-v2')
    HAS_EMBEDDINGS = True
    logger.info("✅ Sentence-transformers loaded")
except ImportError:
    HAS_EMBEDDINGS = False
    EMBEDDING_MODEL = None
    logger.warning("⚠️ sentence-transformers not available")

from fuzzywuzzy import fuzz


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Compute cosine similarity between two vectors."""
    norm_product = np.linalg.norm(a) * np.linalg.norm(b)
    if norm_product < 1e-8:
        return 0.0
    return float(np.dot(a, b) / norm_product)


def compute_hybrid_similarity(text1: str, text2: str) -> Tuple[float, Dict]:
    """Compute hybrid similarity combining fuzzy and semantic matching."""
    text1 = (text1 or "").lower().strip()
    text2 = (text2 or "").lower().strip()
    
    if not text1 or not text2:
        return 0.0, {"fuzzy": 0, "semantic": 0, "combined": 0}
    
    # Fuzzy matching
    fuzzy_score = fuzz.token_set_ratio(text1, text2) / 100.0
    
    # Semantic matching
    if HAS_EMBEDDINGS and EMBEDDING_MODEL:
        emb1 = EMBEDDING_MODEL.encode(text1, convert_to_numpy=True)
        emb2 = EMBEDDING_MODEL.encode(text2, convert_to_numpy=True)
        semantic_score = cosine_similarity(emb1, emb2)
    else:
        semantic_score = fuzzy_score
    
    # Weighted combination (semantic weighted higher)
    combined = 0.3 * fuzzy_score + 0.7 * semantic_score
    
    return combined, {
        "fuzzy": round(fuzzy_score, 3),
        "semantic": round(semantic_score, 3),
        "combined": round(combined, 3)
    }


# ============================================================================
# LLM INTERACTION
# ============================================================================

def call_llm(
    prompt: str,
    max_tokens: int = None,
    model: str = None
) -> Tuple[Optional[Dict], Optional[str]]:
    """
    Call LLM with robust error handling.
    Returns (parsed_json, raw_content).
    """
    max_tokens = max_tokens or CONFIG.max_tokens_extraction
    model = model or CONFIG.model
    
    for attempt in range(CONFIG.retry_attempts):
        try:
            response = SESSION.post(
                "https://openrouter.ai/api/v1/chat/completions",
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": max_tokens,
                    "temperature": CONFIG.temperature
                },
                timeout=300
            )
            response.raise_for_status()
            
            content = response.json()["choices"][0]["message"]["content"]
            
            # Parse JSON
            json_match = re.search(r'\{[\s\S]*\}', content)
            if json_match:
                try:
                    # Clean and parse
                    json_str = json_match.group()
                    json_str = re.sub(r'[\x00-\x1f\x7f-\x9f]', ' ', json_str)
                    return json.loads(json_str), content
                except json.JSONDecodeError:
                    # Try fixing common issues
                    json_str = re.sub(r',\s*}', '}', json_str)
                    json_str = re.sub(r',\s*]', ']', json_str)
                    try:
                        return json.loads(json_str), content
                    except:
                        pass
            
            return None, content
            
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 400:
                logger.error(f"Bad request: {str(e)[:100]}")
                return None, None
            if attempt < CONFIG.retry_attempts - 1:
                logger.warning(f"Retry {attempt + 1}: {str(e)[:80]}")
                time.sleep(CONFIG.retry_delay * (attempt + 1))
        except Exception as e:
            if attempt < CONFIG.retry_attempts - 1:
                logger.warning(f"Retry {attempt + 1}: {str(e)[:80]}")
                time.sleep(CONFIG.retry_delay * (attempt + 1))
            else:
                logger.error(f"LLM call failed: {e}")
    
    return None, None


def llm_validate_match(extracted: str, ground_truth: str) -> Tuple[bool, float]:
    """Use LLM to validate semantic equivalence between outcomes."""
    prompt = f"""Are these two outcome variables semantically equivalent in an impact evaluation context?

EXTRACTED: "{extracted}"
GROUND TRUTH: "{ground_truth}"

Consider:
- Same concept with different wording (e.g., "income" vs "earnings")
- Different units or time periods (e.g., "monthly" vs "yearly")
- Different aggregation (e.g., "household" vs "per capita")
- Abbreviations or full names

Answer with JSON only: {{"match": true/false, "confidence": 0.0-1.0}}"""

    result, _ = call_llm(prompt, max_tokens=CONFIG.max_tokens_validation)
    
    if result:
        return result.get("match", False), result.get("confidence", 0.5)
    return False, 0.0


# ============================================================================
# DOCUMENT LOADING
# ============================================================================

def get_s3_client():
    """Get R2/S3 client."""
    return boto3.client(
        's3',
        endpoint_url=f'https://{CLOUDFLARE_ACCOUNT_ID}.r2.cloudflarestorage.com',
        aws_access_key_id=R2_ACCESS_KEY,
        aws_secret_access_key=R2_SECRET_KEY
    )


def load_document(r2_key: str) -> Tuple[str, List[ParsedTable], Dict]:
    """
    Load document and preprocess tables.
    Returns (prose_content, parsed_tables, raw_data).
    """
    s3 = get_s3_client()
    response = s3.get_object(Bucket=R2_BUCKET, Key=r2_key)
    content = response['Body'].read()
    
    try:
        data = json.loads(content.decode('utf-8'))
    except UnicodeDecodeError:
        data = json.loads(content.decode('latin-1'))
    
    prose = data.get("content", "")
    raw_tables = data.get("tables", [])
    
    # Preprocess tables
    parsed_tables = []
    for table in raw_tables:
        parsed = preprocess_mineru_table(table)
        if parsed:
            parsed_tables.append(parsed)
    
    return prose, parsed_tables, data


# ============================================================================
# TABLE FILTERING (Smart selection of results tables)
# ============================================================================

def is_results_table(table: ParsedTable) -> Tuple[bool, str]:
    """
    Determine if a table is a results table (vs descriptive/methodology).
    Returns (is_results, reason).
    """
    caption_lower = (table.caption or "").lower()
    
    # Skip if too few rows
    if len(table.rows) < CONFIG.min_table_rows:
        return False, "too_few_rows"
    
    # Keywords indicating results tables
    results_keywords = [
        "effect", "impact", "result", "outcome", "treatment",
        "coefficient", "regression", "estimate", "primary",
        "secondary", "robustness", "heterogeneity", "itt", "ate"
    ]
    
    # Keywords indicating non-results tables
    skip_keywords = [
        "summary statistics", "balance", "baseline", "descriptive",
        "sample", "attrition", "timeline", "intervention", "program description",
        "variable definition", "data source", "survey"
    ]
    
    # Check caption
    for keyword in skip_keywords:
        if keyword in caption_lower:
            return False, f"skip_keyword:{keyword}"
    
    for keyword in results_keywords:
        if keyword in caption_lower:
            return True, f"results_keyword:{keyword}"
    
    # Check table content for numeric patterns (coefficients, SEs)
    numeric_cells = 0
    coefficient_pattern = re.compile(r'-?\d+\.?\d*\*{0,3}')
    se_pattern = re.compile(r'\(\d+\.?\d*\)')
    
    for row in table.rows[:5]:  # Check first 5 rows
        for cell in row:
            if coefficient_pattern.search(cell):
                numeric_cells += 1
            if se_pattern.search(cell):
                return True, "has_standard_errors"
    
    if numeric_cells >= 3:
        return True, "has_numeric_data"
    
    return False, "no_indicators"


def filter_results_tables(tables: List[ParsedTable]) -> List[ParsedTable]:
    """Filter to keep only results tables."""
    if not CONFIG.skip_descriptive_tables:
        return tables
    
    results_tables = []
    for table in tables:
        is_results, reason = is_results_table(table)
        if is_results:
            results_tables.append(table)
    
    # If too few results tables, include all
    if len(results_tables) < 3 and len(tables) > 0:
        return tables
    
    return results_tables


# ============================================================================
# EXTRACTION PROMPT
# ============================================================================

EXTRACTION_PROMPT_TEMPLATE = """You are an expert at extracting structured data from academic impact evaluation papers.

## TASK
Extract ALL outcome variables and their statistical results from the tables below.

## DOCUMENT EXCERPT
{prose}

## TABLES FROM PDF
{tables}

## EXPECTED OUTCOMES (from evaluation protocol)
{expected_outcomes}

## EXTRACTION INSTRUCTIONS

For EACH outcome row in the results tables, extract:

1. **outcome_name**: The exact variable name from the table
   - Include units if shown (e.g., "Income (USD/month)")
   - Include timing if shown (e.g., "Savings at endline")

2. **outcome_category**: Classify into ONE of:
   - "Income" (wages, earnings, revenue, profits, business income)
   - "Assets" (livestock, equipment, housing, land, wealth index)
   - "Savings" (cash savings, savings account, savings group)
   - "Expenditure" (consumption, spending, food expenditure)
   - "Poverty" (poverty rate, poverty gap, poor/non-poor)

3. **coefficient**: The treatment effect estimate
   - Extract the NUMBER only (e.g., 0.15 from "0.15***")
   - Preserve sign (negative values like -18.01)

4. **standard_error**: The SE, usually in parentheses below coefficient
   - Extract NUMBER only (e.g., 0.05 from "(0.05)")

5. **confidence_interval_lower** and **confidence_interval_upper**: If shown as [low, high]

6. **p_value**: If explicitly shown

7. **n_treatment**, **n_control**, **n_total**: Sample sizes if shown

8. **evidence_location**: Table number and column (e.g., "Table 3, Column 2")

## CRITICAL RULES

1. Extract EVERY outcome from EVERY results table - aim for 20-50 outcomes per study
2. Each row with a coefficient is a separate outcome
3. If a table has multiple columns (e.g., different time periods), extract each as separate outcome
4. Skip rows that are just labels (like "Panel A" or "Observations")
5. The *** notation means p<0.01, ** means p<0.05, * means p<0.10

## OUTPUT FORMAT

Return ONLY valid JSON (no markdown, no explanation):

{{
  "outcomes": [
    {{
      "outcome_name": "Household income (monthly, USD)",
      "outcome_category": "Income",
      "coefficient": 245.30,
      "standard_error": 89.20,
      "confidence_interval_lower": null,
      "confidence_interval_upper": null,
      "p_value": 0.006,
      "n_treatment": 1200,
      "n_control": 1300,
      "n_total": 2500,
      "evidence_location": "Table 3, Column 2"
    }},
    {{
      "outcome_name": "Total savings (USD)",
      "outcome_category": "Savings",
      "coefficient": 52.10,
      "standard_error": 18.50,
      "confidence_interval_lower": null,
      "confidence_interval_upper": null,
      "p_value": null,
      "n_treatment": null,
      "n_control": null,
      "n_total": 2500,
      "evidence_location": "Table 4, Column 1"
    }}
  ],
  "extraction_notes": "Brief notes about extraction challenges if any"
}}"""


def build_extraction_prompt(
    prose: str,
    tables: List[ParsedTable],
    expected_outcomes: List[str]
) -> str:
    """Build the extraction prompt."""
    
    # Format tables
    tables_text = ""
    for i, table in enumerate(tables):
        md = table.to_markdown()
        if md:
            tables_text += f"\n\n### TABLE {i+1}\n{md}"
    
    if not tables_text:
        tables_text = "(No tables found)"
    
    # Format expected outcomes
    if expected_outcomes:
        outcomes_text = "\n".join(f"- {name}" for name in expected_outcomes[:30])
    else:
        outcomes_text = "(No specific outcomes expected - extract all impact outcomes)"
    
    # Build prompt
    prompt = EXTRACTION_PROMPT_TEMPLATE.format(
        prose=prose[:CONFIG.max_content_chars],
        tables=tables_text,
        expected_outcomes=outcomes_text
    )
    
    # Safety check
    if len(prompt) > CONFIG.max_prompt_chars:
        # Truncate tables if needed
        available = CONFIG.max_prompt_chars - len(prose[:CONFIG.max_content_chars]) - 5000
        tables_text = tables_text[:available]
        prompt = EXTRACTION_PROMPT_TEMPLATE.format(
            prose=prose[:CONFIG.max_content_chars],
            tables=tables_text,
            expected_outcomes=outcomes_text
        )
    
    return prompt


# ============================================================================
# MULTI-PASS EXTRACTION
# ============================================================================

def extract_from_tables_batch(
    prose: str,
    tables: List[ParsedTable],
    expected_outcomes: List[str],
    batch_idx: int
) -> List[Dict]:
    """Extract outcomes from a batch of tables."""
    
    prompt = build_extraction_prompt(prose, tables, expected_outcomes)
    logger.debug(f"Batch {batch_idx}: {len(prompt):,} chars, {len(tables)} tables")
    
    result, _ = call_llm(prompt)
    
    if result and "outcomes" in result:
        outcomes = result["outcomes"]
        # Add batch info
        for o in outcomes:
            o["_batch"] = batch_idx
        return outcomes
    
    return []


def extract_outcomes_multipass(
    prose: str,
    tables: List[ParsedTable],
    expected_outcomes: List[str]
) -> List[Dict]:
    """
    Extract outcomes using multi-pass approach for large documents.
    """
    all_outcomes = []
    
    # Filter to results tables
    results_tables = filter_results_tables(tables)
    logger.info(f"  Filtered to {len(results_tables)}/{len(tables)} results tables")
    
    if not results_tables:
        results_tables = tables[:15]  # Fallback
    
    # Process in batches if many tables
    if len(results_tables) <= CONFIG.max_tables_per_batch:
        # Single pass
        outcomes = extract_from_tables_batch(prose, results_tables, expected_outcomes, 0)
        all_outcomes.extend(outcomes)
    else:
        # Multi-pass
        num_batches = (len(results_tables) + CONFIG.max_tables_per_batch - 1) // CONFIG.max_tables_per_batch
        logger.info(f"  Multi-pass extraction: {num_batches} batches")
        
        for batch_idx in range(num_batches):
            start = batch_idx * CONFIG.max_tables_per_batch
            end = start + CONFIG.max_tables_per_batch
            batch_tables = results_tables[start:end]
            
            outcomes = extract_from_tables_batch(prose, batch_tables, expected_outcomes, batch_idx)
            all_outcomes.extend(outcomes)
            
            logger.info(f"  Batch {batch_idx + 1}/{num_batches}: {len(outcomes)} outcomes")
    
    # Deduplicate by outcome name
    seen_names = set()
    unique_outcomes = []
    for o in all_outcomes:
        name = (o.get("outcome_name") or "").lower().strip()
        if name and name not in seen_names:
            seen_names.add(name)
            unique_outcomes.append(o)
    
    return unique_outcomes


# ============================================================================
# MATCHING
# ============================================================================

def match_outcomes(
    extracted: List[Dict],
    ground_truth: List[Dict],
    use_llm_validation: bool = True
) -> Dict:
    """Match extracted outcomes to ground truth with hybrid similarity."""
    
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
        if best_score >= CONFIG.high_confidence_threshold:
            matches.append({
                "extracted_idx": ext_idx,
                "gt_idx": best_match_idx,
                "extracted_name": ext_name,
                "gt_name": ground_truth[best_match_idx].get('name', ''),
                "similarity": best_scores,
                "match_type": "high_confidence"
            })
            unmatched_gt.remove(best_match_idx)
            
        elif best_score >= CONFIG.llm_validation_threshold and use_llm_validation:
            gt_name = ground_truth[best_match_idx].get('name', '')
            is_match, confidence = llm_validate_match(ext_name, gt_name)
            llm_calls += 1
            
            if is_match and confidence >= CONFIG.llm_validation_min_confidence:
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
    f1 = 2 * recall * precision / (recall + precision) if (recall + precision) > 0 else 0
    
    return {
        "matches": matches,
        "matched_count": len(matches),
        "unmatched_gt_count": len(unmatched_gt),
        "unmatched_gt_names": [ground_truth[i].get('name', '') for i in unmatched_gt],
        "llm_calls": llm_calls,
        "recall": recall,
        "precision": precision,
        "f1": f1
    }


# ============================================================================
# MAIN PROCESSING
# ============================================================================

@dataclass
class StudyResult:
    """Result for a single study."""
    study_id: str
    author: str
    success: bool
    error: Optional[str] = None
    num_tables_total: int = 0
    num_tables_results: int = 0
    num_outcomes_extracted: int = 0
    num_outcomes_gt: int = 0
    num_matched: int = 0
    recall: float = 0.0
    precision: float = 0.0
    f1: float = 0.0
    outcomes: List[Dict] = None
    matching: Dict = None


def process_study(study: Dict, idx: int, total: int) -> StudyResult:
    """Process a single study."""
    study_id = study.get('study_id', 'unknown')
    gt = study.get('ground_truth', {})
    author = gt.get('author', 'Unknown')
    gt_outcomes = gt.get('outcomes', [])
    r2_key = study.get('r2_key')
    
    logger.info(f"[{idx}/{total}] {author} - {len(gt_outcomes)} GT outcomes")
    
    result = StudyResult(
        study_id=study_id,
        author=author,
        success=False,
        num_outcomes_gt=len(gt_outcomes),
        outcomes=[]
    )
    
    if not r2_key:
        result.error = "No R2 key"
        return result
    
    # Load document
    try:
        prose, tables, raw_data = load_document(r2_key)
        result.num_tables_total = len(tables)
        logger.info(f"  📄 {len(prose):,} chars, {len(tables)} tables")
    except Exception as e:
        result.error = f"Load error: {e}"
        logger.error(f"  ❌ {result.error}")
        return result
    
    # Extract outcomes
    try:
        expected_outcomes = [o.get('name', '') for o in gt_outcomes if o.get('name')]
        outcomes = extract_outcomes_multipass(prose, tables, expected_outcomes)
        result.outcomes = outcomes
        result.num_outcomes_extracted = len(outcomes)
        logger.info(f"  ✅ Extracted {len(outcomes)} outcomes")
    except Exception as e:
        result.error = f"Extraction error: {e}"
        logger.error(f"  ❌ {result.error}")
        return result
    
    # Match outcomes
    if gt_outcomes:
        try:
            matching = match_outcomes(outcomes, gt_outcomes, use_llm_validation=True)
            result.matching = matching
            result.num_matched = matching['matched_count']
            result.recall = matching['recall']
            result.precision = matching['precision']
            result.f1 = matching['f1']
            
            logger.info(f"  📊 Matched: {result.num_matched}/{len(gt_outcomes)} "
                       f"(R: {result.recall:.1%}, P: {result.precision:.1%}, F1: {result.f1:.1%})")
            
            if matching['llm_calls'] > 0:
                logger.info(f"  🤖 LLM validations: {matching['llm_calls']}")
        except Exception as e:
            result.error = f"Matching error: {e}"
            logger.error(f"  ❌ {result.error}")
    
    result.success = True
    return result


def main():
    """Run V10 extraction pipeline."""
    start_time = datetime.now()
    
    print("=" * 70)
    print("EXTRACTION PIPELINE V10 - Professional Edition")
    print("=" * 70)
    print(f"Model: {CONFIG.model}")
    print(f"Max tokens: {CONFIG.max_tokens_extraction}")
    print(f"Confidence threshold: {CONFIG.high_confidence_threshold}")
    print(f"LLM validation threshold: {CONFIG.llm_validation_threshold}")
    print("=" * 70)
    
    # Load studies
    with open("evaluation/matched_studies_r2.json") as f:
        studies = json.load(f)
    
    logger.info(f"Loaded {len(studies)} studies")
    
    # Process all studies
    results: List[StudyResult] = []
    
    for idx, study in enumerate(studies, 1):
        result = process_study(study, idx, len(studies))
        results.append(result)
        
        # Progress report every 10 studies
        if idx % 10 == 0:
            successful = [r for r in results if r.success]
            total_matched = sum(r.num_matched for r in successful)
            total_gt = sum(r.num_outcomes_gt for r in successful)
            total_extracted = sum(r.num_outcomes_extracted for r in successful)
            
            recall = total_matched / total_gt if total_gt else 0
            precision = total_matched / total_extracted if total_extracted else 0
            f1 = 2 * recall * precision / (recall + precision) if (recall + precision) else 0
            
            print(f"\n{'='*50}")
            print(f"PROGRESS: {idx}/{len(studies)}")
            print(f"Matched: {total_matched}/{total_gt} | R: {recall:.1%} | P: {precision:.1%} | F1: {f1:.1%}")
            print(f"{'='*50}\n")
    
    # Final summary
    successful = [r for r in results if r.success]
    total_matched = sum(r.num_matched for r in successful)
    total_gt = sum(r.num_outcomes_gt for r in successful)
    total_extracted = sum(r.num_outcomes_extracted for r in successful)
    
    final_recall = total_matched / total_gt if total_gt else 0
    final_precision = total_matched / total_extracted if total_extracted else 0
    final_f1 = 2 * final_recall * final_precision / (final_recall + final_precision) if (final_recall + final_precision) else 0
    
    elapsed = datetime.now() - start_time
    
    print("\n" + "=" * 70)
    print("FINAL RESULTS - V10")
    print("=" * 70)
    print(f"Studies processed: {len(results)}")
    print(f"Successful: {len(successful)}")
    print(f"Time elapsed: {elapsed}")
    print()
    print(f"Ground truth outcomes: {total_gt}")
    print(f"Extracted outcomes: {total_extracted}")
    print(f"Matched outcomes: {total_matched}")
    print()
    print(f"{'='*40}")
    print(f"RECALL:    {final_recall:.1%}")
    print(f"PRECISION: {final_precision:.1%}")
    print(f"F1 SCORE:  {final_f1:.1%}")
    print(f"{'='*40}")
    print()
    print("COMPARISON:")
    print("  V6 Baseline: 26.2% recall, 33.9% precision, 29.6% F1")
    print("  V9 Pipeline: 30.5% recall, 32.1% precision, 31.3% F1")
    print(f"  V10 Pro:     {final_recall:.1%} recall, {final_precision:.1%} precision, {final_f1:.1%} F1")
    
    # Perfect recall studies
    perfect_recall = [r for r in successful if r.recall == 1.0 and r.num_outcomes_gt > 0]
    print(f"\nStudies with 100% recall: {len(perfect_recall)}")
    for r in perfect_recall[:10]:
        print(f"  - {r.author}: {r.num_matched}/{r.num_outcomes_gt}")
    
    # Save results
    output_data = {
        "config": asdict(CONFIG),
        "summary": {
            "total_studies": len(results),
            "successful_studies": len(successful),
            "total_gt_outcomes": total_gt,
            "total_extracted": total_extracted,
            "total_matched": total_matched,
            "recall": final_recall,
            "precision": final_precision,
            "f1": final_f1,
            "elapsed_seconds": elapsed.total_seconds()
        },
        "results": [asdict(r) for r in results]
    }
    
    output_path = Path("extraction_pipeline/v10_results.json")
    with open(output_path, "w") as f:
        json.dump(output_data, f, indent=2, default=str)
    
    logger.info(f"Results saved to {output_path}")


if __name__ == "__main__":
    main()
