"""
V14 Extraction Pipeline - Model Comparison & Traceability

KEY IMPROVEMENTS:
1. Track source_model for each extracted outcome
2. Add literal_text field showing exact source text
3. Run models separately to compare their performance
4. Improved matching for generic GT names (Assets, Income, Expenditure)
5. Substring/containment matching

This version runs Claude and GPT separately, tracks their output, 
then compares which model performs better.
"""

import os
import re
import json
import boto3
import requests
import numpy as np
from typing import Dict, List, Optional, Tuple, Set
from datetime import datetime
from dotenv import load_dotenv
import time
import logging
from dataclasses import dataclass, field
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
    """Pipeline configuration for V14."""
    # Models to compare
    models: List[str] = field(default_factory=lambda: [
        "anthropic/claude-3.5-sonnet",
        "openai/gpt-4o-2024-11-20"
    ])
    max_tokens_extraction: int = 32000
    max_tokens_validation: int = 200
    temperature: float = 0.0
    
    # Deduplication - keep most variants
    dedup_similarity_threshold: float = 0.55
    
    # Matching thresholds
    exact_match_threshold: float = 0.90
    high_confidence_threshold: float = 0.45
    llm_validation_threshold: float = 0.20
    llm_validation_min_confidence: float = 0.35
    
    # V14 NEW: Enable containment matching for generic GT
    enable_containment_matching: bool = True
    containment_min_length: int = 4  # Min chars for containment check
    
    # Table processing
    max_tables_per_batch: int = 10
    min_table_rows: int = 2
    
    # Processing
    max_content_chars: int = 50000
    max_prompt_chars: int = 120000
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

try:
    from fuzzywuzzy import fuzz
    HAS_FUZZY = True
except ImportError:
    HAS_FUZZY = False


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    norm_product = np.linalg.norm(a) * np.linalg.norm(b)
    if norm_product < 1e-8:
        return 0.0
    return float(np.dot(a, b) / norm_product)


def normalize_outcome_name(name: str) -> str:
    """Normalize outcome name for better matching."""
    if not name:
        return ""
    
    name = name.lower().strip()
    
    # Standardize common abbreviations
    replacements = {
        " hh ": " household ",
        "pcc": "per capita consumption",
        "cons.": "consumption",
        "expend.": "expenditure",
        "usd": "dollars",
        " pp ": " percentage points ",
    }
    
    for old, new in replacements.items():
        name = name.replace(old, new)
    
    name = " ".join(name.split())
    return name


def compute_hybrid_similarity(text1: str, text2: str) -> Tuple[float, Dict]:
    """Compute hybrid similarity with containment check."""
    text1_norm = normalize_outcome_name(text1)
    text2_norm = normalize_outcome_name(text2)
    
    if not text1_norm or not text2_norm:
        return 0.0, {"fuzzy": 0, "semantic": 0, "combined": 0, "containment": False}
    
    # Check containment for generic names
    containment = False
    if CONFIG.enable_containment_matching:
        if len(text1_norm) >= CONFIG.containment_min_length and len(text2_norm) >= CONFIG.containment_min_length:
            # Check if one is contained in the other
            if text1_norm in text2_norm or text2_norm in text1_norm:
                containment = True
    
    # Fuzzy matching
    if HAS_FUZZY:
        fuzzy_score = fuzz.token_set_ratio(text1_norm, text2_norm) / 100.0
    else:
        words1 = set(text1_norm.split())
        words2 = set(text2_norm.split())
        fuzzy_score = len(words1 & words2) / len(words1 | words2) if words1 and words2 else 0.0
    
    # Semantic matching
    if HAS_EMBEDDINGS and EMBEDDING_MODEL:
        emb1 = EMBEDDING_MODEL.encode(text1_norm, convert_to_numpy=True)
        emb2 = EMBEDDING_MODEL.encode(text2_norm, convert_to_numpy=True)
        semantic_score = cosine_similarity(emb1, emb2)
    else:
        semantic_score = fuzzy_score
    
    # Combined score with containment boost
    combined = 0.3 * fuzzy_score + 0.7 * semantic_score
    if containment:
        combined = max(combined, 0.85)  # Boost for containment
    
    return combined, {
        "fuzzy": round(fuzzy_score, 3),
        "semantic": round(semantic_score, 3),
        "combined": round(combined, 3),
        "containment": containment
    }


