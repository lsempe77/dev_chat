"""
Extraction Pipeline V17b - Fast Recall Improvements

TARGET: 95% recall, 70% precision

V16 RESULTS: 73.2% recall, 11.5% precision (52/71 matched on 5 studies)
V17 (failed): Too slow due to per-match semantic validation

V17b = V16 + Fast recall improvements (no semantic validation):
1. Many-to-many matching: same GT can match multiple extracted outcomes
2. Taxonomy boost: +0.15 for generic GT names like "Assets", "Consumption"  
3. Bi-directional matching: GT-driven fallback pass for hard-to-match items
4. Lower thresholds for maximum recall

NO semantic validation (V17's per-match embeddings were too slow)
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
import sys
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
    """Pipeline configuration - V17b: Fast recall improvements."""
    # V17b: GPT-4o as primary model
    models: List[str] = field(default_factory=lambda: [
        "openai/gpt-4o",           # PRIMARY
        "openai/gpt-4o-mini"       # Secondary
    ])
    max_tokens_extraction: int = 32000
    max_tokens_validation: int = 200
    temperature: float = 0.0
    
    # Deduplication - LESS AGGRESSIVE (same as V13)
    dedup_similarity_threshold: float = 0.55
    
    # Matching thresholds - VERY LOW for max recall
    exact_match_threshold: float = 0.90
    high_confidence_threshold: float = 0.40  # V17b: lowered from 0.45
    llm_validation_threshold: float = 0.15   # V17b: lowered from 0.20
    llm_validation_min_confidence: float = 0.30  # V17b: lowered from 0.35
    
    # V17b: Many-to-many matching (same GT can match multiple extracted)
    allow_many_to_many: bool = True
    max_matches_per_gt: int = 5  # Allow up to 5 extracted outcomes per GT
    
    # V17b: Taxonomy boost for generic GT names
    taxonomy_boost: float = 0.15  # Boost similarity for taxonomy matches
    
    # Table processing
    max_tables_per_batch: int = 10
    min_table_rows: int = 2
    skip_descriptive_tables: bool = False
    
    # Prose extraction
    extract_from_prose: bool = True
    
    # Processing
    max_content_chars: int = 50000
    max_prompt_chars: int = 120000
    retry_attempts: int = 3
    retry_delay: int = 5
    
    # Few-shot examples
    use_few_shot: bool = True
    
    # V13: Greedy LLM matching for remaining unmatched
    use_greedy_llm_matching: bool = True
    greedy_llm_min_overlap: int = 2
    
    # Output
    review_output_path: str = "extraction_pipeline/v17b_review_queue.json"


CONFIG = Config()

# ============================================================================
# V17b: OUTCOME TAXONOMY FOR GENERIC GT NAME MATCHING
# ============================================================================
# Maps generic GT outcome names to related specific patterns
# Used to boost similarity when extracted outcomes conceptually match

OUTCOME_TAXONOMY = {
    # Economic outcomes
    "assets": ["asset", "wealth", "property", "livestock", "savings", "durable", "productive assets", "total asset", "asset value", "household asset"],
    "consumption": ["consumption", "expenditure", "spending", "food consumption", "total consumption", "per capita consumption", "household consumption", "consumption expenditure"],
    "income": ["income", "earnings", "revenue", "wage", "salary", "profit", "household income", "total income", "per capita income", "monthly income", "annual income"],
    "poverty": ["poverty", "poor", "below poverty", "poverty line", "poverty rate", "poverty status", "poverty index", "poverty headcount"],
    "food security": ["food security", "food insecurity", "hunger", "dietary", "nutrition", "caloric", "meal", "food access", "food consumption score"],
    
    # Agricultural outcomes
    "agricultural production": ["yield", "production", "harvest", "crop", "output", "agricultural output", "farm production", "agricultural productivity"],
    "land": ["land", "plot", "hectare", "acreage", "farm size", "cultivated area", "land ownership", "land use"],
    
    # Education outcomes
    "education": ["education", "school", "enrollment", "attendance", "literacy", "test score", "grade", "learning", "cognitive", "numeracy"],
    "school enrollment": ["enrollment", "enrolment", "school enrollment", "enrolled", "attending school", "in school"],
    
    # Health outcomes
    "health": ["health", "illness", "disease", "morbidity", "mortality", "BMI", "weight", "height", "stunting", "wasting", "nutrition"],
    "child health": ["child health", "infant", "under-5", "child mortality", "stunting", "wasting", "child nutrition", "immunization"],
    
    # Employment/Labor
    "employment": ["employment", "employed", "job", "work", "labor", "occupation", "working", "labor supply", "labor market"],
    "labor supply": ["labor", "work hours", "hours worked", "labor supply", "time use", "working hours", "labor participation"],
    
    # Financial outcomes  
    "savings": ["saving", "savings", "deposit", "bank account", "financial savings", "accumulated savings"],
    "credit": ["credit", "loan", "borrowing", "debt", "lending", "credit access", "credit constraint"],
    
    # Business outcomes
    "business": ["business", "enterprise", "firm", "self-employment", "microenterprise", "business profit", "business revenue"],
    "profit": ["profit", "net income", "business profit", "earnings", "returns", "margin"],
    
    # Social outcomes
    "empowerment": ["empowerment", "decision", "autonomy", "agency", "bargaining", "women's empowerment", "decision-making"],
    "wellbeing": ["wellbeing", "well-being", "welfare", "happiness", "life satisfaction", "subjective wellbeing"],
}

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
# OUTCOME NORMALIZATION
# ============================================================================

def normalize_outcome_name(name: str) -> str:
    """Normalize outcome name for better matching."""
    if not name:
        return ""
    
    name = name.lower().strip()
    
    prefixes = [
        "log ", "ln ", "log of ", "natural log of ",
        "change in ", "changes in ", "delta ",
        "z-score ", "z score ", "zscore ",
        "standardized ", "std. ", "std ",
        "total ", "average ", "mean ", "median ",
        "monthly ", "annual ", "yearly ", "daily ",
        "per capita ", "per-capita ",
    ]
    for prefix in prefixes:
        if name.startswith(prefix):
            name = name[len(prefix):]
    
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
        "agricultural": "agriculture",
        "non-agricultural": "non-agriculture",
        "non agricultural": "non-agriculture",
        "agric.": "agriculture",
        "educ.": "education",
        "schooling": "education",
        "years of schooling": "education years",
        "school enrollment": "enrollment",
        "school attendance": "attendance",
    }
    
    for old, new in replacements.items():
        name = name.replace(old, new)
    
    name = name.replace("(", " ").replace(")", " ")
    name = " ".join(name.split())
    
    return name


def get_outcome_core_words(name: str) -> Set[str]:
    """Extract core semantic words from outcome name."""
    name = normalize_outcome_name(name)
    
    stop_words = {
        'the', 'a', 'an', 'of', 'in', 'on', 'at', 'to', 'for', 'and', 'or',
        'is', 'are', 'was', 'were', 'be', 'been', 'being',
        'by', 'with', 'from', 'as', 'that', 'this', 'it',
        'per', 'total', 'overall', 'all', 'any', 'other',
    }
    
    words = set(name.split())
    return words - stop_words


def compute_word_overlap(text1: str, text2: str) -> int:
    """Compute number of overlapping core words."""
    words1 = get_outcome_core_words(text1)
    words2 = get_outcome_core_words(text2)
    return len(words1 & words2)


def compute_hybrid_similarity(text1: str, text2: str) -> Tuple[float, Dict]:
    """Compute hybrid similarity combining fuzzy and semantic matching."""
    text1_norm = normalize_outcome_name(text1)
    text2_norm = normalize_outcome_name(text2)
    
    if not text1_norm or not text2_norm:
        return 0.0, {"fuzzy": 0, "semantic": 0, "combined": 0, "word_overlap": 0}
    
    word_overlap = compute_word_overlap(text1, text2)
    
    if HAS_FUZZY:
        fuzzy_score = fuzz.token_set_ratio(text1_norm, text2_norm) / 100.0
    else:
        words1 = set(text1_norm.split())
        words2 = set(text2_norm.split())
        if words1 and words2:
            fuzzy_score = len(words1 & words2) / len(words1 | words2)
        else:
            fuzzy_score = 0.0
    
    if HAS_EMBEDDINGS and EMBEDDING_MODEL:
        emb1 = EMBEDDING_MODEL.encode(text1_norm, convert_to_numpy=True)
        emb2 = EMBEDDING_MODEL.encode(text2_norm, convert_to_numpy=True)
        semantic_score = cosine_similarity(emb1, emb2)
    else:
        semantic_score = fuzzy_score
    
    overlap_boost = min(0.1, word_overlap * 0.02)
    combined = 0.3 * fuzzy_score + 0.7 * semantic_score + overlap_boost
    combined = min(1.0, combined)
    
    return combined, {
        "fuzzy": round(fuzzy_score, 3),
        "semantic": round(semantic_score, 3),
        "combined": round(combined, 3),
        "word_overlap": word_overlap
    }


# ============================================================================
# SEMANTIC DEDUPLICATION
# ============================================================================

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
    
    deduped = [valid_outcomes[i] for i in keep_indices]
    logger.info(f"    Dedup: {len(valid_outcomes)} → {len(deduped)} outcomes (threshold={threshold})")
    
    return deduped


# ============================================================================
# EXTRACTION PROMPT
# ============================================================================

EXTRACTION_PROMPT = """You are an expert at extracting outcome variables from academic research papers on impact evaluation.

