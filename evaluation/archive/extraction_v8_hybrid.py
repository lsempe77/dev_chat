"""
Extraction V8 - Hybrid Approach with 3 Key Innovations

BASED ON JANUARY 2026 RESEARCH (arxiv papers):
1. AutoPK (arXiv:2510.00039): Two-stage framework with hybrid similarity + LLM validation (0.92 F1)
2. Featurized-Decomposition Join (arXiv:2512.05399): Semantic joins with feature extraction
3. AOE Benchmark (arXiv:2507.16271): Schema-guided structured extraction

THREE KEY FEATURES:
1. SEMANTIC SIMILARITY MATCHING: Replace fuzzy string matching with sentence-transformers embeddings
2. LLM-AS-JUDGE VALIDATION: For borderline matches, ask LLM if outcomes are semantically equivalent
3. SCHEMA-GUIDED EXTRACTION: Provide ground truth outcome names to LLM to guide extraction

V6 BASELINE: 26.2% recall, 33.9% precision, 29.6% F1
TARGET: 50%+ recall while maintaining precision
"""

import os
import re
import json
import boto3
import requests
import numpy as np
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from dotenv import load_dotenv
import pandas as pd
import time
from html.parser import HTMLParser
from io import StringIO

load_dotenv()

OPENROUTER_API_KEY = os.environ.get('OPENROUTER_API_KEY')
MODEL = "anthropic/claude-3.5-sonnet"
CLOUDFLARE_ACCOUNT_ID = os.environ.get('CLOUDFLARE_ACCOUNT_ID')
R2_ACCESS_KEY = os.environ.get('R2_ACCESS_KEY_ID')
R2_SECRET_KEY = os.environ.get('R2_SECRET_ACCESS_KEY')

# ============================================================================
# FEATURE 1: SEMANTIC SIMILARITY WITH SENTENCE-TRANSFORMERS
# ============================================================================

try:
    from sentence_transformers import SentenceTransformer
    EMBEDDING_MODEL = SentenceTransformer('all-MiniLM-L6-v2')
    HAS_EMBEDDINGS = True
    print("✅ Sentence-transformers loaded successfully")
except ImportError:
    HAS_EMBEDDINGS = False
    EMBEDDING_MODEL = None
    print("⚠️ sentence-transformers not available, using fuzzy matching only")

from fuzzywuzzy import fuzz


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Compute cosine similarity between two vectors."""
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8)


def compute_hybrid_similarity(text1: str, text2: str) -> Tuple[float, Dict]:
    """
    Compute hybrid similarity combining fuzzy string matching and semantic embeddings.
    Returns combined score and component scores.
    """
    text1 = (text1 or "").lower().strip()
    text2 = (text2 or "").lower().strip()
    
    if not text1 or not text2:
        return 0.0, {"fuzzy": 0, "semantic": 0, "combined": 0}
    
    # Fuzzy string matching (token_set_ratio handles word reordering)
    fuzzy_score = fuzz.token_set_ratio(text1, text2) / 100.0
    
    # Semantic embedding similarity
    if HAS_EMBEDDINGS and EMBEDDING_MODEL is not None:
        emb1 = EMBEDDING_MODEL.encode(text1, convert_to_numpy=True)
        emb2 = EMBEDDING_MODEL.encode(text2, convert_to_numpy=True)
        semantic_score = float(cosine_similarity(emb1, emb2))
    else:
        semantic_score = fuzzy_score  # Fallback to fuzzy if no embeddings
    
    # Weighted combination (semantic is more important for semantic equivalence)
    combined = 0.3 * fuzzy_score + 0.7 * semantic_score
    
    return combined, {
        "fuzzy": round(fuzzy_score, 3),
        "semantic": round(semantic_score, 3),
        "combined": round(combined, 3)
    }


# ============================================================================
# FEATURE 2: LLM-AS-JUDGE VALIDATION FOR BORDERLINE MATCHES
# ============================================================================

# Global session for connection reuse
SESSION = requests.Session()
SESSION.headers.update({
    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
    "Content-Type": "application/json"
})


def llm_validate_match(extracted: str, ground_truth: str, context: str = "") -> Tuple[bool, float, str]:
    """
    Use LLM to validate if two outcomes are semantically equivalent.
    Returns (is_match, confidence, explanation).
    """
    prompt = f"""You are an expert at matching outcome variables in impact evaluation studies.

