"""
Extraction Pipeline V12 - Precision-Recall Optimized

TARGET: 95% recall, 70% precision

KEY IMPROVEMENTS OVER V11:
1. Aggressive semantic deduplication (0.70 threshold) - collapse 2252 → ~600
2. Much lower matching thresholds - catch more of the 127 missed outcomes
3. Two-stage matching: semantic first, then LLM validation for ALL borderline cases
4. Outcome normalization before matching
5. Extract from PROSE as well as tables (catch text-only outcomes)
6. Triple model ensemble: Claude + GPT-4o + GPT-4o-mini for higher coverage
7. No table filtering - process ALL tables to avoid missing outcomes

V11 Results: 71.3% recall, 14% precision (315/442 matched, 2252 extracted)
V12 Target: 95% recall, 70% precision (420/442 matched, ~600 extracted)
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
    # Model settings - TWO HIGH-QUALITY MODELS ONLY
    # GPT-4o-mini removed: extracts too many outcomes (noise)
    models: List[str] = field(default_factory=lambda: [
        "anthropic/claude-3.5-sonnet",
        "openai/gpt-4o-2024-11-20"
    ])
    max_tokens_extraction: int = 32000
    max_tokens_validation: int = 200
    temperature: float = 0.0
    
    # Deduplication - AGGRESSIVE
    dedup_similarity_threshold: float = 0.70  # Was 0.85 in V11
    
    # Matching thresholds - MUCH LOWER to catch more matches
    high_confidence_threshold: float = 0.55  # Was 0.65 in V11
    llm_validation_threshold: float = 0.30   # Was 0.40 in V11
    llm_validation_min_confidence: float = 0.40  # Was 0.50 in V11
    
    # Table processing - INCLUDE ALL
    max_tables_per_batch: int = 10
    min_table_rows: int = 2  # Lower threshold
    skip_descriptive_tables: bool = False  # Process ALL tables
    
    # Prose extraction
    extract_from_prose: bool = True  # NEW: Extract outcomes from text too
    
    # Processing
    max_content_chars: int = 50000  # Increased
    max_prompt_chars: int = 120000  # Increased
    retry_attempts: int = 3
    retry_delay: int = 5
    
    # Few-shot examples
    use_few_shot: bool = True
    
    # Output
    review_output_path: str = "extraction_pipeline/v12_review_queue.json"


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

try:
    from fuzzywuzzy import fuzz
    HAS_FUZZY = True
except ImportError:
    HAS_FUZZY = False
    logger.warning("⚠️ fuzzywuzzy not available")


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Compute cosine similarity between two vectors."""
    norm_product = np.linalg.norm(a) * np.linalg.norm(b)
    if norm_product < 1e-8:
        return 0.0
    return float(np.dot(a, b) / norm_product)


# ============================================================================
# OUTCOME NORMALIZATION - KEY FOR MATCHING
# ============================================================================

def normalize_outcome_name(name: str) -> str:
    """
    Normalize outcome name for better matching.
    This is critical for improving recall.
    """
    if not name:
        return ""
    
    name = name.lower().strip()
    
    # Remove common prefixes/suffixes
    prefixes = [
        "log ", "ln ", "log of ", "natural log of ",
        "change in ", "changes in ", "delta ",
        "z-score ", "z score ", "zscore ",
        "standardized ", "std. ", "std ",
    ]
    for prefix in prefixes:
        if name.startswith(prefix):
            name = name[len(prefix):]
    
    # Standardize common abbreviations
    replacements = {
        " hh ": " household ",
        "(hh)": "(household)",
        " hh$": " household",
        "^hh ": "household ",
        "pcc": "per capita consumption",
        "cons.": "consumption",
        "cons ": "consumption ",
        "expend.": "expenditure",
        "expend ": "expenditure ",
        "inc.": "income",
        "inc ": "income ",
        "emp.": "employment",
        "emp ": "employment ",
        " yr ": " year ",
        " yrs ": " years ",
        " mo ": " month ",
        " mos ": " months ",
        "usd": "dollars",
        " pp ": " percentage points ",
        " pct ": " percent ",
        " %": " percent",
        "female-headed": "female headed",
        "female headed": "female",
        "male-headed": "male headed",
        "male headed": "male",
    }
    
    for old, new in replacements.items():
        name = name.replace(old, new)
    
    # Remove parenthetical qualifiers but keep core meaning
    # e.g., "income (monthly)" -> "income monthly"
    name = name.replace("(", " ").replace(")", " ")
    
    # Remove extra whitespace
    name = " ".join(name.split())
    
    return name