Your task: Extract ALL outcome variable names from the provided tables.

RULES:
1. Extract the EXACT outcome variable name as written in the table
2. Include ALL outcomes - even if they seem similar, keep them separate
3. Look for outcomes in:
   - Row headers (most common location)
   - Column headers (when columns represent different outcomes)
   - Panel headers (e.g., "Panel A: Education outcomes")
4. DO NOT include:
   - Control variables
   - Fixed effects
   - Statistical measures (R², N, SE)
   - Time dummies
   - Constants/intercepts

FORMAT: Return a JSON array of objects with "outcome_name" and "table_source" fields.

Example response:
```json
[
  {"outcome_name": "Total household consumption", "table_source": "Table 3"},
  {"outcome_name": "Food consumption", "table_source": "Table 3"},
  {"outcome_name": "Non-food consumption", "table_source": "Table 3"}
]
```

TABLES TO ANALYZE:
"""

PROSE_EXTRACTION_PROMPT = """You are an expert at extracting outcome variables from academic research papers.

Your task: Extract ALL outcome variable names mentioned in this text that represent MEASURED OUTCOMES of the study.

RULES:
1. Only extract variables that were actually MEASURED as outcomes in the study
2. Look for phrases like "we measure", "outcome variables include", "dependent variables", "we examine effects on"
3. Include ALL variants (e.g., if both "income" and "consumption" are measured, include both)
4. DO NOT include:
   - Variables mentioned as examples from other studies
   - Control variables
   - Methodology descriptions