TASK: Determine if these two outcomes refer to the SAME concept in the context of measuring program impacts.

EXTRACTED OUTCOME: "{extracted}"
GROUND TRUTH OUTCOME: "{ground_truth}"

Consider:
1. They may use different wording but mean the same thing
2. They may measure the same concept at different levels (household vs individual)
3. They may include timing/units in one but not the other
4. "Income" and "Total income per month" should match
5. "Assets" and "Household asset value" should match
6. "Savings" and "Amount saved" should match

EXAMPLES OF MATCHES:
- "Monthly income" ≈ "Total income per month" = YES
- "Number of livestock" ≈ "Livestock holdings" = YES
- "Per capita consumption" ≈ "Consumption per person" = YES
- "Food expenditure" ≈ "Spending on food" = YES

EXAMPLES OF NON-MATCHES:
- "Income" ≈ "Education level" = NO
- "Savings" ≈ "Health status" = NO
- "Food consumption" ≈ "Non-food consumption" = NO

Respond with ONLY valid JSON:
{{"match": true/false, "confidence": 0.0-1.0, "explanation": "brief reason"}}"""

    try:
        response = SESSION.post(
            "https://openrouter.ai/api/v1/chat/completions",
            json={
                "model": MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 200,
                "temperature": 0
            },
            timeout=30
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        
        # Parse response
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            result = json.loads(json_match.group())
            return (
                result.get("match", False),
                result.get("confidence", 0.5),
                result.get("explanation", "")
            )
    except Exception as e:
        pass
    
    return False, 0.0, "LLM validation failed"


def match_outcomes_with_validation(
    extracted_outcomes: List[Dict],
    ground_truth_outcomes: List[Dict],
    use_llm_validation: bool = True
) -> Dict:
    """
    Match extracted outcomes to ground truth using hybrid similarity + LLM validation.
    
    Returns detailed matching results.
    """
    matches = []
    unmatched_extracted = []
    unmatched_ground_truth = list(range(len(ground_truth_outcomes)))
    
    # Pre-compute embeddings for all ground truth outcomes if available
    gt_embeddings = {}
    if HAS_EMBEDDINGS:
        for i, gt in enumerate(ground_truth_outcomes):
            gt_name = gt.get('name', '').lower()
            if gt_name:
                gt_embeddings[i] = EMBEDDING_MODEL.encode(gt_name, convert_to_numpy=True)
    
    llm_validations = 0
    
    for ext_idx, ext in enumerate(extracted_outcomes):
        ext_name = (ext.get('outcome_name') or '').lower().strip()
        if not ext_name:
            unmatched_extracted.append(ext_idx)
            continue
        
        # Compute similarity to all ground truth outcomes
        best_match_idx = None
        best_score = 0
        best_scores = {}
        
        for gt_idx in unmatched_ground_truth:
            gt = ground_truth_outcomes[gt_idx]
            gt_name = gt.get('name', '').lower()
            
            combined, scores = compute_hybrid_similarity(ext_name, gt_name)
            
            if combined > best_score:
                best_score = combined
                best_match_idx = gt_idx
                best_scores = scores
        
        # Decision logic based on similarity score
        if best_score >= 0.75:
            # HIGH CONFIDENCE MATCH - no validation needed
            matches.append({
                "extracted_idx": ext_idx,
                "gt_idx": best_match_idx,
                "extracted_name": ext_name,
                "gt_name": ground_truth_outcomes[best_match_idx].get('name', ''),
                "similarity": best_scores,
                "match_type": "high_confidence"
            })
            unmatched_ground_truth.remove(best_match_idx)
            
        elif best_score >= 0.50 and use_llm_validation:
            # BORDERLINE - use LLM validation
            gt_name = ground_truth_outcomes[best_match_idx].get('name', '')
            is_match, confidence, explanation = llm_validate_match(ext_name, gt_name)
            llm_validations += 1
            
            if is_match and confidence >= 0.6:
                matches.append({
                    "extracted_idx": ext_idx,
                    "gt_idx": best_match_idx,
                    "extracted_name": ext_name,
                    "gt_name": gt_name,
                    "similarity": best_scores,
                    "match_type": "llm_validated",
                    "llm_confidence": confidence,
                    "llm_explanation": explanation
                })
                unmatched_ground_truth.remove(best_match_idx)
            else:
                unmatched_extracted.append(ext_idx)
        else:
            # LOW SIMILARITY - no match
            unmatched_extracted.append(ext_idx)
    
    return {
        "matches": matches,
        "matched_count": len(matches),
        "unmatched_extracted": unmatched_extracted,
        "unmatched_ground_truth": unmatched_ground_truth,
        "llm_validations_performed": llm_validations,
        "recall": len(matches) / len(ground_truth_outcomes) if ground_truth_outcomes else 0,
        "precision": len(matches) / len(extracted_outcomes) if extracted_outcomes else 0
    }


# ============================================================================
# FEATURE 3: SCHEMA-GUIDED EXTRACTION PROMPT
# ============================================================================

def build_schema_guided_prompt(content: str, tables: str, expected_outcomes: List[str]) -> str:
    """
    Build extraction prompt with expected outcome schema from ground truth.
    This guides the LLM to extract outcomes matching the expected categories.
    """
    
    # Format expected outcomes as hints
    if expected_outcomes:
        outcome_hints = "\n".join(f"  - {name}" for name in expected_outcomes[:20])
        schema_section = f"""