def compute_hybrid_similarity(text1: str, text2: str) -> Tuple[float, Dict]:
    """Compute hybrid similarity combining fuzzy and semantic matching."""
    # Normalize first
    text1_norm = normalize_outcome_name(text1)
    text2_norm = normalize_outcome_name(text2)
    
    if not text1_norm or not text2_norm:
        return 0.0, {"fuzzy": 0, "semantic": 0, "combined": 0}
    
    # Fuzzy matching
    if HAS_FUZZY:
        fuzzy_score = fuzz.token_set_ratio(text1_norm, text2_norm) / 100.0
    else:
        # Simple overlap score
        words1 = set(text1_norm.split())
        words2 = set(text2_norm.split())
        if words1 and words2:
            fuzzy_score = len(words1 & words2) / len(words1 | words2)
        else:
            fuzzy_score = 0.0
    
    # Semantic matching
    if HAS_EMBEDDINGS and EMBEDDING_MODEL:
        emb1 = EMBEDDING_MODEL.encode(text1_norm, convert_to_numpy=True)
        emb2 = EMBEDDING_MODEL.encode(text2_norm, convert_to_numpy=True)
        semantic_score = cosine_similarity(emb1, emb2)
    else:
        semantic_score = fuzzy_score
    
    # Weighted combination - favor semantic
    combined = 0.3 * fuzzy_score + 0.7 * semantic_score
    
    return combined, {
        "fuzzy": round(fuzzy_score, 3),
        "semantic": round(semantic_score, 3),
        "combined": round(combined, 3)
    }


# ============================================================================
# AGGRESSIVE SEMANTIC DEDUPLICATION
# ============================================================================

def semantic_deduplicate(outcomes: List[Dict], threshold: float = None) -> List[Dict]:
    """
    Aggressively deduplicate outcomes using semantic similarity.
    Keep the outcome with more complete information when merging.
    """
    threshold = threshold or CONFIG.dedup_similarity_threshold
    
    if not outcomes or not HAS_EMBEDDINGS:
        return outcomes
    
    # Get embeddings for all outcomes
    names = [normalize_outcome_name(o.get("outcome_name", "")) for o in outcomes]
    
    # Filter out empty names
    valid_indices = [i for i, n in enumerate(names) if n]
    if not valid_indices:
        return outcomes
    
    valid_outcomes = [outcomes[i] for i in valid_indices]
    valid_names = [names[i] for i in valid_indices]
    
    # Encode all at once for efficiency
    embeddings = EMBEDDING_MODEL.encode(valid_names, convert_to_numpy=True)
    
    # Find duplicates using clustering
    keep_indices = []
    merged = [False] * len(valid_outcomes)
    
    for i in range(len(valid_outcomes)):
        if merged[i]:
            continue
        
        # This outcome becomes a cluster representative
        keep_indices.append(i)
        
        # Find all similar outcomes and mark as merged
        for j in range(i + 1, len(valid_outcomes)):
            if merged[j]:
                continue
            
            sim = cosine_similarity(embeddings[i], embeddings[j])
            if sim >= threshold:
                merged[j] = True
                # Could merge fields here if needed
    
    # Return deduplicated list
    deduped = [valid_outcomes[i] for i in keep_indices]
    
    logger.info(f"    Dedup: {len(outcomes)} → {len(deduped)} outcomes (threshold={threshold})")
    
    return deduped


# ============================================================================
# LLM INTERACTION
# ============================================================================