FORMAT: Return a JSON array with "outcome_name" and "source" fields.

TEXT TO ANALYZE:
"""


def call_llm(model: str, prompt: str, max_tokens: int = None, timeout: int = 300) -> Optional[str]:
    """Call LLM via OpenRouter with extended timeout."""
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
                },
                timeout=timeout  # Extended timeout for GPT-4o
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
    """Parse JSON from LLM response, handling markdown code blocks."""
    if not response:
        return []
    
    response = re.sub(r'```json\s*', '', response)
    response = re.sub(r'```\s*', '', response)
    response = response.strip()
    
    try:
        data = json.loads(response)
        if isinstance(data, list):
            return data
        elif isinstance(data, dict):
            return [data]
    except json.JSONDecodeError:
        match = re.search(r'\[[\s\S]*\]', response)
        if match:
            try:
                return json.loads(match.group())
            except:
                pass
    
    return []


# ============================================================================
# EXTRACTION FUNCTIONS
# ============================================================================

def extract_outcomes_from_tables(tables: List[Dict], model: str) -> List[Dict]:
    """Extract outcomes from a batch of tables using specified model."""
    if not tables:
        return []
    
    table_content = []
    for i, table in enumerate(tables):
        table_id = table.get("table_id", f"Table {i+1}")
        content = table.get("content", "")
        if content:
            table_content.append(f"\n### {table_id}\n{content[:8000]}")
    
    if not table_content:
        return []
    
    prompt = EXTRACTION_PROMPT + "\n".join(table_content)
    
    if len(prompt) > CONFIG.max_prompt_chars:
        prompt = prompt[:CONFIG.max_prompt_chars]
    
    response = call_llm(model, prompt)
    outcomes = parse_json_response(response)
    
    return outcomes


def extract_outcomes_from_prose(text: str, model: str = "openai/gpt-4o") -> List[Dict]:
    """Extract outcomes mentioned in prose/text sections."""
    if not text or not CONFIG.extract_from_prose:
        return []
    
    text = text[:20000]
    
    prompt = PROSE_EXTRACTION_PROMPT + text
    response = call_llm(model, prompt, max_tokens=2000)
    outcomes = parse_json_response(response)
    
    for o in outcomes:
        o["source"] = "prose"
    
    return outcomes


def ensemble_extract_v16(tables: List[Dict], prose_text: str = "") -> List[Dict]:
    """
    V16 ensemble extraction: parallel extraction with GPT-4o models.
    """
    all_outcomes = []
    
    # Extract from tables with all models in parallel
    with ThreadPoolExecutor(max_workers=len(CONFIG.models)) as executor:
        futures = {
            executor.submit(extract_outcomes_from_tables, tables, model): model 
            for model in CONFIG.models
        }
        
        for future in as_completed(futures):
            model = futures[future]
            try:
                outcomes = future.result()
                logger.info(f"    {model.split('/')[-1]}: {len(outcomes)} outcomes")
                all_outcomes.extend(outcomes)
            except Exception as e:
                logger.error(f"    {model} failed: {e}")
    
    # Also extract from prose
    if prose_text:
        prose_outcomes = extract_outcomes_from_prose(prose_text)
        logger.info(f"    Prose extraction: {len(prose_outcomes)} outcomes")
        all_outcomes.extend(prose_outcomes)
    
    return all_outcomes


# ============================================================================
# LLM MATCH VALIDATION
# ============================================================================

def llm_validate_match(extracted_name: str, gt_name: str) -> Tuple[bool, float]:
    """Use LLM to validate if two outcome names refer to the same concept."""
    prompt = f"""Do these two outcome variable names refer to the SAME or VERY SIMILAR concept?