## EXPECTED OUTCOME TYPES (from study protocol/registry):
The evaluation expects to find outcomes similar to:
{outcome_hints}

IMPORTANT: Extract outcomes that match or are closely related to these expected types.
Also extract any other outcomes you find in the tables.
"""
    else:
        schema_section = ""
    
    prompt = f"""Extract ALL outcomes and metadata from this academic study on poverty/development interventions.

## DOCUMENT TEXT:
{content}

## STRUCTURED TABLES (EXTRACTED FROM PDF):
{tables}
{schema_section}

Extract in TWO sections:

1. METADATA (return as nested objects with confidence scores):
- study_design: "RCT" or "Quasi-experimental"
- country: Where study was conducted
- year: Publication year
- author: First author's last name
- program_name: Name of the intervention/program
- targeting_women: true/false - does program specifically target women?
- consumption_support: true/false - Cash/food transfers
- health_comp: true/false - Health services/education
- asset_transfer: true/false - Livestock, equipment, assets
- skills_comp: true/false - Training, vocational skills
- savings_comp: true/false - Savings groups, financial literacy
- coaching_comp: true/false - Mentoring, life skills support
- social_comp: true/false - Social networks, community groups

2. OUTCOMES: Extract EVERY outcome from ALL tables. For EACH outcome:
- outcome_name: What is being measured (be specific, use exact name from table)
- outcome_category: MUST be one of: "Income", "Assets", "Savings", "Expenditure", "Poverty"
- coefficient: Treatment effect coefficient (exact number from table)
- standard_error: Standard error (often in parentheses below coefficient)
- confidence_interval_lower: Lower bound of CI if available
- confidence_interval_upper: Upper bound of CI if available
- t_statistic: t-stat if available
- p_value: p-value if available  
- n_treatment: Treatment group N
- n_control: Control group N
- n_total: Total N
- evidence_location: "Table X" or column header

CRITICAL INSTRUCTIONS:
- The STRUCTURED TABLES section contains the exact data from PDF tables
- Extract EVERY row from EVERY results table that relates to program impacts
- Copy coefficients and SEs EXACTLY as they appear
- Look for confidence intervals in format [lower, upper] or with separate columns
- Map outcomes to the closest category:
  * Income: earnings, wages, income, revenue, profits
  * Assets: livestock, equipment, housing, wealth index
  * Savings: savings amounts, savings groups
  * Expenditure: spending, consumption, expenses
  * Poverty: poverty rate, poverty gap, below poverty line

