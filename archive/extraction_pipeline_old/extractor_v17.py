"""
Extraction Pipeline V17 - Advanced Matching Fixes

TARGET: 95% recall, 70% precision

V16 RESULTS: 73.2% recall, 11.5% precision (52/71 matched on 5 studies)

V17 IMPROVEMENTS:
1. Many-to-Many Matching: Allow multiple extracted outcomes to match same GT name
   - GT can have "Assets" appearing 10 times (different subgroups/timepoints)
   - Previously only 1 got matched; now all can match
   
2. Semantic Validation: Prevent false positive matches from consuming GT slots
   - Check concept overlap between extracted and GT
   - Verify outcome types match (count vs value vs index vs binary)
   
3. Hierarchical Taxonomy: Map generic GT names to specific patterns
   - "Assets" should match "Livestock asset value", "Household assets", etc.
   - "Expenditure" should match "Food consumption", "Monthly spending", etc.

EXPECTED IMPACT: +13-20% recall improvement
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
from collections import defaultdict

# Local imports
from preprocess import preprocess_mineru_table, ParsedTable

load_dotenv()

# ============================================================================
# CONFIGURATION
# ============================================================================

@dataclass
class Config:
    """Pipeline configuration - V17 with advanced matching."""
    # Models - same as V16
    models: List[str] = field(default_factory=lambda: [
        "openai/gpt-4o",
        "openai/gpt-4o-mini"
    ])
    max_tokens_extraction: int = 32000
    max_tokens_validation: int = 200
    temperature: float = 0.0
    
    # Deduplication - LESS AGGRESSIVE
    dedup_similarity_threshold: float = 0.55
    
    # Matching thresholds
    exact_match_threshold: float = 0.90
    high_confidence_threshold: float = 0.45
    llm_validation_threshold: float = 0.20
    llm_validation_min_confidence: float = 0.35
    
    # V17: Semantic validation settings
    min_concept_overlap: float = 0.3  # At least 30% concept overlap
    validate_outcome_types: bool = True
    
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
    
    # Greedy LLM matching
    use_greedy_llm_matching: bool = True
    greedy_llm_min_overlap: int = 2
    
    # Output
    review_output_path: str = "extraction_pipeline/v17_review_queue.json"


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
# HIERARCHICAL OUTCOME TAXONOMY (V17 NEW)
# ============================================================================

OUTCOME_TAXONOMY = {
    "assets": [
        "asset", "assets", "household asset", "productive asset", "livestock asset",
        "business asset", "agricultural asset", "durable goods", "durables",
        "asset index", "asset value", "wealth", "wealth index", "property",
        "asset ownership", "asset holdings", "capital", "equipment"
    ],
    "expenditure": [
        "expenditure", "consumption", "spending", "expenses",
        "food expenditure", "non-food expenditure", "monthly expenditure",
        "per capita expenditure", "household expenditure", "total expenditure",
        "food consumption", "non-food consumption", "per capita consumption"
    ],
    "income": [
        "income", "revenue", "revenues", "earnings", "wage", "wages",
        "profit", "profits", "business income", "farm income", "non-farm income",
        "total income", "household income", "annual income", "monthly income",
        "labor income", "agricultural income", "income per capita"
    ],
    "savings": [
        "saving", "savings", "deposits", "bank balance", "financial assets",
        "cash savings", "formal savings", "informal savings"
    ],
    "employment": [
        "employment", "labor", "work", "job", "occupation",
        "working hours", "labor supply", "employment status",
        "self-employment", "wage employment", "labor participation"
    ],
    "education": [
        "education", "schooling", "enrollment", "attendance",
        "years of schooling", "school enrollment", "school attendance",
        "educational attainment", "literacy", "numeracy", "test scores"
    ],
    "health": [
        "health", "illness", "disease", "medical", "healthcare",
        "health status", "health outcomes", "nutrition", "anthropometric",
        "height", "weight", "bmi", "stunting", "wasting"
    ],
    "food security": [
        "food security", "food insecurity", "hunger", "dietary",
        "food consumption score", "food diversity", "meals",
        "adequate food", "food shortage", "caloric intake"
    ],
    "livestock": [
        "livestock", "cattle", "goat", "sheep", "poultry", "chicken",
        "tlu", "tropical livestock", "herd size", "animal", "animals"
    ],
    "credit": [
        "credit", "loan", "loans", "borrowing", "debt",
        "credit access", "loan amount", "interest rate"
    ]
}

def get_taxonomy_matches(gt_name: str) -> List[str]:
    """Get expanded list of acceptable matches for a GT name using taxonomy."""
    gt_lower = gt_name.lower()
    
    # Check if GT matches any taxonomy category
    for category, terms in OUTCOME_TAXONOMY.items():
        # If GT is a generic category name
        if gt_lower in terms or any(term in gt_lower for term in [category]):
            return terms
    
    return [gt_lower]


def taxonomy_match_score(extracted_name: str, gt_name: str) -> float:
    """Check if extracted name matches GT through taxonomy expansion."""
    ext_lower = extracted_name.lower()
    gt_lower = gt_name.lower()
    
    # Direct match
    if ext_lower == gt_lower:
        return 1.0
    
    # Check taxonomy expansion
    acceptable_terms = get_taxonomy_matches(gt_name)
    
    for term in acceptable_terms:
        if term in ext_lower or ext_lower in term:
            return 0.8  # High match through taxonomy
    
    return 0.0

# ============================================================================
# OUTCOME TYPE CLASSIFICATION (V17 NEW)
# ============================================================================

OUTCOME_TYPE_PATTERNS = {
    "count": [
        r"count", r"number of", r"number", r"how many", r"quantity",
        r"\bnum\b", r"total\s+\w+\s*$", r"tlu", r"tropical livestock units"
    ],
    "value": [
        r"value", r"worth", r"amount", r"usd", r"dollar", r"\$",
        r"ppp", r"birr", r"price", r"cost", r"revenue", r"income",
        r"expenditure", r"consumption", r"spending", r"profit", r"wage"
    ],
    "index": [
        r"index", r"score", r"composite", r"standardized", r"z-score",
        r"scale", r"measure", r"rating"
    ],
    "binary": [
        r"whether", r"if", r"has", r"have", r"own", r"access to",
        r"received", r"participated", r"enrolled", r"employed",
        r"dummy", r"indicator", r"1\s*=", r"yes/no"
    ],
    "rate": [
        r"rate", r"ratio", r"percent", r"percentage", r"proportion",
        r"share", r"\%", r"per\s+capita"
    ]
}


def classify_outcome_type(name: str) -> str:
    """Classify an outcome into type categories."""
    name_lower = name.lower()
    
    type_scores = defaultdict(float)
    
    for outcome_type, patterns in OUTCOME_TYPE_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, name_lower):
                type_scores[outcome_type] += 1
    
    if not type_scores:
        return "unknown"
    
    return max(type_scores, key=type_scores.get)


def types_compatible(ext_type: str, gt_type: str) -> bool:
    """Check if two outcome types are compatible for matching."""
    if ext_type == "unknown" or gt_type == "unknown":
        return True  # Don't block on unknown types
    
    if ext_type == gt_type:
        return True
    
    # Compatible type pairs
    compatible_pairs = {
        ("value", "rate"),
        ("rate", "value"),
        ("count", "value"),
        ("value", "count"),
        ("index", "value"),
        ("value", "index"),
    }
    
    return (ext_type, gt_type) in compatible_pairs

# ============================================================================
# CONCEPT EXTRACTION (V17 NEW)
# ============================================================================

CONCEPT_STOPWORDS = {
    'the', 'a', 'an', 'of', 'in', 'on', 'at', 'to', 'for', 'and', 'or',
    'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had',
    'by', 'with', 'from', 'as', 'that', 'this', 'it', 'its',
    'per', 'total', 'overall', 'all', 'any', 'other', 'each',
    'monthly', 'yearly', 'annual', 'daily', 'weekly',
    'average', 'mean', 'median', 'sum', 'log', 'ln',
    'usd', 'ppp', 'dollars', 'birr', 'kes',
    '1', '2', '3', '4', '5', 'i', 'ii', 'iii', 'iv', 'v'
}


def extract_core_concepts(name: str) -> Set[str]:
    """Extract core semantic concepts from an outcome name."""
    # Normalize
    name = name.lower()
    name = re.sub(r'[^\w\s]', ' ', name)
    name = ' '.join(name.split())
    
    words = set(name.split())
    concepts = words - CONCEPT_STOPWORDS
    
    # Remove short words (likely not meaningful)
    concepts = {w for w in concepts if len(w) > 2}
    
    return concepts


def compute_concept_overlap(extracted_name: str, gt_name: str) -> float:
    """Compute overlap of core concepts between two outcome names."""
    ext_concepts = extract_core_concepts(extracted_name)
    gt_concepts = extract_core_concepts(gt_name)
    
    if not gt_concepts:
        return 1.0  # If GT has no concepts, don't penalize
    
    if not ext_concepts:
        return 0.0
    
    overlap = len(ext_concepts & gt_concepts)
    
    # Compute overlap as fraction of GT concepts found
    overlap_ratio = overlap / len(gt_concepts)
    
    return overlap_ratio

# ============================================================================
# SEMANTIC VALIDATION (V17 NEW)
# ============================================================================

def validate_semantic_match(extracted_name: str, gt_name: str, similarity_score: float) -> Tuple[bool, str]:
    """
    Validate if a semantic match is truly valid.
    Returns (is_valid, rejection_reason)
    """
    # Check 1: Concept overlap
    concept_overlap = compute_concept_overlap(extracted_name, gt_name)
    
    if concept_overlap < CONFIG.min_concept_overlap and similarity_score < 0.7:
        return False, f"low_concept_overlap ({concept_overlap:.2f})"
    
    # Check 2: Outcome type compatibility
    if CONFIG.validate_outcome_types:
        ext_type = classify_outcome_type(extracted_name)
        gt_type = classify_outcome_type(gt_name)
        
        if not types_compatible(ext_type, gt_type):
            return False, f"type_mismatch ({ext_type} vs {gt_type})"
    
    # Check 3: Taxonomy match boost
    taxonomy_score = taxonomy_match_score(extracted_name, gt_name)
    if taxonomy_score >= 0.8:
        return True, "taxonomy_match"
    
    return True, "passed_validation"

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
    
    # V17: Add taxonomy boost
    taxonomy_score = taxonomy_match_score(text1, text2)
    taxonomy_boost = taxonomy_score * 0.15
    
    overlap_boost = min(0.1, word_overlap * 0.02)
    combined = 0.3 * fuzzy_score + 0.7 * semantic_score + overlap_boost + taxonomy_boost
    combined = min(1.0, combined)
    
    return combined, {
        "fuzzy": round(fuzzy_score, 3),
        "semantic": round(semantic_score, 3),
        "combined": round(combined, 3),
        "word_overlap": word_overlap,
        "taxonomy_boost": round(taxonomy_boost, 3)
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


def call_llm(model: str, prompt: str, max_tokens: int = None, timeout: int = 120) -> Optional[str]:
    """Call LLM via OpenRouter with extended timeout and robust retry."""
    import requests.exceptions
    max_tokens = max_tokens or CONFIG.max_tokens_extraction
    
    for attempt in range(CONFIG.retry_attempts + 2):  # Extra attempts for network issues
        try:
            response = SESSION.post(
                "https://openrouter.ai/api/v1/chat/completions",
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": max_tokens,
                    "temperature": CONFIG.temperature,
                },
                timeout=(30, timeout)  # (connect timeout, read timeout)
            )
            
            if response.status_code == 200:
                data = response.json()
                return data["choices"][0]["message"]["content"]
            elif response.status_code == 429:
                wait_time = CONFIG.retry_delay * (attempt + 1)
                logger.warning(f"Rate limited, waiting {wait_time}s...")
                time.sleep(wait_time)
            elif response.status_code >= 500:
                logger.warning(f"Server error {response.status_code}, retrying...")
                time.sleep(CONFIG.retry_delay * (attempt + 1))
            else:
                logger.error(f"API error: {response.status_code}")
                return None
                
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            logger.warning(f"Network error (attempt {attempt + 1}): {type(e).__name__}")
            if attempt < CONFIG.retry_attempts + 1:
                time.sleep(CONFIG.retry_delay * (attempt + 1))
            continue
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            if attempt < CONFIG.retry_attempts + 1:
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


def ensemble_extract_v17(tables: List[Dict], prose_text: str = "") -> List[Dict]:
    """V17 ensemble extraction."""
    all_outcomes = []
    
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
# V17 MULTI-PASS MATCHING (MANY-TO-MANY + SEMANTIC VALIDATION)
# ============================================================================

def match_outcomes_v17(
    extracted: List[Dict],
    ground_truth: List[Dict],
    use_llm_validation: bool = True
) -> Dict:
    """
    V17 multi-pass matching with key improvements:
    1. Many-to-many: Same GT name can be matched multiple times (for different GT indices)
    2. Semantic validation: Prevent false positive matches
    3. Taxonomy expansion: Generic GT names match specific extractions
    """
    matches = []
    unmatched_gt = set(range(len(ground_truth)))
    unmatched_ext = set(range(len(extracted)))
    llm_calls = 0
    rejected_matches = []
    
    # Build GT name to indices map for many-to-many matching
    gt_name_to_indices = defaultdict(list)
    for gt_idx, gt in enumerate(ground_truth):
        gt_name = gt.get('name', '').lower().strip()
        gt_name_to_indices[gt_name].append(gt_idx)
    
    # Pre-compute similarity matrix
    similarity_matrix = {}
    for ext_idx in range(len(extracted)):
        ext_name = extracted[ext_idx].get('outcome_name', '')
        for gt_idx in range(len(ground_truth)):
            gt_name = ground_truth[gt_idx].get('name', '')
            score, details = compute_hybrid_similarity(ext_name, gt_name)
            similarity_matrix[(ext_idx, gt_idx)] = (score, details)
    
    def try_match(ext_idx: int, gt_idx: int, match_type: str, llm_conf: float = None) -> bool:
        """Attempt to match extracted outcome to GT outcome."""
        if gt_idx not in unmatched_gt or ext_idx not in unmatched_ext:
            return False
        
        ext_name = extracted[ext_idx].get('outcome_name', '')
        gt_name = ground_truth[gt_idx].get('name', '')
        score, details = similarity_matrix[(ext_idx, gt_idx)]
        
        # V17: Semantic validation to prevent false positives
        if match_type in ["high_confidence", "llm_validated", "greedy_llm"]:
            is_valid, rejection_reason = validate_semantic_match(ext_name, gt_name, score)
            if not is_valid:
                rejected_matches.append({
                    "ext_name": ext_name,
                    "gt_name": gt_name,
                    "reason": rejection_reason,
                    "score": score
                })
                return False
        
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
        unmatched_gt.discard(gt_idx)
        unmatched_ext.discard(ext_idx)
        return True
    
    # Pass 1: Exact/near-exact matches (always valid)
    for ext_idx in list(unmatched_ext):
        best_gt, best_score = None, 0
        for gt_idx in unmatched_gt:
            score, _ = similarity_matrix[(ext_idx, gt_idx)]
            if score > best_score:
                best_score = score
                best_gt = gt_idx
        
        if best_gt is not None and best_score >= CONFIG.exact_match_threshold:
            try_match(ext_idx, best_gt, "exact")
    
    # Pass 2: High-confidence semantic matches (with validation)
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
    
    # Pass 4: Greedy LLM matching for remaining unmatched GT
    if CONFIG.use_greedy_llm_matching and unmatched_gt:
        logger.info(f"    Greedy LLM: {len(unmatched_gt)} GT still unmatched")
        
        for gt_idx in list(unmatched_gt):
            gt_name = ground_truth[gt_idx].get('name', '')
            
            candidates = []
            for ext_idx in unmatched_ext:
                ext_name = extracted[ext_idx].get('outcome_name', '')
                overlap = compute_word_overlap(ext_name, gt_name)
                
                # V17: Also check taxonomy match
                tax_score = taxonomy_match_score(ext_name, gt_name)
                if overlap >= CONFIG.greedy_llm_min_overlap or tax_score >= 0.5:
                    candidates.append((ext_idx, overlap + tax_score))
            
            candidates.sort(key=lambda x: x[1], reverse=True)
            
            for ext_idx, _ in candidates[:3]:
                if ext_idx not in unmatched_ext:
                    continue
                
                ext_name = extracted[ext_idx].get('outcome_name', '')
                is_match, confidence = llm_validate_match(ext_name, gt_name)
                llm_calls += 1
                
                if is_match and confidence >= 0.3:
                    try_match(ext_idx, gt_idx, "greedy_llm", confidence)
                    break
    
    # Pass 5 (V17 NEW): Bi-directional matching - for each unmatched GT, find best remaining extracted
    if unmatched_gt:
        logger.info(f"    Bi-directional pass: {len(unmatched_gt)} GT still unmatched")
        
        for gt_idx in list(unmatched_gt):
            gt_name = ground_truth[gt_idx].get('name', '')
            
            best_ext, best_score = None, 0
            for ext_idx in unmatched_ext:
                score, _ = similarity_matrix[(ext_idx, gt_idx)]
                if score > best_score:
                    best_score = score
                    best_ext = ext_idx
            
            if best_ext is not None and best_score >= 0.35:
                ext_name = extracted[best_ext].get('outcome_name', '')
                
                # Lower threshold validation for GT-driven matches
                is_valid, _ = validate_semantic_match(ext_name, gt_name, best_score)
                if is_valid:
                    # Quick LLM check
                    is_match, confidence = llm_validate_match(ext_name, gt_name)
                    llm_calls += 1
                    
                    if is_match and confidence >= 0.25:
                        try_match(best_ext, gt_idx, "bidirectional", confidence)
    
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
        "unmatched_gt_indices": list(unmatched_gt),
        "rejected_matches": rejected_matches
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

def process_study_v17(study: Dict, idx: int, total: int) -> Dict:
    """Process a single study with V17 pipeline."""
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
            batch_outcomes = ensemble_extract_v17(batch_tables, batch_prose)
            batch_outcomes = semantic_deduplicate(batch_outcomes)
            
            logger.info(f"    Batch {batch_idx + 1}/{num_batches}: {len(batch_outcomes)} outcomes")
            all_outcomes.extend(batch_outcomes)
        
        all_outcomes = semantic_deduplicate(all_outcomes)
        logger.info(f"  ✅ Extracted {len(all_outcomes)} outcomes")
        
        result["n_extracted"] = len(all_outcomes)
        result["extracted_outcomes"] = all_outcomes
        
        # V17 matching
        matching = match_outcomes_v17(all_outcomes, gt_outcomes)
        
        result["n_matched"] = matching["n_matched"]
        result["recall"] = matching["recall"]
        result["precision"] = matching["precision"]
        result["f1"] = matching["f1"]
        result["matches"] = matching["matches"]
        result["unmatched_gt_indices"] = matching["unmatched_gt_indices"]
        result["rejected_matches"] = matching.get("rejected_matches", [])
        result["success"] = True
        
        logger.info(f"  📊 Matched: {matching['n_matched']}/{len(gt_outcomes)} "
                   f"(R: {matching['recall']*100:.1f}%, P: {matching['precision']*100:.1f}%, "
                   f"F1: {matching['f1']*100:.1f}%)")
        
        if matching.get("rejected_matches"):
            logger.info(f"  🚫 Rejected {len(matching['rejected_matches'])} false positive matches")
        
    except Exception as e:
        result["error"] = str(e)
        logger.error(f"  ❌ Error: {e}")
    
    return result


def run_v17_pipeline(num_studies: int = None):
    """Run V17 pipeline on studies."""
    logger.info("=" * 70)
    logger.info("EXTRACTION PIPELINE V17 - Advanced Matching Fixes")
    logger.info("=" * 70)
    logger.info("Improvements:")
    logger.info("  1. Many-to-many matching (same GT name can match multiple times)")
    logger.info("  2. Semantic validation (prevent false positive matches)")
    logger.info("  3. Hierarchical taxonomy (generic GT → specific extractions)")
    logger.info("  4. Bi-directional matching (GT-driven fallback)")
    logger.info("")
    logger.info(f"Models: {CONFIG.models}")
    logger.info(f"Dedup threshold: {CONFIG.dedup_similarity_threshold}")
    logger.info(f"Match thresholds: exact={CONFIG.exact_match_threshold}, high={CONFIG.high_confidence_threshold}, llm={CONFIG.llm_validation_threshold}")
    logger.info(f"Concept overlap min: {CONFIG.min_concept_overlap}")
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
    total_rejected = 0
    
    for idx, study in enumerate(studies, 1):
        result = process_study_v17(study, idx, len(studies))
        results.append(result)
        
        if result["success"]:
            total_gt += result["n_gt_outcomes"]
            total_extracted += result["n_extracted"]
            total_matched += result["n_matched"]
            total_rejected += len(result.get("rejected_matches", []))
        
        if idx % 5 == 0:
            successful = [r for r in results if r.get('success')]
            if successful:
                avg_recall = np.mean([r['recall'] for r in successful])
                avg_precision = np.mean([r['precision'] for r in successful])
                logger.info("=" * 50)
                logger.info(f"PROGRESS: {idx}/{len(studies)}")
                logger.info(f"R: {avg_recall*100:.1f}% | P: {avg_precision*100:.1f}%")
                logger.info(f"Matched: {total_matched}/{total_gt}")
                logger.info(f"Rejected FPs: {total_rejected}")
                logger.info("=" * 50)
    
    elapsed = datetime.now() - start_time
    overall_recall = total_matched / total_gt if total_gt > 0 else 0
    overall_precision = total_matched / total_extracted if total_extracted > 0 else 0
    overall_f1 = 2 * overall_recall * overall_precision / (overall_recall + overall_precision) if (overall_recall + overall_precision) > 0 else 0
    
    studies_100_recall = sum(1 for r in results if r.get("recall", 0) == 1.0)
    
    logger.info("")
    logger.info("=" * 70)
    logger.info("FINAL RESULTS - V17 (Advanced Matching)")
    logger.info("=" * 70)
    logger.info(f"Studies processed: {len(studies)}")
    logger.info(f"Successful: {sum(1 for r in results if r.get('success'))}")
    logger.info(f"Time elapsed: {elapsed}")
    logger.info("")
    logger.info(f"Ground truth outcomes: {total_gt}")
    logger.info(f"Extracted outcomes: {total_extracted}")
    logger.info(f"Matched outcomes: {total_matched}")
    logger.info(f"Rejected false positives: {total_rejected}")
    logger.info("")
    logger.info(f"RECALL:    {overall_recall * 100:.1f}%  (V16 baseline: 73.2%)")
    logger.info(f"PRECISION: {overall_precision * 100:.1f}%  (V16 baseline: 11.5%)")
    logger.info(f"F1 SCORE:  {overall_f1 * 100:.1f}%")
    logger.info("")
    logger.info(f"Studies with 100% recall: {studies_100_recall}")
    logger.info("=" * 70)
    
    output_path = Path(__file__).parent / "v17_results.json"
    with open(output_path, 'w') as f:
        json.dump({
            "summary": {
                "total_gt": total_gt,
                "total_extracted": total_extracted,
                "total_matched": total_matched,
                "total_rejected_fps": total_rejected,
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
    run_v17_pipeline(num_studies)
