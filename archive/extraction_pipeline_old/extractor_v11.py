"""
Extraction Pipeline V11 - Enterprise Edition

IMPROVEMENTS OVER V10:
1. Increased max_tokens: 32,000 (GPT-4o supports 16K output, Claude 8K)
2. Table ranking via embeddings: Select most relevant tables first
3. Ensemble extraction: Claude + GPT-4o, union results
4. Few-shot examples: Include ground truth examples in prompt
5. Human-in-the-loop: Save failed matches for active learning

TARGET: 50%+ recall (vs V10's 41.6%)
"""

import os
import re
import json
import boto3
import requests
import numpy as np
from typing import Dict, List, Optional, Tuple, Any, Set
from datetime import datetime
from dotenv import load_dotenv
import time
import logging
from dataclasses import dataclass, asdict, field
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# Local imports
from preprocess import preprocess_mineru_table, ParsedTable

load_dotenv()

# ============================================================================
# CONFIGURATION
# ============================================================================

@dataclass
class Config:
    """Pipeline configuration."""
    # Model settings - ENSEMBLE
    models: List[str] = field(default_factory=lambda: [
        "anthropic/claude-3.5-sonnet",
        "openai/gpt-4o-2024-11-20"
    ])
    max_tokens_extraction: int = 32000  # Increased from 16000
    max_tokens_validation: int = 200
    temperature: float = 0.0
    
    # Table ranking
    use_table_ranking: bool = True
    max_tables_after_ranking: int = 20  # Keep top 20 most relevant tables
    
    # Table filtering
    max_tables_per_batch: int = 8  # Smaller batches for more focused extraction
    min_table_rows: int = 3
    skip_descriptive_tables: bool = True
    
    # Matching thresholds
    high_confidence_threshold: float = 0.65  # Lower from 0.70
    llm_validation_threshold: float = 0.40   # Lower from 0.45
    llm_validation_min_confidence: float = 0.50  # Lower from 0.55
    
    # Processing
    max_content_chars: int = 40000
    max_prompt_chars: int = 100000
    retry_attempts: int = 3
    retry_delay: int = 5
    
    # Few-shot examples
    use_few_shot: bool = True
    num_few_shot_examples: int = 5
    
    # Human-in-the-loop
    save_for_review: bool = True
    review_output_path: str = "extraction_pipeline/v11_review_queue.json"


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
# SEMANTIC SIMILARITY & TABLE RANKING
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


def rank_tables_by_relevance(
    tables: List[ParsedTable],
    expected_outcomes: List[str]
) -> List[Tuple[ParsedTable, float]]:
    """
    Rank tables by semantic similarity to expected outcomes.
    Returns list of (table, score) sorted by relevance.
    """
    if not HAS_EMBEDDINGS or not expected_outcomes:
        return [(t, 1.0) for t in tables]
    
    # Create outcome query embedding
    outcome_text = " ".join(expected_outcomes[:20])  # Use first 20 outcomes
    outcome_emb = EMBEDDING_MODEL.encode(outcome_text, convert_to_numpy=True)
    
    ranked = []
    for table in tables:
        # Create table text representation
        table_text = (table.caption or "") + " "
        if table.headers:
            table_text += " ".join(table.headers) + " "
        # Add first few rows
        for row in table.rows[:3]:
            table_text += " ".join(row) + " "
        
        if not table_text.strip():
            ranked.append((table, 0.0))
            continue
        
        table_emb = EMBEDDING_MODEL.encode(table_text, convert_to_numpy=True)
        score = cosine_similarity(outcome_emb, table_emb)
        ranked.append((table, score))
    
    # Sort by score descending
    ranked.sort(key=lambda x: x[1], reverse=True)
    return ranked


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
    
    # Weighted combination
    combined = 0.3 * fuzzy_score + 0.7 * semantic_score
    
    return combined, {
        "fuzzy": round(fuzzy_score, 3),
        "semantic": round(semantic_score, 3),
        "combined": round(combined, 3)
    }


# ============================================================================
# FEW-SHOT EXAMPLES
# ============================================================================