def semantic_deduplicate(outcomes: List[Dict], threshold: float = None) -> List[Dict]:
    """Deduplicate outcomes using semantic similarity."""
    threshold = threshold or CONFIG.dedup_similarity_threshold
    
    if not outcomes or not HAS_EMBEDDINGS:
        return outcomes
    
    names = [normalize_outcome_name(o.get("outcome_name", "")) for o in outcomes]
    valid_indices = [i for i, n in enumerate(names) if n]
    if not valid_indices:
        return outcomes
    
    valid_outcomes = [outcomes[i] for i in valid_indices]
    valid_names = [names[i] for i in valid_indices]
    
    embeddings = EMBEDDING_MODEL.encode(valid_names, convert_to_numpy=True)
    
    keep_indices = []
    merged = [False] * len(valid_outcomes)
    
    for i in range(len(valid_outcomes)):
        if merged[i]:
            continue
        keep_indices.append(i)
        
        for j in range(i + 1, len(valid_outcomes)):
            if merged[j]:
                continue
            sim = cosine_similarity(embeddings[i], embeddings[j])
            len_ratio = min(len(valid_names[i]), len(valid_names[j])) / max(len(valid_names[i]), len(valid_names[j]), 1)
            if sim >= threshold and len_ratio >= 0.7:
                merged[j] = True
    
    return [valid_outcomes[i] for i in keep_indices]


# ============================================================================
# EXTRACTION PROMPT WITH LITERAL TEXT REQUIREMENT
# ============================================================================

EXTRACTION_PROMPT = """You are an expert at extracting outcome variables from impact evaluation papers.

## TASK
Extract ALL outcome variables with their statistical results from the provided tables.

## CRITICAL: For EACH outcome you extract, you MUST provide:
1. outcome_name: The name of the outcome variable
2. literal_text: The EXACT text from the table/document where this outcome appears (copy verbatim)
3. table_source: Which table it came from
4. coefficient: The effect size/coefficient if available
5. standard_error: The SE if available

## RULES
1. Extract EVERY outcome that has a coefficient/effect size
2. Multiple columns = extract EACH as separate outcome
3. Include the base outcome AND variants (e.g., "consumption" AND "food consumption")
4. The literal_text field should be the exact row/cell text, not paraphrased

## TABLES TO ANALYZE:
{tables}

## OUTPUT FORMAT
Return ONLY valid JSON:
{{
  "outcomes": [
    {{
      "outcome_name": "Household consumption",
      "literal_text": "Household consumption | 0.128*** | (0.041) | 1,245",
      "table_source": "Table 3",
      "coefficient": 0.128,
      "standard_error": 0.041
    }}
  ]
}}
"""