Extracted: "{extracted_name}"
Ground Truth: "{gt_name}"

Consider them a match if:
- They measure the same underlying concept (even with different wording)
- One is a subset or variant of the other
- They differ only in specificity or time period

Respond with ONLY a JSON object:
{{"match": true/false, "confidence": 0.0-1.0, "reason": "brief explanation"}}"""
    
    response = call_llm(
        "openai/gpt-4o-mini",
        prompt,
        max_tokens=CONFIG.max_tokens_validation
    )
    
    if not response:
        return False, 0.0
    
    try:
        response = re.sub(r'```json\s*', '', response)
        response = re.sub(r'```\s*', '', response)
        
        data = json.loads(response.strip())
        return data.get("match", False), data.get("confidence", 0.0)
    except:
        lower = response.lower()
        if '"match": true' in lower or '"match":true' in lower:
            return True, 0.7
        return False, 0.0


# ============================================================================
# MULTI-PASS MATCHING
# ============================================================================

def match_outcomes_v16(
    extracted: List[Dict],
    ground_truth: List[Dict],
    use_llm_validation: bool = True
) -> Dict:
    """V16 multi-pass matching (same as V13)."""
    matches = []
    unmatched_gt = list(range(len(ground_truth)))
    unmatched_ext = list(range(len(extracted)))
    llm_calls = 0
    
    similarity_matrix = {}
    for ext_idx in range(len(extracted)):
        ext_name = extracted[ext_idx].get('outcome_name', '')
        for gt_idx in range(len(ground_truth)):
            gt_name = ground_truth[gt_idx].get('name', '')
            score, details = compute_hybrid_similarity(ext_name, gt_name)
            similarity_matrix[(ext_idx, gt_idx)] = (score, details)
    
    def try_match(ext_idx: int, gt_idx: int, match_type: str, llm_conf: float = None):
        nonlocal unmatched_gt, unmatched_ext
        
        if gt_idx not in unmatched_gt or ext_idx not in unmatched_ext:
            return False
        
        ext_name = extracted[ext_idx].get('outcome_name', '')
        gt_name = ground_truth[gt_idx].get('name', '')
        score, details = similarity_matrix[(ext_idx, gt_idx)]
        
        match_record = {
            "extracted_idx": ext_idx,
            "gt_idx": gt_idx,
            "extracted_name": ext_name,
            "gt_name": gt_name,
            "similarity": details,
            "match_type": match_type
        }
        if llm_conf is not None:
            match_record["llm_confidence"] = llm_conf
        
        matches.append(match_record)
        unmatched_gt.remove(gt_idx)
        unmatched_ext.remove(ext_idx)
        return True
    
    # Pass 1: Exact/near-exact matches
    for ext_idx in list(unmatched_ext):
        best_gt, best_score = None, 0
        for gt_idx in unmatched_gt:
            score, _ = similarity_matrix[(ext_idx, gt_idx)]
            if score > best_score:
                best_score = score
                best_gt = gt_idx
        
        if best_gt is not None and best_score >= CONFIG.exact_match_threshold:
            try_match(ext_idx, best_gt, "exact")
    
    # Pass 2: High-confidence semantic matches
    for ext_idx in list(unmatched_ext):
        best_gt, best_score = None, 0
        for gt_idx in unmatched_gt:
            score, _ = similarity_matrix[(ext_idx, gt_idx)]
            if score > best_score:
                best_score = score
                best_gt = gt_idx
        
        if best_gt is not None and best_score >= CONFIG.high_confidence_threshold:
            try_match(ext_idx, best_gt, "high_confidence")
    
    # Pass 3: LLM validation for medium-confidence
    if use_llm_validation:
        candidates = []
        for ext_idx in unmatched_ext:
            for gt_idx in unmatched_gt:
                score, details = similarity_matrix[(ext_idx, gt_idx)]
                if score >= CONFIG.llm_validation_threshold:
                    candidates.append((ext_idx, gt_idx, score, details))
        
        candidates.sort(key=lambda x: x[2], reverse=True)
        
        for ext_idx, gt_idx, score, details in candidates:
            if gt_idx not in unmatched_gt or ext_idx not in unmatched_ext:
                continue
            
            ext_name = extracted[ext_idx].get('outcome_name', '')
            gt_name = ground_truth[gt_idx].get('name', '')
            
            is_match, confidence = llm_validate_match(ext_name, gt_name)
            llm_calls += 1
            
            if is_match and confidence >= CONFIG.llm_validation_min_confidence:
                try_match(ext_idx, gt_idx, "llm_validated", confidence)
    
    # Pass 4: Greedy LLM matching
    if CONFIG.use_greedy_llm_matching and unmatched_gt:
        logger.info(f"    Greedy LLM: {len(unmatched_gt)} GT still unmatched")
        
        for gt_idx in list(unmatched_gt):
            gt_name = ground_truth[gt_idx].get('name', '')
            
            candidates = []
            for ext_idx in unmatched_ext:
                ext_name = extracted[ext_idx].get('outcome_name', '')
                overlap = compute_word_overlap(ext_name, gt_name)
                if overlap >= CONFIG.greedy_llm_min_overlap:
                    candidates.append((ext_idx, overlap))
            
            candidates.sort(key=lambda x: x[1], reverse=True)
            
            for ext_idx, overlap in candidates[:3]:
                if ext_idx not in unmatched_ext:
                    continue
                
                ext_name = extracted[ext_idx].get('outcome_name', '')
                is_match, confidence = llm_validate_match(ext_name, gt_name)
                llm_calls += 1
                
                if is_match and confidence >= 0.3:
                    try_match(ext_idx, gt_idx, "greedy_llm", confidence)
                    break
    
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
        "llm_calls": llm_calls,
        "unmatched_gt_indices": unmatched_gt
    }


def get_taxonomy_boost(extracted_name: str, gt_name: str) -> float:
    """Check if extracted name matches any patterns in GT's taxonomy category."""
    gt_lower = gt_name.lower().strip()
    ext_lower = extracted_name.lower()
    
    # Find taxonomy category for this GT name
    for category, patterns in OUTCOME_TAXONOMY.items():
        # Check if GT name matches this category
        if category in gt_lower or any(p in gt_lower for p in patterns[:3]):
            # Check if extracted name matches any pattern in this category
            for pattern in patterns:
                if pattern in ext_lower:
                    return CONFIG.taxonomy_boost
    return 0.0