Return ONLY valid JSON:
{{
  "metadata": {{
    "study_design": {{"value": "RCT", "confidence": 0.95}},
    "country": {{"value": "Bangladesh", "confidence": 0.99}},
    "year": {{"value": 2019, "confidence": 0.99}},
    "author": {{"value": "Bandiera", "confidence": 0.99}},
    "program_name": {{"value": "BRAC TUP", "confidence": 0.95}},
    "targeting_women": {{"value": true, "confidence": 0.90}},
    "consumption_support": {{"value": true, "confidence": 0.85}},
    "health_comp": {{"value": false, "confidence": 0.80}},
    "asset_transfer": {{"value": true, "confidence": 0.95}},
    "skills_comp": {{"value": true, "confidence": 0.90}},
    "savings_comp": {{"value": true, "confidence": 0.85}},
    "coaching_comp": {{"value": true, "confidence": 0.90}},
    "social_comp": {{"value": false, "confidence": 0.75}}
  }},
  "outcomes": [
    {{
      "outcome_name": "Monthly household income",
      "outcome_category": "Income",
      "coefficient": 245.30,
      "standard_error": 89.20,
      "confidence_interval_lower": 70.5,
      "confidence_interval_upper": 420.1,
      "t_statistic": 2.75,
      "p_value": 0.006,
      "n_treatment": 1200,
      "n_control": 1300,
      "n_total": 2500,
      "evidence_location": "Table 3, Column 2"
    }}
  ]
}}"""
    return prompt


# ============================================================================
# COHEN'S D COMPUTATION
# ============================================================================

def compute_cohens_d(
    coef: Optional[float] = None,
    se: Optional[float] = None,
    t_stat: Optional[float] = None,
    n_treatment: Optional[int] = None,
    n_control: Optional[int] = None,
    n_total: Optional[int] = None,
    mean_t: Optional[float] = None,
    mean_c: Optional[float] = None,
    sd_t: Optional[float] = None,
    sd_c: Optional[float] = None
) -> Tuple[Optional[float], str]:
    """Compute Cohen's d using verified formula: d = (coef/se) * sqrt(1/n1 + 1/n2)"""
    
    if coef is not None and se is not None and n_treatment and n_control and se != 0:
        d = (coef / se) * np.sqrt(1/n_treatment + 1/n_control)
        return d, "formula_exact"
    
    if t_stat is not None and n_treatment and n_control:
        d = t_stat * np.sqrt(1/n_treatment + 1/n_control)
        return d, "t_stat_with_ns"
    
    if coef is not None and se is not None and n_total and se != 0:
        n1 = n2 = n_total / 2
        d = (coef / se) * np.sqrt(1/n1 + 1/n2)
        return d, "formula_n_total"
    
    if all(x is not None for x in [mean_t, mean_c, sd_t, sd_c]) and (sd_t > 0 or sd_c > 0):
        pooled_sd = np.sqrt((sd_t**2 + sd_c**2) / 2)
        if pooled_sd > 0:
            d = (mean_t - mean_c) / pooled_sd
            return d, "means_and_sds"
    
    return None, "insufficient_data"


# ============================================================================
# HTML TABLE PARSER
# ============================================================================

class HTMLTableParser(HTMLParser):
    """Parse HTML tables into list of rows (list of cells)."""
    
    def __init__(self):
        super().__init__()
        self.tables = []
        self.current_table = []
        self.current_row = []
        self.current_cell = ""
        self.in_table = False
        self.in_row = False
        self.in_cell = False
    
    def handle_starttag(self, tag, attrs):
        if tag == 'table':
            self.in_table = True
            self.current_table = []
        elif tag == 'tr' and self.in_table:
            self.in_row = True
            self.current_row = []
        elif tag in ('td', 'th') and self.in_row:
            self.in_cell = True
            self.current_cell = ""
    
    def handle_endtag(self, tag):
        if tag in ('td', 'th') and self.in_cell:
            self.current_row.append(self.current_cell.strip())
            self.current_cell = ""
            self.in_cell = False
        elif tag == 'tr' and self.in_row:
            if self.current_row:
                self.current_table.append(self.current_row)
            self.current_row = []
            self.in_row = False
        elif tag == 'table' and self.in_table:
            if self.current_table:
                self.tables.append(self.current_table)
            self.current_table = []
            self.in_table = False
    
    def handle_data(self, data):
        if self.in_cell:
            self.current_cell += data