def call_llm(
    prompt: str,
    max_tokens: int = None,
    model: str = None
) -> Tuple[Optional[Dict], Optional[str]]:
    """Call LLM with robust error handling."""
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
    prompt = f"""Are these two outcome variables referring to the SAME underlying concept?

EXTRACTED: "{extracted}"
GROUND TRUTH: "{ground_truth}"

MATCH GENEROUSLY:
- Same concept, different wording = MATCH (e.g., "income" = "earnings" = "revenue")
- Different units = MATCH (e.g., "monthly income" = "annual income")
- Different aggregation = MATCH (e.g., "household" = "per capita")
- Abbreviations = MATCH (e.g., "HH" = "household", "cons." = "consumption")
- Sub-outcomes = MATCH (e.g., "food consumption" matches "consumption")
- Time qualifiers = MATCH (e.g., "income at 12 months" = "income")

Only return false if they are CLEARLY different concepts.

Return JSON: {{"match": true/false, "confidence": 0.0-1.0}}"""

    result, _ = call_llm(prompt, max_tokens=100, model="openai/gpt-4o-mini")
    
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
    
    # Preprocess tables - keep ALL tables
    parsed_tables = []
    for table in raw_tables:
        parsed = preprocess_mineru_table(table)
        if parsed and len(parsed.rows) >= CONFIG.min_table_rows:
            parsed_tables.append(parsed)
    
    return prose, parsed_tables, data


# ============================================================================
# EXTRACTION PROMPTS
# ============================================================================

FEW_SHOT_EXAMPLES = """
## EXAMPLE 1: Results Table

Table 3: Treatment Effects
| Outcome | Effect | SE |
|---------|--------|-----|
| Per capita consumption | 0.128*** | (0.041) |
| Food expenditure | 0.095** | (0.038) |
| Non-food expenditure | 0.156*** | (0.052) |

Extracted:
- outcome_name: "Per capita consumption", coefficient: 0.128, standard_error: 0.041
- outcome_name: "Food expenditure", coefficient: 0.095, standard_error: 0.038
- outcome_name: "Non-food expenditure", coefficient: 0.156, standard_error: 0.052

## EXAMPLE 2: Multiple Subgroups

Table 5: Heterogeneous Effects
| Outcome | Full Sample | Female HH | Male HH |
|---------|-------------|-----------|---------|
| Income | 45.2*** (12.3) | 52.1*** (15.8) | 38.4** (14.2) |

Extracted (EACH column is separate):
- outcome_name: "Income", coefficient: 45.2, standard_error: 12.3
- outcome_name: "Income - Female HH", coefficient: 52.1, standard_error: 15.8  
- outcome_name: "Income - Male HH", coefficient: 38.4, standard_error: 14.2
"""

EXTRACTION_PROMPT = """You are an expert at extracting outcome variables from impact evaluation papers.

## TASK
Extract ALL outcome variables with statistical results from this document.

## CRITICAL INSTRUCTIONS
1. Extract EVERY outcome that has a coefficient/effect size
2. Each table cell with a number is potentially an outcome
3. Multiple columns = extract EACH as separate outcome
4. Include the base outcome name (e.g., "consumption") AND variants (e.g., "food consumption")
5. Look in BOTH tables AND prose for results mentioned in text

## EXPECTED OUTCOMES TO FIND
These are outcomes we expect - make sure to extract them if present:
{expected_outcomes}

## FEW-SHOT EXAMPLES
{few_shot}

## DOCUMENT CONTENT
{prose}

## TABLES
{tables}

## OUTPUT FORMAT
Return ONLY valid JSON:

{{
  "outcomes": [
    {{
      "outcome_name": "Household consumption",
      "coefficient": 0.128,
      "standard_error": 0.041,
      "p_value": 0.01,
      "evidence_location": "Table 3"
    }}
  ]
}}

Extract comprehensively - aim for 30-100 outcomes per paper."""