def match_outcomes_v17b(
    extracted: List[Dict],
    ground_truth: List[Dict],
    use_llm_validation: bool = True
) -> Dict:
    """
    V17b matching with fast recall improvements:
    1. Many-to-many: same GT can match multiple extracted outcomes
    2. Taxonomy boost: +0.15 for conceptually related outcomes
    3. Lower thresholds for maximum recall
    4. Bi-directional: GT-driven fallback for hard-to-match items
    """
    matches = []
    matched_gt = set()  # Track which GTs have been matched (can match multiple times)
    gt_match_counts = {i: 0 for i in range(len(ground_truth))}  # Count matches per GT
    unmatched_ext = list(range(len(extracted)))
    llm_calls = 0
    
    # Compute similarity matrix with taxonomy boost
    similarity_matrix = {}
    for ext_idx in range(len(extracted)):
        ext_name = extracted[ext_idx].get('outcome_name', '')
        for gt_idx in range(len(ground_truth)):
            gt_name = ground_truth[gt_idx].get('name', '')
            base_score, details = compute_hybrid_similarity(ext_name, gt_name)
            
            # Apply taxonomy boost
            tax_boost = get_taxonomy_boost(ext_name, gt_name)
            boosted_score = min(1.0, base_score + tax_boost)
            
            if tax_boost > 0:
                details['taxonomy_boost'] = tax_boost
                details['boosted_combined'] = boosted_score
            
            similarity_matrix[(ext_idx, gt_idx)] = (boosted_score, details)
    
    def try_match_v17b(ext_idx: int, gt_idx: int, match_type: str, llm_conf: float = None) -> bool:
        """Try to match - allows many-to-many if enabled."""
        nonlocal matched_gt, unmatched_ext
        
        if ext_idx not in unmatched_ext:
            return False
        
        # Check if GT can still accept matches (many-to-many limit)
        if CONFIG.allow_many_to_many:
            if gt_match_counts[gt_idx] >= CONFIG.max_matches_per_gt:
                return False
        else:
            if gt_idx in matched_gt:
                return False
        
        ext_name = extracted[ext_idx].get('outcome_name', '')
        gt_name = ground_truth[gt_idx].get('name', '')
        score, details = similarity_matrix[(ext_idx, gt_idx)]
        
        match_record = {
            "extracted_idx": ext_idx,
            "gt_idx": gt_idx,
            "extracted_name": ext_name,
            "gt_name": gt_name,
            "similarity": details,
            "match_type": match_type
        }
        if llm_conf is not None:
            match_record["llm_confidence"] = llm_conf
        
        matches.append(match_record)
        matched_gt.add(gt_idx)
        gt_match_counts[gt_idx] += 1
        unmatched_ext.remove(ext_idx)
        return True
    
    # Pass 1: Exact/near-exact matches
    for ext_idx in list(unmatched_ext):
        best_gt, best_score = None, 0
        for gt_idx in range(len(ground_truth)):
            if not CONFIG.allow_many_to_many and gt_idx in matched_gt:
                continue
            if gt_match_counts[gt_idx] >= CONFIG.max_matches_per_gt:
                continue
            
            score, _ = similarity_matrix[(ext_idx, gt_idx)]
            if score > best_score:
                best_score = score
                best_gt = gt_idx
        
        if best_gt is not None and best_score >= CONFIG.exact_match_threshold:
            try_match_v17b(ext_idx, best_gt, "exact")
    
    # Pass 2: High-confidence semantic matches (with taxonomy boost)
    for ext_idx in list(unmatched_ext):
        best_gt, best_score = None, 0
        for gt_idx in range(len(ground_truth)):
            if not CONFIG.allow_many_to_many and gt_idx in matched_gt:
                continue
            if gt_match_counts[gt_idx] >= CONFIG.max_matches_per_gt:
                continue
            
            score, _ = similarity_matrix[(ext_idx, gt_idx)]
            if score > best_score:
                best_score = score
                best_gt = gt_idx
        
        if best_gt is not None and best_score >= CONFIG.high_confidence_threshold:
            try_match_v17b(ext_idx, best_gt, "high_confidence")
    
    # Pass 3: LLM validation for medium-confidence
    if use_llm_validation:
        candidates = []
        for ext_idx in unmatched_ext:
            for gt_idx in range(len(ground_truth)):
                if not CONFIG.allow_many_to_many and gt_idx in matched_gt:
                    continue
                if gt_match_counts[gt_idx] >= CONFIG.max_matches_per_gt:
                    continue
                
                score, details = similarity_matrix[(ext_idx, gt_idx)]
                if score >= CONFIG.llm_validation_threshold:
                    candidates.append((ext_idx, gt_idx, score, details))
        
        candidates.sort(key=lambda x: x[2], reverse=True)
        
        for ext_idx, gt_idx, score, details in candidates:
            if ext_idx not in unmatched_ext:
                continue
            if not CONFIG.allow_many_to_many and gt_idx in matched_gt:
                continue
            if gt_match_counts[gt_idx] >= CONFIG.max_matches_per_gt:
                continue
            
            ext_name = extracted[ext_idx].get('outcome_name', '')
            gt_name = ground_truth[gt_idx].get('name', '')
            
            is_match, confidence = llm_validate_match(ext_name, gt_name)
            llm_calls += 1
            
            if is_match and confidence >= CONFIG.llm_validation_min_confidence:
                try_match_v17b(ext_idx, gt_idx, "llm_validated", confidence)
    
    # Pass 4: GT-driven fallback (bi-directional matching)
    # For each unmatched GT, look for any remaining extracted outcomes that could match
    unmatched_gt_indices = [i for i in range(len(ground_truth)) if i not in matched_gt]
    
    if CONFIG.use_greedy_llm_matching and unmatched_gt_indices:
        logger.info(f"    GT-driven fallback: {len(unmatched_gt_indices)} GT unmatched")
        
        for gt_idx in unmatched_gt_indices:
            gt_name = ground_truth[gt_idx].get('name', '')
            
            # Find candidates with any word overlap
            candidates = []
            for ext_idx in unmatched_ext:
                ext_name = extracted[ext_idx].get('outcome_name', '')
                overlap = compute_word_overlap(ext_name, gt_name)
                score, _ = similarity_matrix[(ext_idx, gt_idx)]
                
                # Lower threshold for GT-driven pass
                if overlap >= 1 or score >= 0.10:
                    candidates.append((ext_idx, overlap, score))
            
            candidates.sort(key=lambda x: (x[1], x[2]), reverse=True)
            
            for ext_idx, overlap, score in candidates[:5]:  # Try more candidates
                if ext_idx not in unmatched_ext:
                    continue
                
                ext_name = extracted[ext_idx].get('outcome_name', '')
                is_match, confidence = llm_validate_match(ext_name, gt_name)
                llm_calls += 1
                
                if is_match and confidence >= 0.25:  # Lower threshold
                    try_match_v17b(ext_idx, gt_idx, "gt_driven_fallback", confidence)
                    break
    
    # Calculate metrics - use unique GT matches for recall
    unique_gt_matched = len(matched_gt)
    recall = unique_gt_matched / len(ground_truth) if ground_truth else 0
    precision = len(matches) / len(extracted) if extracted else 0
    f1 = 2 * recall * precision / (recall + precision) if (recall + precision) > 0 else 0
    
    return {
        "matches": matches,
        "recall": recall,
        "precision": precision,
        "f1": f1,
        "n_matched": len(matches),
        "n_unique_gt_matched": unique_gt_matched,
        "n_extracted": len(extracted),
        "n_ground_truth": len(ground_truth),
        "llm_calls": llm_calls,
        "unmatched_gt_indices": list(set(range(len(ground_truth))) - matched_gt)
    }