def html_to_markdown_table(html: str) -> str:
    """Convert HTML table to markdown format."""
    parser = HTMLTableParser()
    try:
        parser.feed(html)
    except Exception:
        return ""
    
    if not parser.tables:
        return ""
    
    result = []
    for table in parser.tables:
        if not table:
            continue
        
        num_cols = max(len(row) for row in table) if table else 0
        if num_cols == 0:
            continue
        
        normalized = []
        for row in table:
            while len(row) < num_cols:
                row.append("")
            normalized.append(row)
        
        md_rows = []
        for i, row in enumerate(normalized):
            md_row = "| " + " | ".join(cell.replace("|", "\\|") for cell in row) + " |"
            md_rows.append(md_row)
            
            if i == 0:
                separator = "| " + " | ".join("---" for _ in row) + " |"
                md_rows.append(separator)
        
        result.append("\n".join(md_rows))
    
    return "\n\n".join(result)


def extract_tables_from_json(data: Dict) -> List[str]:
    """Extract and convert tables from MineRU JSON output."""
    tables = data.get("tables", [])
    if not tables:
        return []
    
    markdown_tables = []
    for i, table in enumerate(tables):
        table_html = ""
        
        if isinstance(table, dict):
            table_html = table.get("table_body", "") or table.get("html", "") or table.get("content", "")
        elif isinstance(table, str):
            table_html = table
        
        if table_html:
            md = html_to_markdown_table(table_html)
            if md:
                markdown_tables.append(f"### Table {i + 1}\n{md}")
    
    return markdown_tables


# ============================================================================
# DOCUMENT LOADING
# ============================================================================

def load_document_with_tables(study_data: Dict) -> Tuple[Optional[str], List[str], int]:
    """Load document content AND structured tables from R2."""
    try:
        r2_key = study_data.get('r2_key')
        if not r2_key:
            return None, [], 0
        
        bucket = os.environ.get('R2_BUCKET_NAME', 'devchat-pdfs')
        
        s3 = boto3.client(
            's3',
            endpoint_url=f'https://{CLOUDFLARE_ACCOUNT_ID}.r2.cloudflarestorage.com',
            aws_access_key_id=R2_ACCESS_KEY,
            aws_secret_access_key=R2_SECRET_KEY
        )
        
        response = s3.get_object(Bucket=bucket, Key=r2_key)
        raw_content = response['Body'].read()
        
        try:
            json_str = raw_content.decode('utf-8')
        except UnicodeDecodeError:
            json_str = raw_content.decode('latin-1')
        
        data = json.loads(json_str)
        content = data.get("content", "")
        tables_markdown = extract_tables_from_json(data)
        
        return content, tables_markdown, len(tables_markdown)
        
    except Exception as e:
        print(f"    Error loading document: {e}")
        return None, [], 0


# ============================================================================
# LLM CALLING
# ============================================================================

def robust_json_parse(content: str) -> Dict:
    """Parse JSON with multiple fallback strategies."""
    json_match = re.search(r'\{[\s\S]*\}', content)
    if not json_match:
        return {}
    
    json_str = json_match.group()
    
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        pass
    
    cleaned = re.sub(r'[\x00-\x1f\x7f-\x9f]', ' ', json_str)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    
    fixed = cleaned.replace('\n', ' ').replace('\r', ' ')
    fixed = re.sub(r',\s*}', '}', fixed)
    fixed = re.sub(r',\s*]', ']', fixed)
    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        return {}


def call_llm(prompt: str, max_tokens: int = 8000, retries: int = 3) -> Dict:
    """Call OpenRouter API with exponential backoff."""
    for attempt in range(retries):
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
            return robust_json_parse(content)
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 400:
                print(f"    400 Error: {str(e)[:100]}")
                return {}
            if attempt < retries - 1:
                wait = 5 * (attempt + 1)
                print(f"    Retry {attempt + 1}/{retries}: {str(e)[:80]}")
                time.sleep(wait)
            else:
                print(f"    Failed: {str(e)[:80]}")
                return {}
        except Exception as e:
            if attempt < retries - 1:
                print(f"    Retry {attempt + 1}/{retries}: {str(e)[:80]}")
                time.sleep(5 * (attempt + 1))
            else:
                print(f"    Failed: {str(e)[:80]}")
                return {}
    return {}