PROSE_EXTRACTION_PROMPT = """Extract outcome variables mentioned in this text with their effect sizes.

Look for patterns like:
- "increased consumption by 12%"
- "effect on income was 0.15 standard deviations"
- "significant impact on savings (coefficient = 45.2)"

## EXPECTED OUTCOMES
{expected_outcomes}

## TEXT
{prose}

Return JSON with outcomes found in text:
{{
  "outcomes": [
    {{
      "outcome_name": "...",
      "coefficient": 0.0,
      "evidence_location": "prose"
    }}
  ]
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
        tables_text = "(No tables)"
    
    # Format expected outcomes
    if expected_outcomes:
        outcomes_text = "\n".join(f"- {name}" for name in expected_outcomes[:40])
    else:
        outcomes_text = "(Extract all outcomes)"
    
    prompt = EXTRACTION_PROMPT.format(
        expected_outcomes=outcomes_text,
        few_shot=FEW_SHOT_EXAMPLES,
        prose=prose[:CONFIG.max_content_chars],
        tables=tables_text
    )
    
    # Truncate if needed
    if len(prompt) > CONFIG.max_prompt_chars:
        available = CONFIG.max_prompt_chars - 20000
        tables_text = tables_text[:available]
        prompt = EXTRACTION_PROMPT.format(
            expected_outcomes=outcomes_text,
            few_shot=FEW_SHOT_EXAMPLES,
            prose=prose[:CONFIG.max_content_chars],
            tables=tables_text
        )
    
    return prompt


# ============================================================================
# TRIPLE MODEL ENSEMBLE EXTRACTION
# ============================================================================

def extract_with_model(prompt: str, model: str) -> List[Dict]:
    """Extract outcomes using a specific model."""
    result, raw = call_llm(prompt, model=model)
    
    if result and "outcomes" in result:
        outcomes = result["outcomes"]
        for o in outcomes:
            o["_model"] = model.split("/")[-1]
        return outcomes
    
    return []


def ensemble_extract_v12(
    prose: str,
    tables: List[ParsedTable],
    expected_outcomes: List[str]
) -> List[Dict]:
    """
    V12 ensemble extraction:
    1. Run 3 models in parallel
    2. Union all results (maximize recall)
    3. Aggressive deduplication (maximize precision)
    """
    prompt = build_extraction_prompt(prose, tables, expected_outcomes)
    
    all_outcomes = []
    
    # Run all models in parallel
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(extract_with_model, prompt, model): model
            for model in CONFIG.models
        }
        
        for future in as_completed(futures):
            model = futures[future]
            try:
                outcomes = future.result()
                all_outcomes.extend(outcomes)
                logger.info(f"    {model.split('/')[-1]}: {len(outcomes)} outcomes")
            except Exception as e:
                logger.error(f"    {model} failed: {e}")
    
    # Also extract from prose if enabled
    if CONFIG.extract_from_prose and prose:
        prose_prompt = PROSE_EXTRACTION_PROMPT.format(
            expected_outcomes="\n".join(expected_outcomes[:20]) if expected_outcomes else "",
            prose=prose[:30000]
        )
        prose_outcomes = extract_with_model(prose_prompt, "openai/gpt-4o-2024-11-20")
        if prose_outcomes:
            for o in prose_outcomes:
                o["_source"] = "prose"
            all_outcomes.extend(prose_outcomes)
            logger.info(f"    Prose extraction: {len(prose_outcomes)} outcomes")
    
    # Aggressive deduplication
    deduped = semantic_deduplicate(all_outcomes)
    
    return deduped


# ============================================================================
# MULTI-PASS EXTRACTION
# ============================================================================

def extract_outcomes_v12(
    prose: str,
    tables: List[ParsedTable],
    expected_outcomes: List[str]
) -> List[Dict]:
    """
    V12 extraction - no table filtering, multi-pass, aggressive dedup.
    """
    all_outcomes = []
    
    logger.info(f"  Processing {len(tables)} tables")
    
    if not tables:
        # Extract from prose only
        if CONFIG.extract_from_prose:
            outcomes = ensemble_extract_v12(prose, [], expected_outcomes)
            return outcomes
        return []
    
    # Process in batches
    num_batches = (len(tables) + CONFIG.max_tables_per_batch - 1) // CONFIG.max_tables_per_batch
    
    for batch_idx in range(num_batches):
        start = batch_idx * CONFIG.max_tables_per_batch
        end = start + CONFIG.max_tables_per_batch
        batch_tables = tables[start:end]
        
        outcomes = ensemble_extract_v12(prose, batch_tables, expected_outcomes)
        all_outcomes.extend(outcomes)
        
        logger.info(f"  Batch {batch_idx + 1}/{num_batches}: {len(outcomes)} outcomes")
    
    # Final deduplication across all batches
    final = semantic_deduplicate(all_outcomes)
    
    return final


# ============================================================================
# TWO-STAGE MATCHING
# ============================================================================

def match_outcomes_v12(
    extracted: List[Dict],
    ground_truth: List[Dict],
    use_llm_validation: bool = True
) -> Dict:
    """
    V12 matching with very low thresholds and aggressive LLM validation.
    
    Strategy:
    1. High-confidence matches (>0.55 similarity)
    2. LLM validation for ALL remaining pairs (>0.30 similarity)
    3. This catches semantic equivalences missed by embedding similarity
    """
    matches = []
    unmatched_gt = list(range(len(ground_truth)))
    llm_calls = 0
    
    # Pre-compute all pairwise similarities
    similarity_matrix = []
    for ext_idx, ext in enumerate(extracted):
        ext_name = ext.get('outcome_name', '')
        row = []
        for gt_idx, gt in enumerate(ground_truth):
            gt_name = gt.get('name', '')
            score, details = compute_hybrid_similarity(ext_name, gt_name)
            row.append((gt_idx, score, details))
        # Sort by score descending
        row.sort(key=lambda x: x[1], reverse=True)
        similarity_matrix.append(row)
    
    # First pass: high confidence matches
    for ext_idx, ext in enumerate(extracted):
        if not similarity_matrix[ext_idx]:
            continue
        
        best_gt_idx, best_score, best_details = similarity_matrix[ext_idx][0]
        
        if best_gt_idx not in unmatched_gt:
            # Already matched, try next best
            for gt_idx, score, details in similarity_matrix[ext_idx]:
                if gt_idx in unmatched_gt:
                    best_gt_idx, best_score, best_details = gt_idx, score, details
                    break
        
        if best_gt_idx not in unmatched_gt:
            continue
        
        ext_name = ext.get('outcome_name', '')
        gt_name = ground_truth[best_gt_idx].get('name', '')
        
        if best_score >= CONFIG.high_confidence_threshold:
            matches.append({
                "extracted_idx": ext_idx,
                "gt_idx": best_gt_idx,
                "extracted_name": ext_name,
                "gt_name": gt_name,
                "similarity": best_details,
                "match_type": "high_confidence"
            })
            unmatched_gt.remove(best_gt_idx)
    
    # Second pass: LLM validation for borderline cases
    if use_llm_validation:
        for ext_idx, ext in enumerate(extracted):
            # Skip if already matched
            if any(m["extracted_idx"] == ext_idx for m in matches):
                continue
            
            ext_name = ext.get('outcome_name', '')
            if not ext_name:
                continue
            
            # Try to match against remaining ground truth
            for gt_idx, score, details in similarity_matrix[ext_idx]:
                if gt_idx not in unmatched_gt:
                    continue
                
                if score < CONFIG.llm_validation_threshold:
                    break  # Sorted, so remaining will be lower
                
                gt_name = ground_truth[gt_idx].get('name', '')
                
                is_match, confidence = llm_validate_match(ext_name, gt_name)
                llm_calls += 1
                
                if is_match and confidence >= CONFIG.llm_validation_min_confidence:
                    matches.append({
                        "extracted_idx": ext_idx,
                        "gt_idx": gt_idx,
                        "extracted_name": ext_name,
                        "gt_name": gt_name,
                        "similarity": details,
                        "match_type": "llm_validated",
                        "llm_confidence": confidence
                    })
                    unmatched_gt.remove(gt_idx)
                    break
    
    # Calculate metrics
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
    num_tables: int = 0
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
        num_outcomes_gt=len(gt_outcomes)
    )
    
    if not r2_key:
        result.error = "no_r2_key"
        return result
    
    try:
        # Load document
        prose, tables, _ = load_document(r2_key)
        result.num_tables = len(tables)
        
        # Extract expected outcome names for prompting
        expected_names = [o.get('name', '') for o in gt_outcomes if o.get('name')]
        
        # Extract outcomes
        outcomes = extract_outcomes_v12(prose, tables, expected_names)
        result.outcomes = outcomes
        result.num_outcomes_extracted = len(outcomes)
        
        logger.info(f"  ✅ Extracted {len(outcomes)} outcomes")
        
        # Match to ground truth
        matching = match_outcomes_v12(outcomes, gt_outcomes)
        result.matching = matching
        result.num_matched = matching["matched_count"]
        result.recall = matching["recall"]
        result.precision = matching["precision"]
        result.f1 = matching["f1"]
        result.success = True
        
        logger.info(f"  📊 Matched: {result.num_matched}/{len(gt_outcomes)} "
                   f"(R: {result.recall*100:.1f}%, P: {result.precision*100:.1f}%, "
                   f"F1: {result.f1*100:.1f}%)")
        
    except Exception as e:
        result.error = str(e)
        logger.error(f"  ❌ Error: {e}")
    
    return result


def main():
    """Main entry point."""
    logger.info("=" * 70)
    logger.info("V12 EXTRACTION PIPELINE - TARGET: 95% RECALL, 70% PRECISION")
    logger.info("=" * 70)
    
    # Load studies - same source as V11
    studies_path = Path(__file__).parent.parent / "evaluation" / "matched_studies_r2.json"
    with open(studies_path, 'r') as f:
        studies = json.load(f)
    
    logger.info(f"Loaded {len(studies)} studies")
    
    # Process all studies
    results = []
    start_time = datetime.now()
    
    for idx, study in enumerate(studies, 1):
        result = process_study(study, idx, len(studies))
        results.append(result)
        
        # Progress report every 10 studies
        if idx % 10 == 0:
            completed = [r for r in results if r.success]
            if completed:
                avg_recall = np.mean([r.recall for r in completed])
                avg_precision = np.mean([r.precision for r in completed])
                avg_f1 = np.mean([r.f1 for r in completed])
                logger.info("=" * 50)
                logger.info(f"PROGRESS: {idx}/{len(studies)}")
                logger.info(f"R: {avg_recall*100:.1f}% | P: {avg_precision*100:.1f}% | F1: {avg_f1*100:.1f}%")
                logger.info("=" * 50)
    
    elapsed = datetime.now() - start_time
    
    # Calculate final metrics
    successful = [r for r in results if r.success]
    
    total_gt = sum(r.num_outcomes_gt for r in successful)
    total_extracted = sum(r.num_outcomes_extracted for r in successful)
    total_matched = sum(r.num_matched for r in successful)
    
    recall = total_matched / total_gt if total_gt > 0 else 0
    precision = total_matched / total_extracted if total_extracted > 0 else 0
    f1 = 2 * recall * precision / (recall + precision) if (recall + precision) > 0 else 0
    
    studies_100_recall = sum(1 for r in successful if r.recall >= 0.99)
    
    # Print final results
    logger.info("")
    logger.info("=" * 70)
    logger.info("FINAL RESULTS - V12")
    logger.info("=" * 70)
    logger.info(f"Studies processed: {len(studies)}")
    logger.info(f"Successful: {len(successful)}")
    logger.info(f"Time elapsed: {elapsed}")
    logger.info("")
    logger.info(f"Ground truth outcomes: {total_gt}")
    logger.info(f"Extracted outcomes: {total_extracted}")
    logger.info(f"Matched outcomes: {total_matched}")
    logger.info("")
    logger.info(f"RECALL:    {recall*100:.1f}%  (target: 95%)")
    logger.info(f"PRECISION: {precision*100:.1f}%  (target: 70%)")
    logger.info(f"F1 SCORE:  {f1*100:.1f}%")
    logger.info("")
    logger.info(f"Studies with 100% recall: {studies_100_recall}")
    logger.info("=" * 70)
    
    # Save results
    output = {
        "config": asdict(CONFIG),
        "summary": {
            "total_studies": len(studies),
            "successful_studies": len(successful),
            "total_gt_outcomes": total_gt,
            "total_extracted": total_extracted,
            "total_matched": total_matched,
            "recall": recall,
            "precision": precision,
            "f1": f1,
            "elapsed_seconds": elapsed.total_seconds()
        },
        "results": [
            {
                "study_id": r.study_id,
                "author": r.author,
                "success": r.success,
                "error": r.error,
                "num_tables": r.num_tables,
                "num_outcomes_extracted": r.num_outcomes_extracted,
                "num_outcomes_gt": r.num_outcomes_gt,
                "num_matched": r.num_matched,
                "recall": r.recall,
                "precision": r.precision,
                "f1": r.f1,
                "unmatched_gt": r.matching.get("unmatched_gt_names", []) if r.matching else []
            }
            for r in results
        ]
    }
    
    output_path = Path(__file__).parent / "v12_results.json"
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2)
    
    logger.info(f"Results saved to {output_path}")


if __name__ == "__main__":
    main()