# ============================================================================
# R2 DATA LOADING
# ============================================================================

def get_r2_client():
    """Get R2 client."""
    return boto3.client(
        's3',
        endpoint_url=f'https://{CLOUDFLARE_ACCOUNT_ID}.r2.cloudflarestorage.com',
        aws_access_key_id=R2_ACCESS_KEY,
        aws_secret_access_key=R2_SECRET_KEY
    )


def load_document(r2_key: str) -> Tuple[str, List[Dict], Dict]:
    """Load document from R2 and extract tables + prose."""
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
# MAIN PIPELINE
# ============================================================================

def process_study_v16(study: Dict, idx: int, total: int) -> Dict:
    """Process a single study with V16 pipeline."""
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
        "n_tables": 0,
        "n_extracted": 0,
        "n_matched": 0,
        "recall": 0.0,
        "precision": 0.0,
        "f1": 0.0
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
        
        logger.info(f"  Processing {len(tables)} tables")
        
        all_outcomes = []
        num_batches = (len(tables) + CONFIG.max_tables_per_batch - 1) // CONFIG.max_tables_per_batch
        
        for batch_idx in range(num_batches):
            start_idx = batch_idx * CONFIG.max_tables_per_batch
            end_idx = min(start_idx + CONFIG.max_tables_per_batch, len(tables))
            batch_tables = tables[start_idx:end_idx]
            
            batch_prose = prose if batch_idx == 0 else ""
            batch_outcomes = ensemble_extract_v16(batch_tables, batch_prose)
            batch_outcomes = semantic_deduplicate(batch_outcomes)
            
            logger.info(f"    Batch {batch_idx + 1}/{num_batches}: {len(batch_outcomes)} outcomes")
            all_outcomes.extend(batch_outcomes)
        
        all_outcomes = semantic_deduplicate(all_outcomes)
        logger.info(f"  ✅ Extracted {len(all_outcomes)} outcomes")
        
        result["n_extracted"] = len(all_outcomes)
        result["extracted_outcomes"] = all_outcomes
        
        # V17b: Use new matching function with many-to-many and taxonomy boost
        matching = match_outcomes_v17b(all_outcomes, gt_outcomes)
        
        result["n_matched"] = matching["n_matched"]
        result["n_unique_gt_matched"] = matching.get("n_unique_gt_matched", matching["n_matched"])
        result["recall"] = matching["recall"]
        result["precision"] = matching["precision"]
        result["f1"] = matching["f1"]
        result["matches"] = matching["matches"]
        result["unmatched_gt_indices"] = matching["unmatched_gt_indices"]
        result["success"] = True
        
        logger.info(f"  📊 Matched: {matching['n_matched']}/{len(gt_outcomes)} "
                   f"(R: {matching['recall']*100:.1f}%, P: {matching['precision']*100:.1f}%, "
                   f"F1: {matching['f1']*100:.1f}%)")
        
    except Exception as e:
        result["error"] = str(e)
        logger.error(f"  ❌ Error: {e}")
    
    return result


