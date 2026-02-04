"""
Table Classification Pipeline v2 - LLM-First Approach

STEP 1: PARSING (Rules-based)
  - Extract all table captions from document
  - Extract surrounding context (sentences mentioning each table)
  - Match table HTML elements to captions
  - Detect continuation tables

STEP 2: CLASSIFICATION (LLM-based)
  - Send ALL tables to LLM in ONE batch call
  - Include: captions, context, table body preview
  - LLM classifies each as RESULTS / DESCRIPTIVE / SKIP

STEP 3: RECOVERY (LLM-based)
  - For SKIP/UNKNOWN tables with results indicators (stars, SE patterns)
  - Re-classify with full body content

Author: DevChat Pipeline
"""
import re
import json
import os
import sys
from dataclasses import dataclass
from typing import Optional
from bs4 import BeautifulSoup
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables at module level
load_dotenv()


# =============================================================================
# FEW-SHOT EXAMPLES for classification
# =============================================================================

FEW_SHOT_EXAMPLES = """
EXAMPLE 1:
Caption: "Table 3: Balance test - Baseline characteristics by treatment status"
Body preview: "Variable | Treatment | Control | Diff | p-value | Age | 34.2 | 33.8 | 0.4 | 0.62 | Education | 8.1 | 8.3 | -0.2 | 0.45"
Classification: DESCRIPTIVE
Reason: Balance table comparing baseline means, p-values test for pre-treatment equivalence not treatment effects.

EXAMPLE 2:
Caption: "Table 5: Impact of microfinance on household consumption"  
Body preview: "(1) | (2) | (3) | Treatment | 0.142*** | 0.138*** | 0.125** | | (0.042) | (0.041) | (0.048) | Controls | No | Yes | Yes"
Classification: RESULTS
Reason: Regression table with treatment coefficients showing causal effects on consumption.

EXAMPLE 3:
Caption: "[No caption]"
Body preview: "ANCOVA = Analysis of covariance | ATE = Average treatment effect | BCC = Behavior change | CAPI = Computer-assisted"
Classification: SKIP
Reason: Acronym definition table, not quantitative data.

EXAMPLE 4:
Caption: "Table A.12: Heterogeneous effects by gender"
Body preview: "(1) Female | (2) Male | Treatment × Female | 0.089** | | | (0.035) | | Treatment × Male | | 0.156*** | | | (0.044)"
Classification: RESULTS
Reason: Appendix table showing heterogeneous treatment effects by subgroup.

EXAMPLE 5:
Caption: "Table 2: Summary statistics"
Body preview: "Variable | N | Mean | SD | Min | Max | Income | 1,245 | 5,432 | 2,341 | 120 | 45,000"
Classification: DESCRIPTIVE
Reason: Summary statistics describing sample, no treatment effects.

EXAMPLE 6:
Caption: "[No caption]"
Body preview: "(0.045) | (0.052) | (0.048) | T1 | 0.234*** | 0.198*** | 0.212*** | T2 | 0.156** | 0.142** | 0.167**"
Classification: RESULTS
Reason: Continuation of results table with treatment coefficients and standard errors.
"""


@dataclass
class TableInfo:
    """Complete information about a table for classification."""
    index: int                 # Index in tables array
    table_number: str          # "Table 4.1", "Table A1", etc.
    caption: str               # Full caption text
    context: str               # Sentences where table is mentioned
    page_idx: int              # Page where table appears
    html_body: str             # Raw HTML (for extraction later)
    body_preview: str = ""     # Text preview of table body
    is_continuation: bool = False
    continuation_of: int = -1
    
    # Results indicators (detected from body)
    has_stars: bool = False
    has_se_pattern: bool = False
    
    # Classification (populated by LLM)
    classification: str = "UNKNOWN"  # RESULTS, DESCRIPTIVE, SKIP
    classification_reason: str = ""


