"""
V15 Extraction Pipeline - Multi-Model Comparison (January 2026)

Tests the latest models to find the best performer for outcome extraction:
- OpenAI: GPT-4.5, GPT-4o, o1
- Anthropic: Claude 3.5 Sonnet, Claude 3 Opus
- Google: Gemini 2.0 Flash, Gemini 1.5 Pro
- Mistral: Mistral Large, Mistral Medium
- Open-source: DeepSeek V3, Llama 3.3

Each text goes to ONE model only (no duplication).
Runs each model on the same 5 test studies for fair comparison.
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
import logging
from dataclasses import dataclass, field
from pathlib import Path

# Local imports
from preprocess import preprocess_mineru_table, ParsedTable

load_dotenv()

# ============================================================================
# CONFIGURATION
# ============================================================================

@dataclass
class Config:
    """Pipeline configuration for V15."""
    
    # Models to test - January 2026 verified working on OpenRouter
    # Ordered by speed: fast models first for quicker feedback
    models_to_test: List[str] = field(default_factory=lambda: [
        # Fast - reliable, quick responses
        "openai/gpt-4o",                     # GPT-4o (fast, reliable)
        "anthropic/claude-3.5-sonnet",       # Claude 3.5 Sonnet (fast)
        "google/gemini-2.5-flash",           # Gemini 2.5 Flash (fast)
        "deepseek/deepseek-chat",            # DeepSeek V3 (good balance)
        "mistralai/mistral-large-2411",      # Mistral Large (fast)
        # Medium - may be slower
        "anthropic/claude-sonnet-4.5",       # Claude Sonnet 4.5 (newer)
        "x-ai/grok-code-fast-1",             # Grok Code Fast
        # Slow - skip for now
        # "qwen/qwen3-235b-a22b-2507",       # Very slow, skip
    ])
    
    max_tokens_extraction: int = 32000
    temperature: float = 0.0
    
    # Matching thresholds
    exact_match_threshold: float = 0.90
    high_confidence_threshold: float = 0.45
    
    # Table processing
    max_tables_per_batch: int = 10
    min_table_rows: int = 2
    
    # Processing
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
    replacements = {
        " hh ": " household ",
        "pcc": "per capita consumption",
        "cons.": "consumption",
        "expend.": "expenditure",
    }
    for old, new in replacements.items():
        name = name.replace(old, new)
    name = re.sub(r'[^\w\s]', ' ', name)
    name = re.sub(r'\s+', ' ', name)
    return name.strip()


def compute_similarity(ext_name: str, gt_name: str) -> float:
    """Compute hybrid similarity between two outcome names."""
    ext_norm = normalize_outcome_name(ext_name)
    gt_norm = normalize_outcome_name(gt_name)
    
    if not ext_norm or not gt_norm:
        return 0.0
    
    # Exact match
    if ext_norm == gt_norm:
        return 1.0
    
    # Containment check
    if len(gt_norm) >= 4 and gt_norm in ext_norm:
        return 0.85
    
    scores = []
    
    # Semantic similarity
    if HAS_EMBEDDINGS and EMBEDDING_MODEL:
        try:
            emb = EMBEDDING_MODEL.encode([ext_norm, gt_norm])
            semantic_score = cosine_similarity(emb[0], emb[1])
            scores.append(semantic_score)
        except:
            pass
    
    # Fuzzy matching
    if HAS_FUZZY:
        token_score = fuzz.token_set_ratio(ext_norm, gt_norm) / 100.0
        scores.append(token_score)
    
    return max(scores) if scores else 0.0


# ============================================================================
# EXTRACTION PROMPT
# ============================================================================

EXTRACTION_PROMPT = """You are an expert research assistant analyzing impact evaluation tables.

TASK: Extract ALL outcome variables with their effect sizes from these tables.

For each outcome, extract:
1. outcome_name: The outcome variable name (be comprehensive, include full description)
2. literal_text: The exact text from the table row
3. table_source: Which table it came from
4. coefficient: The effect size/coefficient
5. standard_error: The SE if available

RULES:
1. Extract EVERY outcome that has a coefficient/effect size
2. Multiple columns = extract EACH as separate outcome
3. Include the base outcome AND variants (e.g., "consumption" AND "food consumption")
4. Be exhaustive - more is better than fewer

TABLES:
{tables}