def call_llm(model: str, prompt: str, max_tokens: int = None) -> Optional[str]:
    """Call LLM via OpenRouter."""
    max_tokens = max_tokens or CONFIG.max_tokens_extraction
    
    for attempt in range(CONFIG.retry_attempts):
        try:
            response = SESSION.post(
                "https://openrouter.ai/api/v1/chat/completions",
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": max_tokens,
                    "temperature": CONFIG.temperature,
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                return data["choices"][0]["message"]["content"]
            elif response.status_code == 429:
                time.sleep(CONFIG.retry_delay * (attempt + 1))
            else:
                logger.error(f"API error: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            if attempt < CONFIG.retry_attempts - 1:
                time.sleep(CONFIG.retry_delay)
    
    return None


def parse_json_response(response: str) -> List[Dict]:
    """Parse JSON from LLM response."""
    if not response:
        return []
    
    response = re.sub(r'```json\s*', '', response)
    response = re.sub(r'```\s*', '', response)
    response = response.strip()
    
    try:
        data = json.loads(response)
        if isinstance(data, dict) and "outcomes" in data:
            return data["outcomes"]
        elif isinstance(data, list):
            return data
    except json.JSONDecodeError:
        match = re.search(r'\{[\s\S]*"outcomes"[\s\S]*\}', response)
        if match:
            try:
                data = json.loads(match.group())
                return data.get("outcomes", [])
            except:
                pass
    
    return []


def extract_outcomes_single_model(tables: List[Dict], model: str) -> List[Dict]:
    """Extract outcomes using a single model, tracking source."""
    if not tables:
        return []
    
    # Build table content
    table_content = []
    for table in tables:
        table_id = table.get("table_id", "Table")
        content = table.get("content", "")
        if content:
            table_content.append(f"\n### {table_id}\n{content[:8000]}")
    
    if not table_content:
        return []
    
    prompt = EXTRACTION_PROMPT.format(tables="\n".join(table_content))
    
    if len(prompt) > CONFIG.max_prompt_chars:
        prompt = prompt[:CONFIG.max_prompt_chars]
    
    response = call_llm(model, prompt)
    outcomes = parse_json_response(response)
    
    # Add source model to each outcome
    model_short = model.split('/')[-1]
    for o in outcomes:
        o['source_model'] = model_short
    
    return outcomes


# ============================================================================
# R2 DATA LOADING
# ============================================================================

def get_r2_client():
    return boto3.client(
        's3',
        endpoint_url=f'https://{CLOUDFLARE_ACCOUNT_ID}.r2.cloudflarestorage.com',
        aws_access_key_id=R2_ACCESS_KEY,
        aws_secret_access_key=R2_SECRET_KEY
    )


def load_document(r2_key: str) -> Tuple[str, List[Dict], Dict]:
    """Load document from R2."""
    try:
        client = get_r2_client()
        response = client.get_object(Bucket=R2_BUCKET, Key=r2_key)
        content = response['Body'].read()
        
        try:
            data = json.loads(content.decode('utf-8'))
        except UnicodeDecodeError:
            data = json.loads(content.decode('latin-1'))
        
        prose = data.get("content", "")
        raw_tables = data.get("tables", [])
        
        parsed_tables = []
        for idx, table in enumerate(raw_tables):
            parsed = preprocess_mineru_table(table)
            if parsed and len(parsed.rows) >= CONFIG.min_table_rows:
                table_dict = {
                    "table_id": f"Table {idx + 1}",
                    "content": parsed.to_markdown() if hasattr(parsed, 'to_markdown') else str(parsed),
                    "parsed": parsed
                }
                parsed_tables.append(table_dict)
        
        return prose, parsed_tables, data
        
    except Exception as e:
        logger.error(f"Failed to load {r2_key}: {e}")
        return "", [], {}


# ============================================================================
# MATCHING WITH TRACEABILITY
# ============================================================================

def match_outcomes_v14(
    extracted: List[Dict],
    ground_truth: List[Dict],
    use_llm_validation: bool = True
) -> Dict:
    """Match outcomes with full traceability."""
    matches = []
    unmatched_gt = list(range(len(ground_truth)))
    unmatched_ext = list(range(len(extracted)))
    
    # Pre-compute similarities
    similarity_matrix = {}
    for ext_idx in range(len(extracted)):
        ext_name = extracted[ext_idx].get('outcome_name', '')
        for gt_idx in range(len(ground_truth)):
            gt_name = ground_truth[gt_idx].get('name', '')
            score, details = compute_hybrid_similarity(ext_name, gt_name)
            similarity_matrix[(ext_idx, gt_idx)] = (score, details)
    
    def record_match(ext_idx: int, gt_idx: int, match_type: str, llm_conf: float = None):
        if gt_idx not in unmatched_gt or ext_idx not in unmatched_ext:
            return False
        
        ext_outcome = extracted[ext_idx]
        gt_outcome = ground_truth[gt_idx]
        score, details = similarity_matrix[(ext_idx, gt_idx)]
        
        match_record = {
            "extracted_idx": ext_idx,
            "gt_idx": gt_idx,
            "extracted_name": ext_outcome.get('outcome_name', ''),
            "gt_name": gt_outcome.get('name', ''),
            "literal_text": ext_outcome.get('literal_text', ''),  # V14: Include literal text
            "source_model": ext_outcome.get('source_model', 'unknown'),  # V14: Include source model
            "table_source": ext_outcome.get('table_source', ''),
            "similarity": details,
            "match_type": match_type
        }
        if llm_conf is not None:
            match_record["llm_confidence"] = llm_conf
        
        matches.append(match_record)
        unmatched_gt.remove(gt_idx)
        unmatched_ext.remove(ext_idx)
        return True
    
    # Pass 1: Exact/containment matches
    for ext_idx in list(unmatched_ext):
        best_gt, best_score, best_details = None, 0, {}
        for gt_idx in unmatched_gt:
            score, details = similarity_matrix[(ext_idx, gt_idx)]
            # Boost score if containment match
            if details.get('containment'):
                score = max(score, 0.85)
            if score > best_score:
                best_score = score
                best_gt = gt_idx
                best_details = details
        
        if best_gt is not None and best_score >= CONFIG.exact_match_threshold:
            match_type = "containment" if best_details.get('containment') else "exact"
            record_match(ext_idx, best_gt, match_type)
    
    # Pass 2: High-confidence semantic
    for ext_idx in list(unmatched_ext):
        best_gt, best_score = None, 0
        for gt_idx in unmatched_gt:
            score, details = similarity_matrix[(ext_idx, gt_idx)]
            if details.get('containment'):
                score = max(score, 0.85)
            if score > best_score:
                best_score = score
                best_gt = gt_idx
        
        if best_gt is not None and best_score >= CONFIG.high_confidence_threshold:
            record_match(ext_idx, best_gt, "high_confidence")
    
    # Pass 3: LLM validation for remaining
    if use_llm_validation:
        candidates = []
        for ext_idx in unmatched_ext:
            for gt_idx in unmatched_gt:
                score, details = similarity_matrix[(ext_idx, gt_idx)]
                if score >= CONFIG.llm_validation_threshold or details.get('containment'):
                    candidates.append((ext_idx, gt_idx, score, details))
        
        candidates.sort(key=lambda x: x[2], reverse=True)
        
        for ext_idx, gt_idx, score, details in candidates[:50]:  # Limit LLM calls
            if gt_idx not in unmatched_gt or ext_idx not in unmatched_ext:
                continue
            
            ext_name = extracted[ext_idx].get('outcome_name', '')
            gt_name = ground_truth[gt_idx].get('name', '')
            
            # Simple LLM validation
            is_match, confidence = llm_validate_match(ext_name, gt_name)
            
            if is_match and confidence >= CONFIG.llm_validation_min_confidence:
                record_match(ext_idx, gt_idx, "llm_validated", confidence)
    
    # Calculate metrics
    recall = len(matches) / len(ground_truth) if ground_truth else 0
    precision = len(matches) / len(extracted) if extracted else 0
    f1 = 2 * recall * precision / (recall + precision) if (recall + precision) > 0 else 0
    
    return {
        "matches": matches,
        "recall": recall,
        "precision": precision,
        "f1": f1,
        "n_matched": len(matches),
        "n_extracted": len(extracted),
        "n_ground_truth": len(ground_truth),
        "unmatched_gt_indices": unmatched_gt
    }


def llm_validate_match(extracted_name: str, gt_name: str) -> Tuple[bool, float]:
    """Use LLM to validate match."""
    prompt = f"""Do these outcome names refer to the same concept?

Extracted: "{extracted_name}"
Ground Truth: "{gt_name}"

Consider a match if:
- Same underlying concept (even with different wording)
- One is subset/variant of other
- Generic name matches specific variant (e.g., "Assets" matches "Agricultural assets")

JSON only: {{"match": true/false, "confidence": 0.0-1.0}}"""
    
    response = call_llm("openai/gpt-4o-mini", prompt, max_tokens=100)
    
    if not response:
        return False, 0.0
    
    try:
        response = re.sub(r'```json\s*', '', response)
        response = re.sub(r'```\s*', '', response)
        data = json.loads(response.strip())
        return data.get("match", False), data.get("confidence", 0.0)
    except:
        if '"match": true' in response.lower():
            return True, 0.7
        return False, 0.0


# ============================================================================
# MAIN PIPELINE WITH MODEL COMPARISON
# ============================================================================

def process_study_v14(study: Dict, idx: int, total: int) -> Dict:
    """Process study with separate model tracking."""
    study_id = study.get('study_id', 'unknown')
    gt_data = study.get('ground_truth', {})
    author = gt_data.get('author', 'Unknown')
    gt_outcomes = gt_data.get('outcomes', [])
    r2_key = study.get('r2_key')
    
    logger.info(f"[{idx}/{total}] {author} - {len(gt_outcomes)} GT outcomes")
    
    result = {
        "study_id": study_id,
        "author": author,
        "success": False,
        "n_gt_outcomes": len(gt_outcomes),
        "model_results": {}
    }
    
    if not r2_key:
        result["error"] = "no_r2_key"
        return result
    
    try:
        prose, tables, _ = load_document(r2_key)
        result["n_tables"] = len(tables)
        
        if not tables:
            result["error"] = "no_tables"
            return result
        
        # Extract with each model SEPARATELY
        model_outcomes = {}
        for model in CONFIG.models:
            model_short = model.split('/')[-1]
            logger.info(f"  Extracting with {model_short}...")
            
            outcomes = []
            num_batches = (len(tables) + CONFIG.max_tables_per_batch - 1) // CONFIG.max_tables_per_batch
            
            for batch_idx in range(num_batches):
                start_idx = batch_idx * CONFIG.max_tables_per_batch
                end_idx = min(start_idx + CONFIG.max_tables_per_batch, len(tables))
                batch_tables = tables[start_idx:end_idx]
                
                batch_outcomes = extract_outcomes_single_model(batch_tables, model)
                outcomes.extend(batch_outcomes)
            
            # Deduplicate within model
            outcomes = semantic_deduplicate(outcomes)
            model_outcomes[model_short] = outcomes
            logger.info(f"    {model_short}: {len(outcomes)} outcomes")
        
        # Union all outcomes (with source tracking)
        all_outcomes = []
        for model_name, outcomes in model_outcomes.items():
            all_outcomes.extend(outcomes)
        
        # Final dedup
        all_outcomes = semantic_deduplicate(all_outcomes)
        logger.info(f"  ✅ Total after dedup: {len(all_outcomes)} outcomes")
        
        result["n_extracted"] = len(all_outcomes)
        result["extracted_outcomes"] = all_outcomes
        
        # Match against GT
        matching = match_outcomes_v14(all_outcomes, gt_outcomes)
        
        result["n_matched"] = matching["n_matched"]
        result["recall"] = matching["recall"]
        result["precision"] = matching["precision"]
        result["f1"] = matching["f1"]
        result["matches"] = matching["matches"]
        result["unmatched_gt_indices"] = matching["unmatched_gt_indices"]
        result["success"] = True
        
        # Per-model stats
        for model_name, outcomes in model_outcomes.items():
            model_match = match_outcomes_v14(outcomes, gt_outcomes, use_llm_validation=False)
            result["model_results"][model_name] = {
                "extracted": len(outcomes),
                "matched": model_match["n_matched"],
                "recall": model_match["recall"]
            }
        
        logger.info(f"  📊 Matched: {matching['n_matched']}/{len(gt_outcomes)} "
                   f"(R: {matching['recall']*100:.1f}%)")
        
        for model_name, stats in result["model_results"].items():
            logger.info(f"    {model_name}: {stats['matched']}/{len(gt_outcomes)} "
                       f"({stats['recall']*100:.1f}% recall)")
        
    except Exception as e:
        result["error"] = str(e)
        logger.error(f"  ❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    return result


def run_v14_pipeline(max_studies: int = None):
    """Run V14 pipeline with model comparison."""
    logger.info("=" * 70)
    logger.info("V14 EXTRACTION PIPELINE - Model Comparison & Traceability")
    logger.info("=" * 70)
    logger.info(f"Models: {', '.join(CONFIG.models)}")
    logger.info(f"Containment matching: {CONFIG.enable_containment_matching}")
    logger.info("")
    
    eval_path = Path(__file__).parent.parent / "evaluation" / "matched_studies_r2.json"
    with open(eval_path) as f:
        studies = json.load(f)
    
    if max_studies:
        studies = studies[:max_studies]
    
    logger.info(f"Processing {len(studies)} studies")
    
    results = []
    start_time = datetime.now()
    
    # Model-level aggregates
    model_totals = {m.split('/')[-1]: {"extracted": 0, "matched": 0} for m in CONFIG.models}
    total_gt = 0
    total_extracted = 0
    total_matched = 0
    
    for idx, study in enumerate(studies, 1):
        result = process_study_v14(study, idx, len(studies))
        results.append(result)
        
        if result["success"]:
            total_gt += result["n_gt_outcomes"]
            total_extracted += result["n_extracted"]
            total_matched += result["n_matched"]
            
            for model_name, stats in result.get("model_results", {}).items():
                model_totals[model_name]["extracted"] += stats["extracted"]
                model_totals[model_name]["matched"] += stats["matched"]
    
    elapsed = datetime.now() - start_time
    
    # Final summary
    overall_recall = total_matched / total_gt if total_gt > 0 else 0
    overall_precision = total_matched / total_extracted if total_extracted > 0 else 0
    overall_f1 = 2 * overall_recall * overall_precision / (overall_recall + overall_precision) if (overall_recall + overall_precision) > 0 else 0
    
    logger.info("")
    logger.info("=" * 70)
    logger.info("FINAL RESULTS - V14")
    logger.info("=" * 70)
    logger.info(f"Time elapsed: {elapsed}")
    logger.info("")
    logger.info(f"Ground truth outcomes: {total_gt}")
    logger.info(f"Extracted outcomes: {total_extracted}")
    logger.info(f"Matched outcomes: {total_matched}")
    logger.info("")
    logger.info(f"RECALL:    {overall_recall * 100:.1f}%  (target: 95%)")
    logger.info(f"PRECISION: {overall_precision * 100:.1f}%  (target: 70%)")
    logger.info(f"F1 SCORE:  {overall_f1 * 100:.1f}%")
    logger.info("")
    logger.info("=" * 70)
    logger.info("MODEL COMPARISON")
    logger.info("=" * 70)
    
    for model_name, totals in model_totals.items():
        model_recall = totals["matched"] / total_gt if total_gt > 0 else 0
        model_precision = totals["matched"] / totals["extracted"] if totals["extracted"] > 0 else 0
        logger.info(f"{model_name}:")
        logger.info(f"  Extracted: {totals['extracted']}")
        logger.info(f"  Matched: {totals['matched']} ({model_recall*100:.1f}% recall, {model_precision*100:.1f}% precision)")
    
    # Save results
    output_path = Path(__file__).parent / "v14_results.json"
    with open(output_path, 'w') as f:
        json.dump({
            "summary": {
                "total_gt": total_gt,
                "total_extracted": total_extracted,
                "total_matched": total_matched,
                "recall": overall_recall,
                "precision": overall_precision,
                "f1": overall_f1,
                "elapsed_seconds": elapsed.total_seconds()
            },
            "model_comparison": model_totals,
            "studies": results
        }, f, indent=2)
    
    logger.info(f"\nResults saved to {output_path}")
    
    return results


if __name__ == "__main__":
    import sys
    max_studies = int(sys.argv[1]) if len(sys.argv) > 1 else None
    run_v14_pipeline(max_studies)