class TableClassifierV2:
    """
    LLM-first table classification pipeline.
    
    Rules handle parsing/matching.
    LLM handles ALL classification decisions.
    """
    
    def __init__(self, doc: dict, study_id: str = "", verbose: bool = False):
        self.doc = doc
        self.study_id = study_id
        self.verbose = verbose
        self.content = doc.get('content', '')
        self.tables_raw = doc.get('tables', [])
        
        # Configure OpenRouter client (OpenAI-compatible)
        self.client = OpenAI(
            api_key=os.environ.get('OPENROUTER_API_KEY'),
            base_url="https://openrouter.ai/api/v1"
        )
        # Use smarter model for better classification
        self.model_name = "openai/gpt-4o"
        
        # Output
        self.tables: list[TableInfo] = []
        
    def run_pipeline(self) -> list[TableInfo]:
        """Execute full classification pipeline."""
        self._log("=" * 80)
        self._log("TABLE CLASSIFICATION PIPELINE v2 (LLM-First)")
        self._log("=" * 80)
        
        # Step 1: Parse and extract (rules-based)
        self._step1_parse_tables()
        
        # Step 2: Classify with LLM
        self._step2_classify_with_llm()
        
        # Step 3: Recovery pass for SKIP/UNKNOWN with results indicators
        self._step3_recovery_pass()
        
        return self.tables
    
    # =========================================================================
    # STEP 1: PARSING (Rules-based)
    # =========================================================================
    
    def _step1_parse_tables(self):
        """Parse all tables and extract context. Rules only - no classification."""
        self._log("\n[STEP 1] Parsing tables and extracting context...")
        
        # 1a. Extract all table mentions with context from document
        table_contexts = self._extract_table_contexts()
        
        # 1b. Parse table elements from JSON
        for i, table in enumerate(self.tables_raw):
            caption_list = table.get('table_caption', [])
            caption_field = ' '.join(caption_list).strip() if caption_list else ''
            
            # Extract body preview and detect results indicators
            body_preview = ""
            has_stars = False
            has_se_pattern = False
            
            if table.get('table_body'):
                soup = BeautifulSoup(table['table_body'], 'html.parser')
                body_text = soup.get_text(separator=' ', strip=True)
                body_preview = body_text[:400]
                
                # Detect results indicators
                has_stars = bool(re.search(r'\*{1,3}', body_text))
                # SE pattern: numbers in parentheses like (0.042) or (0.12)
                has_se_pattern = bool(re.search(r'\(\s*0?\.\d{2,4}\s*\)', body_text))
            
            # Extract table number from caption
            table_number = ""
            if caption_field:
                match = re.search(r'(Table\s+[\dA-Z]+\.?\d*[a-z]?)', caption_field, re.IGNORECASE)
                if match:
                    table_number = match.group(1)
            
            # Try to find table number in body if not in caption
            if not table_number and body_preview:
                match = re.search(r'(Table\s+[\dA-Z]+\.?\d*[a-z]?)', body_preview[:300], re.IGNORECASE)
                if match:
                    table_number = match.group(1)
            
            # Default table number
            if not table_number:
                table_number = f"Table {i+1}"
            
            # Get context for this table
            context = table_contexts.get(table_number.lower(), "")
            
            self.tables.append(TableInfo(
                index=i,
                table_number=table_number,
                caption=caption_field[:300] if caption_field else "[No caption]",
                context=context[:500] if context else "",
                page_idx=table.get('page_idx', -1),
                html_body=table.get('table_body', ''),
                body_preview=body_preview,
                has_stars=has_stars,
                has_se_pattern=has_se_pattern,
            ))
        
        # 1c. Detect continuation tables
        self._detect_continuations()
        
        self._log(f"  Parsed {len(self.tables)} tables")
        self._log(f"  With captions: {sum(1 for t in self.tables if t.caption != '[No caption]')}")
        self._log(f"  With context: {sum(1 for t in self.tables if t.context)}")
        self._log(f"  With results indicators: {sum(1 for t in self.tables if t.has_stars or t.has_se_pattern)}")
        self._log(f"  Continuations: {sum(1 for t in self.tables if t.is_continuation)}")
    
    def _extract_table_contexts(self) -> dict[str, str]:
        """Extract context sentences for each table mentioned in document."""
        contexts = {}
        
        if not self.content:
            return contexts
        
        # Find all table mentions with surrounding text
        # Capture 150 chars before and 300 after to get full sentence
        for match in re.finditer(
            r'.{0,150}(Table\s+[\dA-Z]+\.?\d*[a-z]?).{0,300}',
            self.content,
            re.IGNORECASE | re.DOTALL
        ):
            full_match = match.group(0)
            table_num = match.group(1)
            key = table_num.lower()
            
            # Accumulate all mentions of this table
            if key not in contexts:
                contexts[key] = full_match
            else:
                # Append additional context (may be mentioned multiple times)
                contexts[key] += " ... " + full_match
        
        return contexts
    
    def _detect_continuations(self):
        """Detect continuation tables based on position and text."""
        for i, table in enumerate(self.tables):
            if table.caption != '[No caption]':
                continue  # Has caption, not a continuation
            
            if i == 0:
                continue
            
            prev = self.tables[i - 1]
            
            # Rule 1: Same page as previous captioned table
            if table.page_idx == prev.page_idx and prev.caption != '[No caption]':
                table.is_continuation = True
                table.continuation_of = i - 1
                table.table_number = prev.table_number + " (cont.)"
                table.caption = f"[Continuation of {prev.table_number}]"
                continue
            
            # Rule 2: Previous was continuation - chain
            if prev.is_continuation:
                parent_idx = prev.continuation_of
                parent = self.tables[parent_idx]
                table.is_continuation = True
                table.continuation_of = parent_idx
                table.table_number = parent.table_number + " (cont.)"
                table.caption = f"[Continuation of {parent.table_number}]"
                continue
            
            # Rule 3: Check for "continued" text in body
            if table.html_body:
                soup = BeautifulSoup(table.html_body, 'html.parser')
                text = soup.get_text(separator=' ', strip=True)[:200].lower()
                if 'continued' in text or 'cont.' in text:
                    # Find most recent captioned table
                    for j in range(i - 1, -1, -1):
                        if self.tables[j].caption != '[No caption]' and not self.tables[j].is_continuation:
                            table.is_continuation = True
                            table.continuation_of = j
                            table.table_number = self.tables[j].table_number + " (cont.)"
                            table.caption = f"[Continuation of {self.tables[j].table_number}]"
                            break
    
    # =========================================================================
    # STEP 2: CLASSIFICATION (LLM-based)
    # =========================================================================
    
    def _step2_classify_with_llm(self):
        """Send all tables to LLM for classification in one batch."""
        self._log("\n[STEP 2] Classifying tables with LLM...")
        
        # Skip tables that are continuations (inherit parent classification)
        tables_to_classify = [t for t in self.tables if not t.is_continuation]
        
        if not tables_to_classify:
            self._log("  No tables to classify")
            return
        
        # Build prompt with all table info
        prompt = self._build_classification_prompt(tables_to_classify)
        
        self._log(f"  Sending {len(tables_to_classify)} tables to LLM...")
        
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
            )
            response_text = response.choices[0].message.content
            classifications = self._parse_llm_response(response_text, tables_to_classify)
            
            # Apply classifications
            for table in tables_to_classify:
                if table.index in classifications:
                    table.classification = classifications[table.index]['class']
                    table.classification_reason = classifications[table.index]['reason']
            
            # Inherit classification for continuation tables
            for table in self.tables:
                if table.is_continuation and table.continuation_of >= 0:
                    parent = self.tables[table.continuation_of]
                    table.classification = parent.classification
                    table.classification_reason = f"Continuation of {parent.table_number}"
            
        except Exception as e:
            self._log(f"  ERROR: LLM classification failed: {e}")
            # Fallback: mark all as UNKNOWN
            for table in self.tables:
                table.classification = "UNKNOWN"
                table.classification_reason = f"LLM error: {str(e)[:50]}"
        
        # Summary
        results = sum(1 for t in self.tables if t.classification == 'RESULTS')
        descriptive = sum(1 for t in self.tables if t.classification == 'DESCRIPTIVE')
        skip = sum(1 for t in self.tables if t.classification == 'SKIP')
        unknown = sum(1 for t in self.tables if t.classification == 'UNKNOWN')
        
        self._log(f"  RESULTS: {results}")
        self._log(f"  DESCRIPTIVE: {descriptive}")
        self._log(f"  SKIP: {skip}")
        self._log(f"  UNKNOWN: {unknown}")
    
    def _build_classification_prompt(self, tables: list[TableInfo]) -> str:
        """Build the LLM prompt for batch classification with few-shot examples."""
        
        # Get document title/abstract if available
        doc_context = ""
        if self.content:
            # Try to extract title (usually first line or heading)
            title_match = re.search(r'^#\s*(.+)$', self.content[:1000], re.MULTILINE)
            if title_match:
                doc_context = f"Document title: {title_match.group(1)}\n"
        
        table_list = []
        for t in tables:
            # Include body preview for better classification
            body_info = f"  Body preview: {t.body_preview[:200]}..." if t.body_preview else "  Body preview: [empty]"
            indicators = []
            if t.has_stars:
                indicators.append("has_stars")
            if t.has_se_pattern:
                indicators.append("has_SE_pattern")
            indicator_str = f"  Indicators: {', '.join(indicators)}" if indicators else "  Indicators: none"
            
            entry = f"""
TABLE {t.index} (page {t.page_idx}):
  Number: {t.table_number}
  Caption: {t.caption}
{body_info}
{indicator_str}
  Context: {t.context[:300] if t.context else '[No context in document]'}
"""
            table_list.append(entry)
        
        prompt = f"""You are an expert at analyzing impact evaluation research papers. Your task is to classify tables.

{doc_context}

=== CLASSIFICATION CATEGORIES ===

**RESULTS** - Tables with causal effect estimates:
- Treatment effect coefficients (β, ITT, ATE, LATE, TOT)
- Regression tables with treatment variables
- Difference-in-differences results
- RCT impact estimates
- Heterogeneous effects / subgroup analysis
- Robustness checks showing effects

**DESCRIPTIVE** - Tables describing data without causal claims:
- Balance tables (treatment vs control at baseline)
- Summary statistics (N, mean, SD)
- Sample characteristics
- Attrition analysis
- Compliance/take-up rates
- Data quality checks

**SKIP** - Non-data tables:
- Acronym lists, glossaries
- Variable definitions / codebooks
- Response codes (-99, -98)
- Table of contents
- Survey question lists

=== FEW-SHOT EXAMPLES ==={FEW_SHOT_EXAMPLES}
=== IMPORTANT RULES ===

1. Tables with (1), (2), (3) columns + significance stars (***/**/*) + standard errors in parentheses = LIKELY RESULTS
2. Tables comparing "Treatment" vs "Control" means with a "Difference" column = DESCRIPTIVE (balance test)
3. Tables titled "Summary statistics" or "Baseline characteristics" = DESCRIPTIVE
4. Tables with captions like "Impact on..." or "Effect of..." = RESULTS
5. Appendix tables can be RESULTS (robustness) or DESCRIPTIVE (additional checks) - look at content
6. When in doubt between RESULTS and DESCRIPTIVE, if it has treatment coefficients with SEs, it's RESULTS

=== TABLES TO CLASSIFY ===
{''.join(table_list)}

=== RESPONSE FORMAT ===
Respond with a JSON array ONLY. No explanation outside JSON.

[
  {{"index": 0, "class": "RESULTS|DESCRIPTIVE|SKIP", "reason": "brief 5-15 word explanation"}}
]

JSON:"""
        
        return prompt
    
    def _parse_llm_response(self, response_text: str, tables: list[TableInfo]) -> dict:
        """Parse LLM response to extract classifications."""
        classifications = {}
        
        # Try to extract JSON from response
        try:
            # Find JSON array in response
            json_match = re.search(r'\[[\s\S]*\]', response_text)
            if json_match:
                results = json.loads(json_match.group())
                for item in results:
                    idx = item.get('index')
                    cls = item.get('class', 'UNKNOWN').upper()
                    reason = item.get('reason', '')
                    
                    # Validate class
                    if cls not in ['RESULTS', 'DESCRIPTIVE', 'SKIP']:
                        cls = 'UNKNOWN'
                    
                    classifications[idx] = {'class': cls, 'reason': reason}
        except json.JSONDecodeError as e:
            self._log(f"  Warning: Could not parse LLM JSON: {e}")
            self._log(f"  Response was: {response_text[:500]}")
        
        return classifications
    
    # =========================================================================
    # STEP 3: RECOVERY PASS (for SKIP/UNKNOWN with results indicators)
    # =========================================================================
    
    def _step3_recovery_pass(self):
        """Re-classify SKIP/UNKNOWN tables that have results indicators."""
        self._log("\n[STEP 3] Recovery pass for SKIP/UNKNOWN with results indicators...")
        
        # Find tables to recover: SKIP or UNKNOWN that have stars or SE patterns
        recovery_candidates = [
            t for t in self.tables 
            if t.classification in ('SKIP', 'UNKNOWN') 
            and (t.has_stars or t.has_se_pattern)
            and not t.is_continuation
        ]
        
        if not recovery_candidates:
            self._log("  No candidates for recovery")
            return
        
        self._log(f"  Found {len(recovery_candidates)} candidates with results indicators")
        
        # Build recovery prompt with full body content
        prompt = self._build_recovery_prompt(recovery_candidates)
        
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
            )
            response_text = response.choices[0].message.content
            classifications = self._parse_llm_response(response_text, recovery_candidates)
            
            # Apply recovery classifications
            recovered = 0
            for table in recovery_candidates:
                if table.index in classifications:
                    new_class = classifications[table.index]['class']
                    new_reason = classifications[table.index]['reason']
                    
                    if new_class != table.classification:
                        old_class = table.classification
                        table.classification = new_class
                        table.classification_reason = f"[Recovered] {new_reason}"
                        recovered += 1
                        self._log(f"  Recovered Table {table.index}: {old_class} -> {new_class}")
            
            self._log(f"  Recovered {recovered} tables")
            
        except Exception as e:
            self._log(f"  ERROR: Recovery pass failed: {e}")
        
        # Updated summary
        results = sum(1 for t in self.tables if t.classification == 'RESULTS')
        descriptive = sum(1 for t in self.tables if t.classification == 'DESCRIPTIVE')
        skip = sum(1 for t in self.tables if t.classification == 'SKIP')
        unknown = sum(1 for t in self.tables if t.classification == 'UNKNOWN')
        
        self._log(f"\n  Final counts: RESULTS={results}, DESCRIPTIVE={descriptive}, SKIP={skip}, UNKNOWN={unknown}")
    
    def _build_recovery_prompt(self, tables: list[TableInfo]) -> str:
        """Build prompt for recovery pass with full body content."""
        
        table_list = []
        for t in tables:
            entry = f"""
TABLE {t.index} (page {t.page_idx}):
  Caption: {t.caption}
  Has stars: {t.has_stars}
  Has SE pattern: {t.has_se_pattern}
  
  FULL BODY CONTENT:
  {t.body_preview[:600]}
"""
            table_list.append(entry)
        
        prompt = f"""You are an expert at analyzing impact evaluation tables. These tables were initially classified as SKIP or UNKNOWN, but they contain statistical indicators (significance stars or standard errors) that suggest they might be RESULTS tables.

REVIEW EACH TABLE CAREFULLY and reclassify:

**RESULTS** - Reclassify as RESULTS if the table contains:
- Treatment effect coefficients with standard errors
- Regression results with *, **, *** significance markers
- Impact estimates from RCT/quasi-experimental studies
- The numbers look like coefficients (e.g., 0.142***, 0.089**, -0.023)

**DESCRIPTIVE** - Keep as DESCRIPTIVE if:
- It's a balance table testing pre-treatment equivalence
- Summary statistics without treatment effects
- The stars indicate balance test p-values, not treatment effects

**SKIP** - Keep as SKIP if:
- It's truly a codebook, glossary, or non-data table
- The "indicators" are false positives

=== TABLES TO REVIEW ===
{''.join(table_list)}

=== RESPONSE ===
JSON array only:

[
  {{"index": X, "class": "RESULTS|DESCRIPTIVE|SKIP", "reason": "explanation"}}
]

JSON:"""
        
        return prompt

    def _log(self, msg: str):
        """Print log message if verbose."""
        if self.verbose:
            print(msg)
    
    # =========================================================================
    # Output methods
    # =========================================================================
    
    def get_results_tables(self) -> list[TableInfo]:
        """Get tables classified as RESULTS."""
        return [t for t in self.tables if t.classification == 'RESULTS']
    
    def get_classification_summary(self) -> dict:
        """Get summary of classification results."""
        return {
            'total_tables': len(self.tables),
            'results': sum(1 for t in self.tables if t.classification == 'RESULTS'),
            'descriptive': sum(1 for t in self.tables if t.classification == 'DESCRIPTIVE'),
            'skip': sum(1 for t in self.tables if t.classification == 'SKIP'),
            'unknown': sum(1 for t in self.tables if t.classification == 'UNKNOWN'),
            'continuations': sum(1 for t in self.tables if t.is_continuation),
        }
    
    def to_dataframe(self):
        """Export classification to pandas DataFrame."""
        import pandas as pd
        
        rows = []
        for t in self.tables:
            rows.append({
                'index': t.index,
                'page': t.page_idx,
                'table_number': t.table_number,
                'caption': t.caption[:150],
                'is_continuation': t.is_continuation,
                'classification': t.classification,
                'reason': t.classification_reason,
            })
        
        return pd.DataFrame(rows)