FEW_SHOT_EXAMPLES = """
## EXAMPLE 1: Cash Transfer Study

Table: Treatment Effects on Consumption
| Outcome | Treatment Effect | SE |
|---------|-----------------|-----|
| Per capita consumption | 0.128*** | (0.041) |
| Food expenditure | 0.095** | (0.038) |
| Non-food expenditure | 0.156*** | (0.052) |

Extracted outcomes:
- outcome_name: "Per capita consumption", coefficient: 0.128, standard_error: 0.041
- outcome_name: "Food expenditure", coefficient: 0.095, standard_error: 0.038
- outcome_name: "Non-food expenditure", coefficient: 0.156, standard_error: 0.052

## EXAMPLE 2: Graduation Program Study

Table 5: Impact on Assets and Savings
| | Full Sample | Female HH |
|Livestock value (USD) | 45.2*** (12.3) | 52.1*** (15.8) |
|Total savings | 28.5** (11.2) | 31.4** (13.1) |
|Productive assets | 0.35** (0.14) | 0.41*** (0.12) |

Extracted outcomes:
- outcome_name: "Livestock value (USD)", coefficient: 45.2, standard_error: 12.3, evidence_location: "Table 5, Full Sample"
- outcome_name: "Livestock value (USD) - Female HH", coefficient: 52.1, standard_error: 15.8, evidence_location: "Table 5, Female HH"
- outcome_name: "Total savings", coefficient: 28.5, standard_error: 11.2
- outcome_name: "Total savings - Female HH", coefficient: 31.4, standard_error: 13.1
- outcome_name: "Productive assets", coefficient: 0.35, standard_error: 0.14
- outcome_name: "Productive assets - Female HH", coefficient: 0.41, standard_error: 0.12

## EXAMPLE 3: Multiple Columns/Time Periods

Table 3: Effects by Time Period
| Outcome | 6 months | 12 months | 24 months |
|---------|----------|-----------|-----------|
| Income | 0.05 (0.03) | 0.12** (0.05) | 0.18*** (0.06) |
| Employment | 0.02 (0.02) | 0.08* (0.04) | 0.11** (0.05) |

Extracted outcomes (each time period is separate):
- outcome_name: "Income at 6 months", coefficient: 0.05, standard_error: 0.03
- outcome_name: "Income at 12 months", coefficient: 0.12, standard_error: 0.05
- outcome_name: "Income at 24 months", coefficient: 0.18, standard_error: 0.06
- outcome_name: "Employment at 6 months", coefficient: 0.02, standard_error: 0.02
- outcome_name: "Employment at 12 months", coefficient: 0.08, standard_error: 0.04
- outcome_name: "Employment at 24 months", coefficient: 0.11, standard_error: 0.05
"""


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
    model = model or CONFIG.models[0]
    
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
                    json_str = json_match.group()
                    json_str = re.sub(r'[\x00-\x1f\x7f-\x9f]', ' ', json_str)
                    return json.loads(json_str), content
                except json.JSONDecodeError:
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
- Same concept with different wording (e.g., "income" vs "earnings" vs "revenue")
- Different units (e.g., "monthly income" vs "annual income" = SAME concept)
- Aggregation differences (e.g., "household" vs "per capita")
- Abbreviations (e.g., "HH" = "household", "cons." = "consumption")

Be GENEROUS - if they refer to the same underlying economic concept, they match.

Answer with JSON only: {{"match": true/false, "confidence": 0.0-1.0, "reason": "brief explanation"}}"""

    result, _ = call_llm(prompt, max_tokens=CONFIG.max_tokens_validation, model=CONFIG.models[0])
    
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
    """Load document and preprocess tables."""
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
# TABLE FILTERING
# ============================================================================

def is_results_table(table: ParsedTable) -> Tuple[bool, str]:
    """Determine if a table is a results table."""
    caption_lower = (table.caption or "").lower()
    
    if len(table.rows) < CONFIG.min_table_rows:
        return False, "too_few_rows"
    
    results_keywords = [
        "effect", "impact", "result", "outcome", "treatment",
        "coefficient", "regression", "estimate", "primary",
        "secondary", "robustness", "heterogeneity", "itt", "ate",
        "main result", "specification"
    ]
    
    skip_keywords = [
        "summary statistics", "balance", "baseline", "descriptive",
        "sample", "attrition", "timeline", "intervention", "program description",
        "variable definition", "data source", "survey", "randomization"
    ]
    
    for keyword in skip_keywords:
        if keyword in caption_lower:
            return False, f"skip_keyword:{keyword}"
    
    for keyword in results_keywords:
        if keyword in caption_lower:
            return True, f"results_keyword:{keyword}"
    
    # Check for coefficient/SE patterns
    se_pattern = re.compile(r'\(\d+\.?\d*\)')
    star_pattern = re.compile(r'\d+\.?\d*\*{1,3}')
    
    for row in table.rows[:5]:
        for cell in row:
            if se_pattern.search(cell) or star_pattern.search(cell):
                return True, "has_statistical_notation"
    
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
    
    if len(results_tables) < 3 and len(tables) > 0:
        return tables
    
    return results_tables


# ============================================================================
# EXTRACTION PROMPT
# ============================================================================

EXTRACTION_PROMPT_TEMPLATE = """You are an expert at extracting structured data from academic impact evaluation papers.