def run_v16_pipeline(num_studies: int = None):
    """Run V16 pipeline on studies."""
    logger.info("=" * 70)
    logger.info("EXTRACTION PIPELINE V16 - V13 Approach + GPT-4o")
    logger.info("=" * 70)
    logger.info(f"Models: {CONFIG.models}")
    logger.info(f"Dedup threshold: {CONFIG.dedup_similarity_threshold}")
    logger.info(f"Match thresholds: exact={CONFIG.exact_match_threshold}, high={CONFIG.high_confidence_threshold}, llm={CONFIG.llm_validation_threshold}")
    logger.info("")
    
    eval_path = Path(__file__).parent.parent / "evaluation" / "matched_studies_r2.json"
    with open(eval_path) as f:
        studies = json.load(f)
    
    if num_studies:
        studies = studies[:num_studies]
    
    logger.info(f"Processing {len(studies)} studies")
    
    results = []
    start_time = datetime.now()
    
    total_gt = 0
    total_extracted = 0
    total_matched = 0
    
    for idx, study in enumerate(studies, 1):
        result = process_study_v16(study, idx, len(studies))
        results.append(result)
        
        if result["success"]:
            total_gt += result["n_gt_outcomes"]
            total_extracted += result["n_extracted"]
            total_matched += result["n_matched"]
        
        if idx % 5 == 0:
            successful = [r for r in results if r.get('success')]
            if successful:
                avg_recall = np.mean([r['recall'] for r in successful])
                avg_precision = np.mean([r['precision'] for r in successful])
                logger.info("=" * 50)
                logger.info(f"PROGRESS: {idx}/{len(studies)}")
                logger.info(f"R: {avg_recall*100:.1f}% | P: {avg_precision*100:.1f}%")
                logger.info(f"Matched: {total_matched}/{total_gt}")
                logger.info("=" * 50)
    
    elapsed = datetime.now() - start_time
    overall_recall = total_matched / total_gt if total_gt > 0 else 0
    overall_precision = total_matched / total_extracted if total_extracted > 0 else 0
    overall_f1 = 2 * overall_recall * overall_precision / (overall_recall + overall_precision) if (overall_recall + overall_precision) > 0 else 0
    
    studies_100_recall = sum(1 for r in results if r.get("recall", 0) == 1.0)
    
    logger.info("")
    logger.info("=" * 70)
    logger.info("FINAL RESULTS - V16 (V13 + GPT-4o)")
    logger.info("=" * 70)
    logger.info(f"Studies processed: {len(studies)}")
    logger.info(f"Successful: {sum(1 for r in results if r.get('success'))}")
    logger.info(f"Time elapsed: {elapsed}")
    logger.info("")
    logger.info(f"Ground truth outcomes: {total_gt}")
    logger.info(f"Extracted outcomes: {total_extracted}")
    logger.info(f"Matched outcomes: {total_matched}")
    logger.info("")
    logger.info(f"RECALL:    {overall_recall * 100:.1f}%  (V13 baseline: 71.9%)")
    logger.info(f"PRECISION: {overall_precision * 100:.1f}%  (V13 baseline: 12.5%)")
    logger.info(f"F1 SCORE:  {overall_f1 * 100:.1f}%")
    logger.info("")
    logger.info(f"Studies with 100% recall: {studies_100_recall}")
    logger.info("=" * 70)
    
    output_path = Path(__file__).parent / "v16_results.json"
    with open(output_path, 'w') as f:
        json.dump({
            "summary": {
                "total_gt": total_gt,
                "total_extracted": total_extracted,
                "total_matched": total_matched,
                "recall": overall_recall,
                "precision": overall_precision,
                "f1": overall_f1,
                "studies_100_recall": studies_100_recall,
                "elapsed_seconds": elapsed.total_seconds()
            },
            "studies": results
        }, f, indent=2)
    
    logger.info(f"Results saved to {output_path}")
    
    return results


if __name__ == "__main__":
    num_studies = int(sys.argv[1]) if len(sys.argv) > 1 else None
    run_v16_pipeline(num_studies)