# =============================================================================
# Test
# =============================================================================

if __name__ == '__main__':
    import boto3
    from dotenv import load_dotenv
    
    load_dotenv()
    
    account_id = os.environ.get('CLOUDFLARE_ACCOUNT_ID')
    r2 = boto3.client(
        's3',
        endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ.get('R2_ACCESS_KEY_ID'),
        aws_secret_access_key=os.environ.get('R2_SECRET_ACCESS_KEY'),
    )
    BUCKET = 'devchat-pdfs'
    
    # Test with sample document
    key = 'rags/0816e8d3-ab23-417c-bf3f-e45531411c73/outputs/json/1f44cd8c70b8_PDFs_of_included_programs_121058367.json'
    
    print("Loading document...")
    response = r2.get_object(Bucket=BUCKET, Key=key)
    doc = json.loads(response['Body'].read().decode('utf-8'))
    
    # Run pipeline
    classifier = TableClassifierV2(doc, study_id="121058367", verbose=True)
    tables = classifier.run_pipeline()
    
    # Show summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    summary = classifier.get_classification_summary()
    for k, v in summary.items():
        print(f"  {k}: {v}")
    
    # Export to DataFrame
    df = classifier.to_dataframe()
    print("\n" + "=" * 80)
    print("CLASSIFICATION DETAILS")
    print("=" * 80)
    print(df.to_string(index=False))
    
    # Save
    df.to_csv('extraction_pipeline/outputs/classification_v2_test.csv', index=False)
    print("\nSaved to: extraction_pipeline/outputs/classification_v2_test.csv")