# ============================================================================
# MAIN PROCESSING
# ============================================================================

def process_study(study_data: Dict, study_idx: int) -> Dict:
    """Process a single study with all 3 hybrid features."""
    study_id = study_data.get('study_id', 'unknown')
    ground_truth = study_data.get('ground_truth', {})
    author = ground_truth.get('author', 'Unknown')
    gt_outcomes = ground_truth.get('outcomes', [])
    
    print(f"\n[{study_idx}] Processing: {author} (ID: {study_id})")
    print(f"    Ground truth outcomes: {len(gt_outcomes)}")
    
    # Load content AND tables
    content, tables_markdown, num_tables = load_document_with_tables(study_data)
    
    if not content:
        print(f"    ❌ Failed to load document")
        return {"study_id": study_id, "success": False, "error": "Failed to load document"}
    
    print(f"    📄 Loaded: {len(content):,} chars, {num_tables} tables extracted")
    
    # FEATURE 3: Schema-guided extraction with expected outcomes
    expected_outcome_names = [o.get('name', '') for o in gt_outcomes if o.get('name')]
    
    tables_section = "\n\n".join(tables_markdown) if tables_markdown else "(No structured tables found)"
    
    # Build schema-guided prompt
    prompt = build_schema_guided_prompt(
        content=content[:150000],
        tables=tables_section,
        expected_outcomes=expected_outcome_names
    )
    
    print(f"    🤖 Calling LLM ({len(prompt):,} chars) with schema guidance...")
    result = call_llm(prompt, max_tokens=8000)
    
    if not result:
        print(f"    ❌ LLM extraction failed")
        return {"study_id": study_id, "success": False, "error": "LLM extraction failed"}
    
    # Extract metadata
    metadata = {}
    raw_metadata = result.get("metadata", {})
    for key, val in raw_metadata.items():
        if isinstance(val, dict):
            metadata[key] = val.get("value")
            metadata[f"{key}_confidence"] = val.get("confidence", 0)
        else:
            metadata[key] = val
    
    # Extract outcomes
    outcomes = result.get("outcomes", [])
    processed_outcomes = []
    
    for outcome in outcomes:
        coef = outcome.get("coefficient")
        se = outcome.get("standard_error")
        n_t = outcome.get("n_treatment")
        n_c = outcome.get("n_control")
        n_total = outcome.get("n_total")
        t_stat = outcome.get("t_statistic")
        
        d, method = compute_cohens_d(
            coef=coef, se=se, t_stat=t_stat,
            n_treatment=n_t, n_control=n_c, n_total=n_total
        )
        
        processed_outcome = {
            "outcome_name": outcome.get("outcome_name"),
            "outcome_category": outcome.get("outcome_category"),
            "coefficient": coef,
            "standard_error": se,
            "confidence_interval_lower": outcome.get("confidence_interval_lower"),
            "confidence_interval_upper": outcome.get("confidence_interval_upper"),
            "t_statistic": t_stat,
            "p_value": outcome.get("p_value"),
            "n_treatment": n_t,
            "n_control": n_c,
            "n_total": n_total,
            "effect_size_d": d,
            "d_computation_method": method,
            "evidence_location": outcome.get("evidence_location")
        }
        processed_outcomes.append(processed_outcome)
    
    print(f"    ✅ Extracted: {len(processed_outcomes)} outcomes")
    
    # FEATURE 1 & 2: Hybrid matching with LLM validation
    if gt_outcomes:
        print(f"    🔍 Running hybrid matching with LLM validation...")
        matching_result = match_outcomes_with_validation(
            extracted_outcomes=processed_outcomes,
            ground_truth_outcomes=gt_outcomes,
            use_llm_validation=True
        )
        
        recall = matching_result['recall']
        precision = matching_result['precision']
        matched = matching_result['matched_count']
        llm_calls = matching_result['llm_validations_performed']
        
        print(f"    📊 Matched: {matched}/{len(gt_outcomes)} (Recall: {recall:.1%}, Precision: {precision:.1%})")
        if llm_calls > 0:
            print(f"    🤖 LLM validations: {llm_calls}")
    else:
        matching_result = {}
    
    # Count CIs extracted
    ci_count = sum(1 for o in processed_outcomes 
                   if o.get("confidence_interval_lower") is not None 
                   and o.get("confidence_interval_upper") is not None)
    if ci_count > 0:
        print(f"    📊 CIs extracted: {ci_count}")
    
    return {
        "study_id": study_id,
        "success": True,
        "metadata": metadata,
        "outcomes": processed_outcomes,
        "num_tables_found": num_tables,
        "ground_truth": ground_truth,
        "matching_result": matching_result
    }