OUTPUT: Return ONLY valid JSON:
{{
  "outcomes": [
    {{
      "outcome_name": "Household consumption",
      "literal_text": "Household consumption | 0.128*** | (0.041)",
      "table_source": "Table 3",
      "coefficient": 0.128,
      "standard_error": 0.041
    }}
  ]
}}
"""


def call_llm(model: str, prompt: str) -> Tuple[Optional[str], float, Optional[str]]:
    """Call LLM via OpenRouter. Returns (response, latency_seconds, error)."""
    start_time = time.time()
    
    for attempt in range(CONFIG.retry_attempts):
        try:
            response = SESSION.post(
                "https://openrouter.ai/api/v1/chat/completions",
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": CONFIG.max_tokens_extraction,
                    "temperature": CONFIG.temperature,
                },
                timeout=180  # 3 minutes max
            )
            
            latency = time.time() - start_time
            
            if response.status_code == 200:
                data = response.json()
                content = data["choices"][0]["message"]["content"]
                return content, latency, None
            elif response.status_code == 429:
                logger.warning(f"Rate limited, waiting...")
                time.sleep(CONFIG.retry_delay * (attempt + 1))
            elif response.status_code == 404:
                return None, latency, f"Model not found: {model}"
            else:
                error_text = response.text[:200]
                return None, latency, f"API error {response.status_code}: {error_text}"
                
        except requests.exceptions.Timeout:
            return None, time.time() - start_time, "Timeout"
        except Exception as e:
            if attempt < CONFIG.retry_attempts - 1:
                time.sleep(CONFIG.retry_delay)
            else:
                return None, time.time() - start_time, str(e)
    
    return None, time.time() - start_time, "Max retries exceeded"


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


def load_document(r2_key: str) -> Tuple[str, List[Dict]]:
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
                }
                parsed_tables.append(table_dict)
        
        return prose, parsed_tables
        
    except Exception as e:
        logger.error(f"Failed to load {r2_key}: {e}")
        return "", []


# ============================================================================
# MATCHING
# ============================================================================

def match_outcomes(extracted: List[Dict], ground_truth: List[Dict]) -> Dict:
    """Match extracted outcomes against ground truth."""
    matches = []
    unmatched_gt = set(range(len(ground_truth)))
    
    for ext_idx, ext in enumerate(extracted):
        ext_name = ext.get('outcome_name', '')
        
        best_gt_idx = None
        best_score = 0.0
        
        for gt_idx in unmatched_gt:
            gt_name = ground_truth[gt_idx].get('name', '')
            score = compute_similarity(ext_name, gt_name)
            
            if score > best_score:
                best_score = score
                best_gt_idx = gt_idx
        
        if best_gt_idx is not None and best_score >= CONFIG.high_confidence_threshold:
            matches.append({
                "ext_idx": ext_idx,
                "gt_idx": best_gt_idx,
                "ext_name": ext_name,
                "gt_name": ground_truth[best_gt_idx].get('name', ''),
                "score": best_score
            })
            unmatched_gt.discard(best_gt_idx)
    
    n_gt = len(ground_truth)
    n_extracted = len(extracted)
    n_matched = len(matches)
    
    return {
        "n_gt": n_gt,
        "n_extracted": n_extracted,
        "n_matched": n_matched,
        "recall": n_matched / n_gt if n_gt > 0 else 0.0,
        "precision": n_matched / n_extracted if n_extracted > 0 else 0.0,
        "matches": matches,
        "unmatched_gt": list(unmatched_gt)
    }


# ============================================================================
# MAIN TESTING FUNCTION
# ============================================================================

def test_model_on_study(model: str, tables: List[Dict], gt_outcomes: List[Dict]) -> Dict:
    """Test a single model on a single study."""
    result = {
        "model": model,
        "model_short": model.split('/')[-1],
        "success": False,
        "error": None,
        "latency": 0.0,
        "n_extracted": 0,
        "n_matched": 0,
        "recall": 0.0,
        "precision": 0.0,
    }
    
    # Build prompt
    table_content = []
    for table in tables:
        table_id = table.get("table_id", "Table")
        content = table.get("content", "")
        if content:
            table_content.append(f"\n### {table_id}\n{content[:8000]}")
    
    if not table_content:
        result["error"] = "no_tables"
        return result
    
    prompt = EXTRACTION_PROMPT.format(tables="\n".join(table_content))
    if len(prompt) > CONFIG.max_prompt_chars:
        prompt = prompt[:CONFIG.max_prompt_chars]
    
    # Call LLM
    response, latency, error = call_llm(model, prompt)
    result["latency"] = latency
    
    if error:
        result["error"] = error
        return result
    
    # Parse outcomes
    outcomes = parse_json_response(response)
    result["n_extracted"] = len(outcomes)
    
    # Match against GT
    matching = match_outcomes(outcomes, gt_outcomes)
    result["n_matched"] = matching["n_matched"]
    result["recall"] = matching["recall"]
    result["precision"] = matching["precision"]
    result["success"] = True
    
    return result


def load_ground_truth() -> List[Dict]:
    """Load ground truth from matched_studies_r2.json."""
    eval_path = Path(__file__).parent.parent / "evaluation" / "matched_studies_r2.json"
    
    if not eval_path.exists():
        logger.error(f"GT file not found: {eval_path}")
        return []
    
    with open(eval_path) as f:
        studies = json.load(f)
    
    return studies


def run_model_comparison(models: List[str] = None, n_studies: int = 5):
    """Run model comparison on N test studies."""
    models = models or CONFIG.models_to_test
    
    logger.info("="*70)
    logger.info("V15 Model Comparison - January 2026")
    logger.info(f"Testing {len(models)} models on {n_studies} studies")
    logger.info("="*70)
    
    # Load GT
    studies = load_ground_truth()
    if not studies:
        logger.error("No ground truth data")
        return
    
    # Select test studies
    studies = studies[:n_studies]
    
    # Results storage
    results = {
        "timestamp": datetime.now().isoformat(),
        "models_tested": models,
        "n_studies": len(studies),
        "model_summaries": {},
        "study_results": []
    }
    
    # Test each study
    for study_idx, study in enumerate(studies):
        # Extract study info from nested structure
        gt_data = study.get("ground_truth", {})
        study_name = f"{gt_data.get('author', 'Unknown')} ({gt_data.get('year', 'N/A')})"
        r2_key = study.get("r2_key", "")
        gt_outcomes = gt_data.get("outcomes", [])
        
        logger.info(f"\n[{study_idx+1}/{len(studies)}] {study_name} - {len(gt_outcomes)} GT outcomes")
        
        if not r2_key:
            logger.warning(f"  ⚠️ No r2_key, skipping")
            continue
        
        # Load document once
        prose, tables = load_document(r2_key)
        if not tables:
            logger.warning(f"  ⚠️ No tables found, skipping")
            continue
        
        logger.info(f"  📄 {len(tables)} tables loaded")
        
        study_results = {
            "study": study_name,
            "n_gt": len(gt_outcomes),
            "model_results": {}
        }
        
        # Test each model on this study
        for model in models:
            model_short = model.split('/')[-1]
            logger.info(f"  🔄 Testing {model_short}...")
            
            result = test_model_on_study(model, tables, gt_outcomes)
            study_results["model_results"][model_short] = result
            
            if result["success"]:
                logger.info(f"    ✅ {result['n_matched']}/{len(gt_outcomes)} "
                           f"({result['recall']*100:.1f}% recall) "
                           f"in {result['latency']:.1f}s")
            else:
                logger.warning(f"    ❌ {result['error']}")
            
            # Small delay between models
            time.sleep(0.5)
        
        results["study_results"].append(study_results)
    
    # Aggregate model performance
    logger.info("\n" + "="*70)
    logger.info("MODEL COMPARISON RESULTS")
    logger.info("="*70)
    
    for model in models:
        model_short = model.split('/')[-1]
        
        recalls = []
        precisions = []
        latencies = []
        successes = 0
        
        for study_result in results["study_results"]:
            if model_short in study_result["model_results"]:
                r = study_result["model_results"][model_short]
                if r["success"]:
                    recalls.append(r["recall"])
                    precisions.append(r["precision"])
                    latencies.append(r["latency"])
                    successes += 1
        
        if recalls:
            results["model_summaries"][model_short] = {
                "avg_recall": np.mean(recalls),
                "avg_precision": np.mean(precisions),
                "avg_latency": np.mean(latencies),
                "success_rate": successes / len(results["study_results"])
            }
            
            logger.info(f"\n{model_short}:")
            logger.info(f"  Recall: {np.mean(recalls)*100:.1f}% (avg)")
            logger.info(f"  Precision: {np.mean(precisions)*100:.1f}% (avg)")
            logger.info(f"  Latency: {np.mean(latencies):.1f}s (avg)")
            logger.info(f"  Success: {successes}/{len(results['study_results'])} studies")
    
    # Find best model
    best_model = None
    best_recall = 0.0
    for model_short, summary in results["model_summaries"].items():
        if summary["avg_recall"] > best_recall:
            best_recall = summary["avg_recall"]
            best_model = model_short
    
    if best_model:
        logger.info(f"\n🏆 BEST MODEL: {best_model} ({best_recall*100:.1f}% avg recall)")
    
    # Save results
    output_path = Path(__file__).parent / "v15_model_comparison.json"
    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    
    logger.info(f"\n📊 Results saved to {output_path}")
    
    return results


if __name__ == "__main__":
    import sys
    
    # Parse arguments
    n_studies = 5
    models = None
    
    if len(sys.argv) > 1:
        try:
            n_studies = int(sys.argv[1])
        except:
            pass
    
    # Option to test specific models from command line
    if len(sys.argv) > 2:
        models = sys.argv[2].split(",")
    
    # Default: use models from Config
    if models is None:
        models = CONFIG.models_to_test
    
    run_model_comparison(models=models, n_studies=n_studies)