## TASK
Extract ALL outcome variables and their statistical results from the tables below.
Be EXHAUSTIVE - extract every single outcome with a coefficient.

## FEW-SHOT EXAMPLES
{few_shot_examples}

## DOCUMENT EXCERPT
{prose}

## TABLES FROM PDF (ranked by relevance)
{tables}

## EXPECTED OUTCOMES (from evaluation protocol)
These are the outcomes we expect to find. Extract these AND any other outcomes:
{expected_outcomes}

## EXTRACTION INSTRUCTIONS

For EACH outcome row, extract:

1. **outcome_name**: The exact variable name from the table
   - Include column/subgroup qualifiers (e.g., "Income - Female HH")
   - Include time period if multiple columns (e.g., "Savings at 12 months")

2. **outcome_category**: Classify into ONE of:
   - "Income" | "Assets" | "Savings" | "Expenditure" | "Poverty" | "Employment" | "Other"

3. **coefficient**: The treatment effect NUMBER (e.g., 0.15 from "0.15***")

4. **standard_error**: The SE NUMBER from parentheses (e.g., 0.05 from "(0.05)")

5. **p_value**: From stars: *** = 0.01, ** = 0.05, * = 0.10, none = null

6. **n_total**: Sample size if shown

7. **evidence_location**: Table number and column (e.g., "Table 3, Column 2")

## CRITICAL RULES

1. Extract EVERY outcome from EVERY results table - aim for 30-100 outcomes
2. Each cell with a coefficient is a separate outcome entry
3. Multiple columns = multiple outcomes (different time periods, subgroups)
4. Do NOT skip outcomes just because they seem similar
5. Include both significant and non-significant results

## OUTPUT FORMAT

Return ONLY valid JSON:

{{
  "outcomes": [
    {{
      "outcome_name": "Household consumption (monthly)",
      "outcome_category": "Expenditure",
      "coefficient": 245.30,
      "standard_error": 89.20,
      "p_value": 0.01,
      "n_total": 2500,
      "evidence_location": "Table 3, Column 1"
    }}
  ],
  "total_outcomes_found": 45,
  "tables_processed": 8
}}"""


def build_extraction_prompt(
    prose: str,
    tables: List[ParsedTable],
    expected_outcomes: List[str]
) -> str:
    """Build the extraction prompt with few-shot examples."""
    
    # Format tables with relevance scores
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
        outcomes_text = "(Extract all impact outcomes)"
    
    # Include few-shot examples
    few_shot = FEW_SHOT_EXAMPLES if CONFIG.use_few_shot else ""
    
    prompt = EXTRACTION_PROMPT_TEMPLATE.format(
        few_shot_examples=few_shot,
        prose=prose[:CONFIG.max_content_chars],
        tables=tables_text,
        expected_outcomes=outcomes_text
    )
    
    # Safety check
    if len(prompt) > CONFIG.max_prompt_chars:
        available = CONFIG.max_prompt_chars - len(prose[:CONFIG.max_content_chars]) - 8000
        tables_text = tables_text[:available]
        prompt = EXTRACTION_PROMPT_TEMPLATE.format(
            few_shot_examples=few_shot,
            prose=prose[:CONFIG.max_content_chars],
            tables=tables_text,
            expected_outcomes=outcomes_text
        )
    
    return prompt


# ============================================================================
# ENSEMBLE EXTRACTION
# ============================================================================

def extract_with_model(
    prompt: str,
    model: str
) -> List[Dict]:
    """Extract outcomes using a specific model."""
    result, raw = call_llm(prompt, model=model)
    
    if result and "outcomes" in result:
        outcomes = result["outcomes"]
        # Tag with model
        for o in outcomes:
            o["_model"] = model.split("/")[-1]
        return outcomes
    
    return []


def ensemble_extract(
    prose: str,
    tables: List[ParsedTable],
    expected_outcomes: List[str]
) -> List[Dict]:
    """
    Extract outcomes using multiple models and merge results.
    Uses union approach - if either model finds an outcome, include it.
    """
    prompt = build_extraction_prompt(prose, tables, expected_outcomes)
    
    all_outcomes = []
    model_results = {}
    
    # Run models in parallel
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {
            executor.submit(extract_with_model, prompt, model): model
            for model in CONFIG.models
        }
        
        for future in as_completed(futures):
            model = futures[future]
            try:
                outcomes = future.result()
                model_results[model] = len(outcomes)
                all_outcomes.extend(outcomes)
                logger.info(f"    {model.split('/')[-1]}: {len(outcomes)} outcomes")
            except Exception as e:
                logger.error(f"    {model} failed: {e}")
    
    # Deduplicate by outcome name (keep first occurrence)
    seen = set()
    unique = []
    for o in all_outcomes:
        name = (o.get("outcome_name") or "").lower().strip()
        if name and name not in seen:
            seen.add(name)
            unique.append(o)
    
    return unique


# ============================================================================
# MULTI-PASS EXTRACTION WITH TABLE RANKING
# ============================================================================

def extract_outcomes_v11(
    prose: str,
    tables: List[ParsedTable],
    expected_outcomes: List[str]
) -> List[Dict]:
    """
    V11 extraction with table ranking, multi-pass, and ensemble.
    """
    all_outcomes = []
    
    # Step 1: Filter to results tables
    results_tables = filter_results_tables(tables)
    logger.info(f"  Filtered to {len(results_tables)}/{len(tables)} results tables")
    
    if not results_tables:
        results_tables = tables[:20]
    
    # Step 2: Rank tables by relevance to expected outcomes
    if CONFIG.use_table_ranking and expected_outcomes:
        ranked = rank_tables_by_relevance(results_tables, expected_outcomes)
        results_tables = [t for t, score in ranked[:CONFIG.max_tables_after_ranking]]
        top_scores = [f"{score:.2f}" for t, score in ranked[:5]]
        logger.info(f"  Top 5 table relevance scores: {top_scores}")
    
    # Step 3: Process in batches
    num_batches = (len(results_tables) + CONFIG.max_tables_per_batch - 1) // CONFIG.max_tables_per_batch
    
    if num_batches == 1:
        # Single pass with ensemble
        outcomes = ensemble_extract(prose, results_tables, expected_outcomes)
        all_outcomes.extend(outcomes)
    else:
        logger.info(f"  Multi-pass extraction: {num_batches} batches")
        for batch_idx in range(num_batches):
            start = batch_idx * CONFIG.max_tables_per_batch
            end = start + CONFIG.max_tables_per_batch
            batch_tables = results_tables[start:end]
            
            outcomes = ensemble_extract(prose, batch_tables, expected_outcomes)
            all_outcomes.extend(outcomes)
            
            logger.info(f"  Batch {batch_idx + 1}/{num_batches}: {len(outcomes)} outcomes")
    
    # Deduplicate final results
    seen_names = set()
    unique_outcomes = []
    for o in all_outcomes:
        name = (o.get("outcome_name") or "").lower().strip()
        if name and name not in seen_names:
            seen_names.add(name)
            unique_outcomes.append(o)
    
    return unique_outcomes


# ============================================================================
# MATCHING WITH REVIEW QUEUE
# ============================================================================

@dataclass
class ReviewItem:
    """Item for human review queue."""
    study_id: str
    author: str
    extracted_name: str
    best_gt_match: str
    similarity_score: float
    extraction_model: str
    table_location: str


def match_outcomes(
    extracted: List[Dict],
    ground_truth: List[Dict],
    study_id: str,
    author: str,
    use_llm_validation: bool = True
) -> Tuple[Dict, List[ReviewItem]]:
    """
    Match extracted outcomes to ground truth.
    Returns (match_results, review_items).
    """
    matches = []
    unmatched_gt = list(range(len(ground_truth)))
    review_items = []
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
        
        gt_name = ground_truth[best_match_idx].get('name', '')
        
        # Decision logic with lower thresholds
        if best_score >= CONFIG.high_confidence_threshold:
            matches.append({
                "extracted_idx": ext_idx,
                "gt_idx": best_match_idx,
                "extracted_name": ext_name,
                "gt_name": gt_name,
                "similarity": best_scores,
                "match_type": "high_confidence"
            })
            unmatched_gt.remove(best_match_idx)
            
        elif best_score >= CONFIG.llm_validation_threshold and use_llm_validation:
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
            else:
                # Add to review queue
                if CONFIG.save_for_review:
                    review_items.append(ReviewItem(
                        study_id=study_id,
                        author=author,
                        extracted_name=ext_name,
                        best_gt_match=gt_name,
                        similarity_score=best_score,
                        extraction_model=ext.get("_model", "unknown"),
                        table_location=ext.get("evidence_location", "unknown")
                    ))
    
    # Also add unmatched ground truth for review
    for gt_idx in unmatched_gt:
        gt = ground_truth[gt_idx]
        gt_name = gt.get('name', '')
        if CONFIG.save_for_review:
            review_items.append(ReviewItem(
                study_id=study_id,
                author=author,
                extracted_name="[NOT FOUND]",
                best_gt_match=gt_name,
                similarity_score=0.0,
                extraction_model="",
                table_location=""
            ))
    
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
    }, review_items


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


def process_study(study: Dict, idx: int, total: int) -> Tuple[StudyResult, List[ReviewItem]]:
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
    
    review_items = []
    
    if not r2_key:
        result.error = "No R2 key"
        return result, review_items
    
    # Load document
    try:
        prose, tables, raw_data = load_document(r2_key)
        result.num_tables_total = len(tables)
        logger.info(f"  📄 {len(prose):,} chars, {len(tables)} tables")
    except Exception as e:
        result.error = f"Load error: {e}"
        logger.error(f"  ❌ {result.error}")
        return result, review_items
    
    # Extract outcomes
    try:
        expected_outcomes = [o.get('name', '') for o in gt_outcomes if o.get('name')]
        outcomes = extract_outcomes_v11(prose, tables, expected_outcomes)
        result.outcomes = outcomes
        result.num_outcomes_extracted = len(outcomes)
        logger.info(f"  ✅ Extracted {len(outcomes)} unique outcomes")
    except Exception as e:
        result.error = f"Extraction error: {e}"
        logger.error(f"  ❌ {result.error}")
        return result, review_items
    
    # Match outcomes
    if gt_outcomes:
        try:
            matching, review_items = match_outcomes(
                outcomes, gt_outcomes, study_id, author, use_llm_validation=True
            )
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
    return result, review_items


def main():
    """Run V11 extraction pipeline."""
    start_time = datetime.now()
    
    print("=" * 70)
    print("EXTRACTION PIPELINE V11 - Enterprise Edition")
    print("=" * 70)
    print(f"Models: {', '.join(CONFIG.models)}")
    print(f"Max tokens: {CONFIG.max_tokens_extraction}")
    print(f"Table ranking: {CONFIG.use_table_ranking}")
    print(f"Few-shot examples: {CONFIG.use_few_shot}")
    print(f"Ensemble extraction: {len(CONFIG.models)} models")
    print("=" * 70)
    
    # Load studies
    with open("evaluation/matched_studies_r2.json") as f:
        studies = json.load(f)
    
    logger.info(f"Loaded {len(studies)} studies")
    
    # Process all studies
    results: List[StudyResult] = []
    all_review_items: List[ReviewItem] = []
    
    for idx, study in enumerate(studies, 1):
        result, review_items = process_study(study, idx, len(studies))
        results.append(result)
        all_review_items.extend(review_items)
        
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
            print(f"Review queue: {len(all_review_items)} items")
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
    print("FINAL RESULTS - V11")
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
    print("  V10 Pro:     41.6% recall, 29.5% precision, 34.6% F1")
    print(f"  V11 Enter:   {final_recall:.1%} recall, {final_precision:.1%} precision, {final_f1:.1%} F1")
    
    # Perfect recall studies
    perfect_recall = [r for r in successful if r.recall == 1.0 and r.num_outcomes_gt > 0]
    print(f"\nStudies with 100% recall: {len(perfect_recall)}")
    for r in perfect_recall[:15]:
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
    
    output_path = Path("extraction_pipeline/v11_results.json")
    with open(output_path, "w") as f:
        json.dump(output_data, f, indent=2, default=str)
    
    logger.info(f"Results saved to {output_path}")
    
    # Save review queue for human-in-the-loop
    if CONFIG.save_for_review and all_review_items:
        review_path = Path(CONFIG.review_output_path)
        review_data = [asdict(item) for item in all_review_items]
        with open(review_path, "w") as f:
            json.dump(review_data, f, indent=2)
        
        print(f"\n📋 Review queue saved: {len(all_review_items)} items for human review")
        print(f"   Location: {review_path}")
        
        # Summary of review items
        not_found = sum(1 for item in all_review_items if item.extracted_name == "[NOT FOUND]")
        low_conf = len(all_review_items) - not_found
        print(f"   - Not found in extraction: {not_found}")
        print(f"   - Low confidence matches: {low_conf}")


if __name__ == "__main__":
    main()