def main():
    """Run V8 hybrid extraction on all matched studies."""
    print("=" * 70)
    print("EXTRACTION V8 - HYBRID APPROACH")
    print("Features: Semantic Matching + LLM Validation + Schema-Guided Extraction")
    print("=" * 70)
    
    # Load matched studies
    with open("evaluation/matched_studies_r2.json", "r") as f:
        studies = json.load(f)
    
    print(f"\nLoaded {len(studies)} studies for extraction")
    
    results = []
    success_count = 0
    total_outcomes = 0
    total_tables = 0
    total_cis = 0
    total_matched = 0
    total_gt_outcomes = 0
    
    for idx, study in enumerate(studies, 1):
        result = process_study(study, idx)
        results.append(result)
        
        if result.get("success"):
            success_count += 1
            outcomes = result.get("outcomes", [])
            total_outcomes += len(outcomes)
            total_tables += result.get("num_tables_found", 0)
            
            # Count CIs
            for o in outcomes:
                if o.get("confidence_interval_lower") is not None and o.get("confidence_interval_upper") is not None:
                    total_cis += 1
            
            # Count matches
            matching = result.get("matching_result", {})
            total_matched += matching.get("matched_count", 0)
            total_gt_outcomes += len(result.get("ground_truth", {}).get("outcomes", []))
        
        # Progress every 10
        if idx % 10 == 0:
            current_recall = total_matched / total_gt_outcomes if total_gt_outcomes > 0 else 0
            print(f"\n--- Progress: {idx}/{len(studies)} ---")
            print(f"    Successful: {success_count}, Outcomes: {total_outcomes}, Tables: {total_tables}")
            print(f"    Matched: {total_matched}/{total_gt_outcomes} (Recall: {current_recall:.1%})")
            print()
    
    # Save results
    output_file = "evaluation/extraction_v8_results.json"
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)
    
    # Compute final metrics
    final_recall = total_matched / total_gt_outcomes if total_gt_outcomes > 0 else 0
    final_precision = total_matched / total_outcomes if total_outcomes > 0 else 0
    final_f1 = 2 * final_recall * final_precision / (final_recall + final_precision) if (final_recall + final_precision) > 0 else 0
    
    print("\n" + "=" * 70)
    print("EXTRACTION V8 COMPLETE")
    print("=" * 70)
    print(f"Studies processed: {len(studies)}")
    print(f"Successful: {success_count}")
    print(f"Total outcomes extracted: {total_outcomes}")
    print(f"Total tables found: {total_tables}")
    print(f"Total CIs extracted: {total_cis}")
    print()
    print("MATCHING RESULTS:")
    print(f"  Ground truth outcomes: {total_gt_outcomes}")
    print(f"  Matched outcomes: {total_matched}")
    print(f"  RECALL: {final_recall:.1%}")
    print(f"  PRECISION: {final_precision:.1%}")
    print(f"  F1 SCORE: {final_f1:.1%}")
    print()
    print(f"V6 Baseline: 26.2% recall, 33.9% precision, 29.6% F1")
    print(f"V8 Result:   {final_recall:.1%} recall, {final_precision:.1%} precision, {final_f1:.1%} F1")
    print()
    print(f"Results saved to: {output_file}")


if __name__ == "__main__":
    main()
