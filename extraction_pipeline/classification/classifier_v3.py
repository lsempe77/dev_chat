"""
Table Classification Pipeline v3 - Comprehensive LLM-First Approach

IMPROVEMENTS OVER v2:
- Extracts captions from content markdown (not just table_caption field)
- Preserves table structure (first/last rows, not flattened text)
- Batches LLM calls (25 tables per batch)
- Validates LLM response counts
- Detects document sections (Methods, Results, Appendix)
- Better SE/star detection regex
- Less aggressive continuation detection
- Adds confidence scoring
- More realistic few-shot examples
- Robust LLM response parsing with retries

Author: DevChat Pipeline
"""
import re
import json
import os
import sys
import time
import logging
from dataclasses import dataclass, field
from typing import Optional
from bs4 import BeautifulSoup
from openai import OpenAI

# Import post-processor for artifact removal
try:
    from extraction_pipeline.mineru_postprocessor import MinerUPostProcessor
    HAS_POSTPROCESSOR = True
except ImportError:
    try:
        from mineru_postprocessor import MinerUPostProcessor
        HAS_POSTPROCESSOR = True
    except ImportError:
        HAS_POSTPROCESSOR = False

# Configure logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')

# =============================================================================
# PRE-COMPILED REGEXES (Module-level for performance)
# =============================================================================

# Star detection patterns
STAR_PATTERNS = [
    re.compile(r'\d(?:\.\d+)?\s*\*{1,3}'),  # 0.142*** or 0.142 ***
    re.compile(r'\)\s*\*{1,3}'),              # )*** or ) ***
    re.compile(r'\*{1,3}\s*\('),              # *** (
]

# Standard error detection patterns  
SE_PATTERNS = [
    re.compile(r'\(\s*0?\.\d{2,4}\s*\)', re.IGNORECASE),       # (0.042) or (.042)
    re.compile(r'\(\s*\d\.\d{2,4}\s*\)', re.IGNORECASE),        # (1.234) - SE >= 1
    re.compile(r'\[\s*0?\.\d{2,4}\s*\]', re.IGNORECASE),        # [0.042] - brackets
    re.compile(r'\(\s*0?\.\d{2,4}\s*\*{0,3}\)', re.IGNORECASE), # (0.04*) - star inside
    re.compile(r'SE\s*[=:]\s*0?\.\d+', re.IGNORECASE),           # SE = 0.042
    re.compile(r's\.e\.\s*[=:]\s*0?\.\d+', re.IGNORECASE),       # s.e. = 0.042
]

# Coefficient terms patterns (all case-insensitive)
COEF_PATTERNS = [
    re.compile(r'\btreatment\b', re.IGNORECASE),
    re.compile(r'\bcontrol\b', re.IGNORECASE),
    re.compile(r'\bitt\b', re.IGNORECASE),
    re.compile(r'\bate\b', re.IGNORECASE),
    re.compile(r'\blate\b', re.IGNORECASE),
    re.compile(r'\btot\b', re.IGNORECASE),
    re.compile(r'\bdid\b', re.IGNORECASE),
    re.compile(r'\bdiff-?in-?diff', re.IGNORECASE),
    re.compile(r'\bcoef', re.IGNORECASE),
    re.compile(r'\beffect\b', re.IGNORECASE),
    re.compile(r'\bimpact\b', re.IGNORECASE),
    re.compile(r'\bOLS\b', re.IGNORECASE),
    re.compile(r'\bIV\b', re.IGNORECASE),
    re.compile(r'\b2SLS\b', re.IGNORECASE),
    re.compile(r'\bFE\b', re.IGNORECASE),
]

# Caption extraction patterns (multilingual: Table, Tableau, Tabla, Tabelle)
CAPTION_PATTERNS = [
    # Standard: Table 4.1: Caption text (min 5 chars, max 250)
    re.compile(r'(?:\*\*)?(?:Table|Tableau|Tabla|Tabelle)\s+([\dA-Z]+\.?\d*[a-z]?)[\s:.\-–]+([^\n\|]{5,250})', re.IGNORECASE),
    # With line break after table number  
    re.compile(r'(?:\*\*)?(?:Table|Tableau|Tabla|Tabelle)\s+([\dA-Z]+\.?\d*[a-z]?)\*?\*?\s*\n\s*([^\n\|]{5,200})', re.IGNORECASE),
]

# Appendix table detection (Table A1, Table A.1, Table B2, etc.)
APPENDIX_TABLE_RE = re.compile(r'Table\s+[A-Za-z]\d', re.IGNORECASE)

# P-value / statistical test patterns (for treatment comparison tables)
PVALUE_PATTERNS = [
    re.compile(r'Test:\s*T\d\s*=\s*T\d', re.IGNORECASE),     # Test: T1 = T2
    re.compile(r'p-?value', re.IGNORECASE),                    # p-value, pvalue
    re.compile(r'\bp\s*[<>=]\s*0?\.\d+', re.IGNORECASE),     # p < 0.05, p = 0.001
    re.compile(r'F-?test', re.IGNORECASE),                     # F-test, Ftest
    re.compile(r'Wald\s*test', re.IGNORECASE),                 # Wald test
    re.compile(r'Chi-?sq', re.IGNORECASE),                     # Chi-square, Chi-sq
    re.compile(r'\bH0:\b', re.IGNORECASE),                    # H0: (null hypothesis)
    re.compile(r'reject.*null', re.IGNORECASE),                # reject the null
    re.compile(r'significance\s*level', re.IGNORECASE),        # significance level
    re.compile(r'\b0\.0{1,3}[1-9]\d*\b'),                     # Small p-values: 0.001, 0.023, etc.
]

# Empty table thresholds
EMPTY_TABLE_MIN_ROWS = 1       # Tables with 0 rows are definitely empty
EMPTY_TABLE_MIN_TEXT_LEN = 10  # Tables with <10 chars of text are empty


# =============================================================================
# FEW-SHOT EXAMPLES - Realistic messy data
# =============================================================================

FEW_SHOT_EXAMPLES = """
EXAMPLE 1 - DESCRIPTIVE (Balance table):
Caption: "Table 1: Baseline balance"
Section: "3. Data and Methods"
Body sample:
  Row 1: Variable | Treatment (N=500) | Control (N=480) | Difference | p-value
  Row 2: Age of household head | 42.3 | 41.8 | 0.5 | 0.423
  Row 3: Years of education | 6.2 | 6.4 | -0.2* | 0.089
  Last row: F-test (joint) | | | | 0.342
Classification: DESCRIPTIVE
Reason: Balance table - stars on differences test pre-treatment equivalence, not causal effects.

EXAMPLE 2 - RESULTS (Regression table):
Caption: "Table 4: Program impacts on consumption"
Section: "5. Results"
Body sample:
  Row 1: | (1) | (2) | (3) | (4)
  Row 2: | OLS | OLS | IV | IV
  Row 3: Treatment | 0.142*** | 0.138*** | 0.189** | 0.175**
  Row 4: | (0.042) | (0.041) | (0.078) | (0.072)
  Last row: Observations | 2,450 | 2,450 | 2,450 | 2,450
Classification: RESULTS
Reason: Regression results - treatment coefficients with SEs showing causal effects.

EXAMPLE 3 - SKIP (Codebook):
Caption: "[No caption]"
Section: "Appendix"
Body sample:
  Row 1: Code | Description
  Row 2: -99 | Not applicable
  Row 3: -98 | Don't know
  Row 4: -97 | Refused
Classification: SKIP
Reason: Survey response codes, not quantitative data.

EXAMPLE 4 - RESULTS (Appendix robustness):
Caption: "Table A.5: Robustness - Alternative specifications"
Section: "Appendix"
Body sample:
  Row 1: Panel A: Excluding outliers
  Row 2: Treatment | 0.131*** | 0.128*** | 0.135***
  Row 3: | (0.039) | (0.038) | (0.041)
  Row 4: Panel B: Winsorized outcomes
  Last row: Treatment | 0.145*** | 0.141*** | 0.148***
Classification: RESULTS
Reason: Robustness checks showing treatment effects under different specifications.

EXAMPLE 5 - DESCRIPTIVE (Summary stats):
Caption: "Table 2: Summary Statistics"
Section: "4. Data"
Body sample:
  Row 1: Variable | N | Mean | SD | Min | Max
  Row 2: Household income | 2,892 | 4,532 | 2,341 | 0 | 45,000
  Row 3: Household size | 2,892 | 5.2 | 2.1 | 1 | 15
Classification: DESCRIPTIVE
Reason: Summary statistics describing sample characteristics, no treatment effects.

EXAMPLE 6 - RESULTS (No caption, continuation):
Caption: "[No caption]"
Section: "5. Results"
Body sample:
  Row 1: (0.045) | (0.052) | (0.048) | (0.055)
  Row 2: T1 × Female | 0.234*** | 0.198*** | 0.212*** | 0.189**
  Row 3: | (0.067) | (0.065) | (0.071) | (0.073)
  Row 4: T1 × Male | 0.156** | 0.142** | 0.167** | 0.151*
  Last row: Observations | 1,245 | 1,245 | 1,245 | 1,102
Classification: RESULTS
Reason: Continuation showing heterogeneous treatment effects by gender with coefficients and SEs.

EXAMPLE 7 - DESCRIPTIVE (Outcome definitions):
Caption: "Table A1. Primary and secondary outcomes: nutrition"
Section: "Appendix"
Body sample:
  Row 1: Outcome | Variable name | Definition | Source
  Row 2: Primary | stunting | Height-for-age z-score < -2 | WHO standards
  Row 3: Primary | wasting | Weight-for-height z-score < -2 | WHO standards
  Row 4: Secondary | dietary diversity | Count of food groups consumed | 24hr recall
  Last row: Secondary | meal frequency | Number of meals per day | Survey
Classification: DESCRIPTIVE
Reason: Defines outcome variables and measurement methods, not actual results or response codes.

EXAMPLE 8 - RESULTS (Spanish - Impactos del tratamiento):
Caption: "Tabla 5: Impactos del tratamiento sobre ingresos"
Section: "5. Resultados"
Body sample:
  Row 1: Variable | (1) MCO | (2) MCO | (3) VI
  Row 2: Tratamiento | 0,234*** | 0,198*** | 0,312**
  Row 3: | (0,067) | (0,065) | (0,142)
  Row 4: Ingreso Laboral | 0,156** | 0,142** | 0,189*
  Last row: Observaciones | 1.245 | 1.245 | 1.102
Classification: RESULTS
Reason: Spanish regression table - "Impactos del tratamiento" means treatment impacts, coefficients with SEs.

EXAMPLE 9 - RESULTS (French - Effet du programme):
Caption: "Tableau 3: Effet du programme sur la consommation"
Section: "4. Résultats"
Body sample:
  Row 1: | (1) | (2) | (3)
  Row 2: Traitement | 0,142*** | 0,138*** | 0,189**
  Row 3: | (0,042) | (0,041) | (0,078)
  Row 4: Traitement × Femme | 0,087* | 0,092** | 0,112*
  Last row: Observations | 2.450 | 2.450 | 2.450
Classification: RESULTS
Reason: French regression table - "Effet du programme" means program effect, with treatment coefficients.

EXAMPLE 10 - RESULTS (Appendix heterogeneity/subgroup):
Caption: "Table B.3: Heterogeneous effects by baseline asset quartile"
Section: "Appendix B: Additional Results"
Body sample:
  Row 1: | Q1 (poorest) | Q2 | Q3 | Q4 (richest)
  Row 2: Treatment | 0.312*** | 0.198** | 0.089 | 0.023
  Row 3: | (0.089) | (0.076) | (0.062) | (0.058)
  Row 4: p-value (Q1=Q4) | | | | 0.003
  Last row: Observations | 612 | 608 | 615 | 610
Classification: RESULTS
Reason: Heterogeneous treatment effects by subgroup (asset quartile) - appendix but still causal estimates.

EXAMPLE 11 - RESULTS (Cost-effectiveness analysis):
Caption: "Table 8: Cost-benefit analysis and cost-effectiveness"
Section: "6. Discussion"
Body sample:
  Row 1: Outcome | Impact | Cost per unit | Benefit-cost ratio
  Row 2: Income (yearly) | $234*** | $150 | 1.56
  Row 3: | (67) | | 
  Row 4: Assets (value) | $890*** | $150 | 5.93
  Last row: | (234) | |
Classification: RESULTS
Reason: Cost-effectiveness table with treatment effects - combines costs with causal impacts.

EXAMPLE 12 - DESCRIPTIVE (Attrition analysis):
Caption: "Table A2: Attrition analysis"
Section: "Appendix"
Body sample:
  Row 1: | Baseline | Endline | Attrition rate | p-value
  Row 2: Treatment | 1,250 | 1,102 | 11.8% | 
  Row 3: Control | 1,200 | 1,089 | 9.3% | 
  Row 4: Difference | | | 2.5pp | 0.234
  Last row: F-test (differential attrition) | | | | 0.189
Classification: DESCRIPTIVE
Reason: Attrition analysis compares sample loss, not treatment effects on outcomes.

EXAMPLE 13 - RESULTS (Mechanism/pathway analysis):
Caption: "Table 6: Mechanisms - Knowledge and behavior changes"
Section: "5.2 Pathways of Impact"
Body sample:
  Row 1: | (1) Knowledge | (2) Savings | (3) Investment
  Row 2: Treatment | 0.45*** | 0.23*** | 0.18**
  Row 3: | (0.08) | (0.05) | (0.07)
  Row 4: Knowledge mediator | | 0.12** | 0.09*
  Last row: | | (0.04) | (0.05)
Classification: RESULTS
Reason: Mechanism analysis showing causal effects on intermediate outcomes (knowledge, behavior).
"""


@dataclass
class TableInfo:
    """Complete information about a table for classification."""
    index: int                 # Index in tables array
    table_number: str          # "Table 4.1", "Table A1", etc.
    caption: str               # Full caption text
    caption_source: str = ""   # Where caption came from: "table_caption", "content", "inferred"
    context: str = ""          # Sentences where table is mentioned in document
    section: str = ""          # Document section: "Methods", "Results", "Appendix", etc.
    page_idx: int = -1         # Page where table appears
    html_body: str = ""        # Raw HTML (for extraction later)
    
    # Structured body info (preserves table structure)
    body_sample: str = ""      # First 3 + last 3 rows
    row_count: int = 0
    col_count: int = 0
    
    # Results indicators
    has_stars: bool = False
    has_se_pattern: bool = False
    has_coef_terms: bool = False
    has_pvalue_pattern: bool = False  # p-value / statistical test indicators
    
    # Continuation detection
    is_continuation: bool = False
    continuation_of: int = -1
    
    # Classification (populated by LLM)
    classification: str = "UNKNOWN"  # RESULTS, DESCRIPTIVE, SKIP
    classification_reason: str = ""
    confidence: str = "medium"  # low, medium, high


class TableClassifierV3:
    """
    Comprehensive LLM-first table classification pipeline.
    
    Fixes from v2:
    - Caption extraction from content markdown
    - Batched LLM calls
    - Preserved table structure
    - Response validation
    - Section detection
    - Robust LLM response parsing
    - Retry with exponential backoff
    """
    
    DEFAULT_BATCH_SIZE = 25  # Tables per LLM call
    DEFAULT_MODEL = "openai/gpt-4o"
    MAX_RETRIES = 3
    
    def __init__(
        self, 
        doc: dict, 
        study_id: str = "", 
        verbose: bool = True,
        batch_size: Optional[int] = None,
        model_name: Optional[str] = None,
        client: Optional[OpenAI] = None,
        enable_postprocessing: bool = True,
        md_content: str = "",  # Full markdown for List of Tables cross-reference
    ):
        self.doc = doc
        self.study_id = study_id
        self.verbose = verbose
        self.content = doc.get('content', '')
        self.tables_raw = doc.get('tables', [])
        self.enable_postprocessing = enable_postprocessing and HAS_POSTPROCESSOR
        self.md_content = md_content  # For LOT caption repair
        
        # Post-processing stats
        self.postprocessing_stats = None
        
        # Configurable parameters
        self.batch_size = batch_size or self.DEFAULT_BATCH_SIZE
        self.model_name = model_name or self.DEFAULT_MODEL
        
        # Configure OpenRouter client (injectable for testing)
        if client:
            self.client = client
        else:
            self.client = OpenAI(
                api_key=os.environ.get('OPENROUTER_API_KEY'),
                base_url="https://openrouter.ai/api/v1"
            )
        
        # Pre-extracted data
        self.section_map: dict[int, str] = {}  # page -> section
        self.caption_map: dict[str, str] = {}  # table_number -> caption from content
        
        # Output
        self.tables: list[TableInfo] = []
        
    def run_pipeline(self) -> list[TableInfo]:
        """Execute full classification pipeline."""
        self._log("=" * 80)
        self._log("TABLE CLASSIFICATION PIPELINE v3")
        self._log("=" * 80)
        
        # Step -1: Post-processing to remove artifacts (NEW)
        if self.enable_postprocessing:
            self._step_minus1_postprocess()
        
        # Step 0: Pre-process document
        self._step0_preprocess_document()
        
        # Step 1: Parse tables with structure preservation
        self._step1_parse_tables()
        
        # Step 1.5: Filter empty tables (mark as EMPTY, skip LLM classification)
        self._step1_5_filter_empty_tables()
        
        # Step 2: Classify with batched LLM calls
        self._step2_classify_with_llm()
        
        # Step 3: Recovery pass for uncertain classifications
        self._step3_recovery_pass()
        
        return self.tables
    
    # =========================================================================
    # STEP -1: POST-PROCESSING (Artifact Removal)
    # =========================================================================
    
    def _step_minus1_postprocess(self):
        """Remove parsing artifacts before classification."""
        self._log("\n[STEP -1] Post-processing to remove artifacts...")
        
        original_count = len(self.tables_raw)
        
        # Run post-processor
        processor = MinerUPostProcessor(
            self.doc, 
            md_content=self.md_content,  # For List of Tables cross-reference
            min_table_rows=2,
            verbose=False,  # Suppress detailed logs
        )
        result = processor.process()
        
        # Update tables_raw with clean tables
        self.tables_raw = result.clean_tables
        self.postprocessing_stats = result.stats
        
        removed = original_count - len(self.tables_raw)
        self._log(f"  Input: {original_count} tables")
        self._log(f"  Removed: {removed} artifacts")
        self._log(f"  Output: {len(self.tables_raw)} clean tables")
        
        # Log artifact details
        if result.artifacts:
            self._log("  Artifacts detected:")
            for artifact in result.artifacts[:5]:  # Show first 5
                self._log(f"    [{artifact['type']}] Page {artifact['page']}: {artifact['caption'][:40]}")
            if len(result.artifacts) > 5:
                self._log(f"    ... and {len(result.artifacts) - 5} more")
    
    # =========================================================================
    # STEP 0: PRE-PROCESS DOCUMENT
    # =========================================================================
    
    def _step0_preprocess_document(self):
        """Extract document structure: sections and captions from content."""
        self._log("\n[STEP 0] Pre-processing document...")
        
        if not self.content:
            self._log("  Warning: No content field in document")
            return
        
        # Extract section headers and their page ranges
        self._extract_sections()
        
        # Extract table captions from content markdown
        self._extract_captions_from_content()
        
        self._log(f"  Sections found: {len(set(self.section_map.values()))}")
        self._log(f"  Captions found in content: {len(self.caption_map)}")
    
    def _extract_sections(self):
        """Extract section headers to understand document structure."""
        # Common section patterns in impact evaluations
        section_patterns = [
            r'(?:^|\n)#+\s*((?:\d+\.?\s*)?(?:Introduction|Background|Literature|Context))',
            r'(?:^|\n)#+\s*((?:\d+\.?\s*)?(?:Data|Sample|Study Design|Methodology|Methods|Empirical Strategy))',
            r'(?:^|\n)#+\s*((?:\d+\.?\s*)?(?:Results|Findings|Main Results|Empirical Results|Impact))',
            r'(?:^|\n)#+\s*((?:\d+\.?\s*)?(?:Discussion|Conclusion|Summary))',
            r'(?:^|\n)#+\s*((?:\d+\.?\s*)?(?:Appendix|Annexe|Supplementary|Online Appendix|Tables|Figures))',
            r'(?:^|\n)#+\s*((?:\d+\.?\s*)?(?:Robustness|Sensitivity|Heterogeneous|Subgroup))',
        ]
        
        current_section = "Unknown"
        # Simple heuristic: track section by position in content
        sections_found = []
        
        for pattern in section_patterns:
            for match in re.finditer(pattern, self.content, re.IGNORECASE):
                section_name = match.group(1).strip()
                position = match.start()
                sections_found.append((position, section_name))
        
        # Sort by position
        sections_found.sort(key=lambda x: x[0])
        
        # Map to simplified section names
        self.sections_by_position = []
        for pos, name in sections_found:
            name_lower = name.lower()
            if any(x in name_lower for x in ['introduction', 'background', 'literature', 'context']):
                simplified = "Introduction"
            elif any(x in name_lower for x in ['data', 'sample', 'design', 'method', 'empirical strategy']):
                simplified = "Methods"
            elif any(x in name_lower for x in ['result', 'finding', 'impact']):
                simplified = "Results"
            elif any(x in name_lower for x in ['discussion', 'conclusion', 'summary']):
                simplified = "Discussion"
            elif any(x in name_lower for x in ['appendix', 'annex', 'supplementary', 'online']):
                simplified = "Appendix"
            elif any(x in name_lower for x in ['robustness', 'sensitivity', 'heterogeneous', 'subgroup']):
                simplified = "Results"  # These are typically results subsections
            else:
                simplified = "Other"
            
            self.sections_by_position.append((pos, simplified))
    
    def _extract_captions_from_content(self):
        """Extract table captions from content markdown."""
        # Use pre-compiled patterns (handles Table, Tableau, Tabla, Tabelle)
        for pattern in CAPTION_PATTERNS:
            for match in pattern.finditer(self.content):
                table_num = f"Table {match.group(1)}"
                caption = match.group(2).strip()
                # Clean up caption
                caption = re.sub(r'\*+', '', caption)  # Remove markdown bold
                caption = re.sub(r'^[:.\-–\s]+', '', caption)  # Clean leading punctuation
                caption = caption.strip()
                
                key = table_num.lower()
                # Accept shorter captions (min 3 chars) - some valid captions are short
                if key not in self.caption_map and len(caption) >= 3:
                    self.caption_map[key] = f"{table_num}: {caption}"
    
    def _get_section_for_position(self, position: int) -> str:
        """Get the section name for a given character position in content."""
        if not hasattr(self, 'sections_by_position') or not self.sections_by_position:
            return "Unknown"
        
        current_section = "Unknown"
        for pos, section in self.sections_by_position:
            if pos <= position:
                current_section = section
            else:
                break
        return current_section
    
    # =========================================================================
    # STEP 1: PARSING (Structure-preserving)
    # =========================================================================
    
    def _step1_parse_tables(self):
        """Parse all tables with structure preservation."""
        self._log("\n[STEP 1] Parsing tables with structure preservation...")
        
        # First pass: extract basic info
        for i, table in enumerate(self.tables_raw):
            table_info = self._parse_single_table(i, table)
            self.tables.append(table_info)
        
        # Second pass: detect continuations (after all tables are parsed)
        self._detect_continuations()
        
        # Extract context from content for each table
        self._extract_table_contexts()
        
        # Stats
        self._log(f"  Total tables: {len(self.tables)}")
        self._log(f"  With captions: {sum(1 for t in self.tables if t.caption != '[No caption]')}")
        self._log(f"    - from table_caption field: {sum(1 for t in self.tables if t.caption_source == 'table_caption')}")
        self._log(f"    - from content markdown: {sum(1 for t in self.tables if t.caption_source == 'content')}")
        self._log(f"  With context: {sum(1 for t in self.tables if t.context)}")
        self._log(f"  With results indicators: {sum(1 for t in self.tables if t.has_stars or t.has_se_pattern)}")
        self._log(f"  Detected continuations: {sum(1 for t in self.tables if t.is_continuation)}")
    
    def _parse_single_table(self, index: int, table: dict) -> TableInfo:
        """Parse a single table, preserving structure."""
        
        # Get HTML body
        html_body = table.get('table_body', '')
        page_idx = table.get('page_idx', -1)
        
        # Parse HTML to get structure
        soup = BeautifulSoup(html_body, 'html.parser') if html_body else None
        
        # Extract structured body sample (first 4 rows + last 2 rows)
        body_sample, row_count, col_count = self._extract_body_sample(soup)
        
        # Get full text for indicator detection
        full_text = soup.get_text(separator=' ', strip=True) if soup else ""
        
        # Detect results indicators with improved regex
        has_stars = self._detect_stars(full_text)
        has_se_pattern = self._detect_se_pattern(full_text)
        has_coef_terms = self._detect_coef_terms(full_text)
        has_pvalue_pattern = self._detect_pvalue_pattern(full_text)
        
        # Extract table number and caption
        table_number, caption, caption_source = self._extract_caption(index, table, body_sample)
        
        # Determine section based on page and content position
        section = self._determine_section(table_number, page_idx)
        
        return TableInfo(
            index=index,
            table_number=table_number,
            caption=caption,
            caption_source=caption_source,
            section=section,
            page_idx=page_idx,
            html_body=html_body,
            body_sample=body_sample,
            row_count=row_count,
            col_count=col_count,
            has_stars=has_stars,
            has_se_pattern=has_se_pattern,
            has_coef_terms=has_coef_terms,
            has_pvalue_pattern=has_pvalue_pattern,
        )
    
    def _extract_body_sample(self, soup) -> tuple[str, int, int]:
        """Extract first 4 rows + last 2 rows to preserve structure."""
        if not soup:
            return "[Empty table]", 0, 0
        
        rows = soup.find_all('tr')
        if not rows:
            # No table rows - just get text
            text = soup.get_text(separator=' ', strip=True)[:500]
            return text, 0, 0
        
        row_count = len(rows)
        col_count = 0
        
        # Get sample rows
        sample_indices = []
        if row_count <= 6:
            sample_indices = list(range(row_count))
        else:
            # First 4 + last 2
            sample_indices = [0, 1, 2, 3] + [row_count - 2, row_count - 1]
        
        lines = []
        for i in sample_indices:
            if i < row_count:
                row = rows[i]
                cells = row.find_all(['td', 'th'])
                if cells:
                    col_count = max(col_count, len(cells))
                    cell_texts = [c.get_text(strip=True)[:50] for c in cells]
                    line = f"  Row {i+1}: " + " | ".join(cell_texts)
                    lines.append(line)
        
        # Add ellipsis if we skipped rows
        if row_count > 6:
            lines.insert(4, f"  ... ({row_count - 6} rows omitted) ...")
        
        return "\n".join(lines), row_count, col_count
    
    def _detect_stars(self, text: str) -> bool:
        """Detect significance stars with pre-compiled patterns."""
        for pattern in STAR_PATTERNS:
            if pattern.search(text):
                return True
        return False
    
    def _detect_se_pattern(self, text: str) -> bool:
        """Detect standard error patterns with pre-compiled regex."""
        for pattern in SE_PATTERNS:
            if pattern.search(text):
                return True
        return False
    
    def _detect_coef_terms(self, text: str) -> bool:
        """Detect coefficient-related terms with pre-compiled case-insensitive patterns."""
        for pattern in COEF_PATTERNS:
            if pattern.search(text):
                return True
        return False
    
    def _detect_pvalue_pattern(self, text: str) -> bool:
        """Detect p-value and statistical test patterns."""
        for pattern in PVALUE_PATTERNS:
            if pattern.search(text):
                return True
        return False
    
    def _extract_caption(self, index: int, table: dict, body_sample: str) -> tuple[str, str, str]:
        """Extract table number and caption from multiple sources."""
        
        # Source 1: table_caption field
        caption_list = table.get('table_caption', [])
        caption_field = ' '.join(caption_list).strip() if caption_list else ''
        
        # Try to extract table number
        table_number = ""
        caption = ""
        source = ""
        
        # Check table_caption field first
        if caption_field:
            match = re.search(r'(Table\s+[\dA-Z]+\.?\d*[a-z]?)', caption_field, re.IGNORECASE)
            if match:
                table_number = match.group(1)
                caption = caption_field
                source = "table_caption"
        
        # Check content markdown (often better)
        if not table_number or len(caption) < 20:
            # Try body sample for table number
            match = re.search(r'(Table\s+[\dA-Z]+\.?\d*[a-z]?)', body_sample[:200], re.IGNORECASE)
            if match:
                potential_num = match.group(1)
                key = potential_num.lower()
                
                # Look up in caption_map from content
                if key in self.caption_map:
                    table_number = potential_num
                    caption = self.caption_map[key]
                    source = "content"
                elif not table_number:
                    table_number = potential_num
        
        # Still no table number? Generate one
        if not table_number:
            table_number = f"Table {index + 1}"
            source = "inferred"
        
        # Still no caption? Try caption_map with current table_number
        if not caption or caption == table_number:
            key = table_number.lower()
            if key in self.caption_map:
                caption = self.caption_map[key]
                source = "content"
            else:
                caption = "[No caption]"
                source = source or "none"
        
        return table_number, caption[:300], source
    
    def _determine_section(self, table_number: str, page_idx: int) -> str:
        """Determine which section a table belongs to."""
        # Check if table number suggests appendix (Table A1, Table A.1, Table B2, etc.)
        if APPENDIX_TABLE_RE.search(table_number):
            return "Appendix"
        
        # Try to find table mention in content and get section
        if self.content:
            match = re.search(re.escape(table_number), self.content, re.IGNORECASE)
            if match:
                return self._get_section_for_position(match.start())
        
        return "Unknown"
    
    def _detect_continuations(self):
        """Detect continuation tables with stricter criteria."""
        for i, table in enumerate(self.tables):
            if table.caption != '[No caption]':
                continue  # Has caption, not a continuation
            
            if i == 0:
                continue
            
            prev = self.tables[i - 1]
            
            # Rule 1: Check for "continued" text in body
            if 'continued' in table.body_sample.lower() or 'cont.' in table.body_sample.lower():
                parent_idx = self._find_parent_table(i)
                if parent_idx >= 0:
                    self._mark_as_continuation(table, parent_idx)
                    continue
            
            # Rule 2: Same page as previous, similar column count, no caption
            if (table.page_idx == prev.page_idx and 
                prev.caption != '[No caption]' and
                abs(table.col_count - prev.col_count) <= 1 and
                table.col_count > 0):
                # Additional check: body starts with data, not headers
                first_row = table.body_sample.split('\n')[0] if table.body_sample else ""
                if re.search(r'Row 1:.*\d', first_row):  # First row has numbers
                    self._mark_as_continuation(table, i - 1)
                    continue
            
            # Rule 3: Previous was continuation - check if chain continues
            if prev.is_continuation and table.page_idx == prev.page_idx:
                if abs(table.col_count - prev.col_count) <= 1:
                    self._mark_as_continuation(table, prev.continuation_of)
    
    def _find_parent_table(self, current_idx: int) -> int:
        """Find the parent table for a continuation."""
        for j in range(current_idx - 1, -1, -1):
            t = self.tables[j]
            if t.caption != '[No caption]' and not t.is_continuation:
                return j
        return -1
    
    def _mark_as_continuation(self, table: TableInfo, parent_idx: int):
        """Mark a table as continuation of another."""
        parent = self.tables[parent_idx]
        table.is_continuation = True
        table.continuation_of = parent_idx
        table.table_number = parent.table_number + " (cont.)"
        table.caption = f"[Continuation of {parent.table_number}]"
        table.section = parent.section
    
    def _extract_table_contexts(self):
        """Extract context sentences for each table from document content."""
        if not self.content:
            return
        
        for table in self.tables:
            if table.is_continuation:
                continue
            
            # Find mentions of this table in content
            pattern = re.escape(table.table_number)
            contexts = []
            
            for match in re.finditer(pattern, self.content, re.IGNORECASE):
                # Get surrounding text (100 chars before, 200 after)
                start = max(0, match.start() - 100)
                end = min(len(self.content), match.end() + 200)
                context = self.content[start:end]
                # Clean up
                context = re.sub(r'\s+', ' ', context).strip()
                contexts.append(context)
            
            if contexts:
                table.context = " ... ".join(contexts[:3])[:600]  # Max 3 mentions
    
    # =========================================================================
    # STEP 1.5: FILTER EMPTY TABLES
    # =========================================================================
    
    def _step1_5_filter_empty_tables(self):
        """Pre-classify truly empty tables as EMPTY to skip LLM calls."""
        self._log("\n[STEP 1.5] Filtering empty tables...")
        
        empty_count = 0
        for table in self.tables:
            if table.is_continuation:
                continue  # Skip continuations (they'll inherit from parent)
            
            # Check if table is empty
            is_empty = self._is_table_empty(table)
            
            if is_empty:
                table.classification = "EMPTY"
                table.classification_reason = "Table has no data (MinerU parsing artifact)"
                table.confidence = "high"
                empty_count += 1
        
        self._log(f"  Marked {empty_count} tables as EMPTY")
        self._log(f"  Remaining for classification: {len([t for t in self.tables if t.classification == 'UNKNOWN' and not t.is_continuation])}")
    
    def _is_table_empty(self, table: TableInfo) -> bool:
        """Check if a table is truly empty (no meaningful data)."""
        # Check 1: No rows at all
        if table.row_count < EMPTY_TABLE_MIN_ROWS:
            return True
        
        # Check 2: Very short text content
        # Get text length from body_sample (excluding row markers)
        text = table.body_sample
        # Remove "Row X:" markers
        text = re.sub(r'Row \\d+:', '', text)
        # Remove whitespace and check length
        text = re.sub(r'\\s+', '', text)
        
        if len(text) < EMPTY_TABLE_MIN_TEXT_LEN:
            return True
        
        return False

    # =========================================================================
    # STEP 2: CLASSIFICATION (Batched LLM calls)
    # =========================================================================
    
    def _step2_classify_with_llm(self):
        """Classify tables with batched LLM calls."""
        self._log("\n[STEP 2] Classifying tables with LLM (batched)...")
        
        # Get tables to classify (exclude continuations AND already-classified EMPTY tables)
        tables_to_classify = [
            t for t in self.tables 
            if not t.is_continuation and t.classification == "UNKNOWN"
        ]
        
        if not tables_to_classify:
            self._log("  No tables to classify")
            return
        
        # Batch processing
        total = len(tables_to_classify)
        for batch_start in range(0, total, self.batch_size):
            batch_end = min(batch_start + self.batch_size, total)
            batch = tables_to_classify[batch_start:batch_end]
            
            self._log(f"  Processing batch {batch_start//self.batch_size + 1}: tables {batch_start+1}-{batch_end} of {total}")
            
            self._classify_batch(batch)
        
        # Inherit classification for continuation tables
        for table in self.tables:
            if table.is_continuation and table.continuation_of >= 0:
                parent = self.tables[table.continuation_of]
                table.classification = parent.classification
                table.classification_reason = f"Continuation of {parent.table_number}"
                table.confidence = parent.confidence
        
        # Summary
        self._log_classification_summary("After Step 2")
    
    def _classify_batch(self, batch: list[TableInfo]):
        """Classify a batch of tables with one LLM call."""
        prompt = self._build_classification_prompt(batch)
        
        try:
            response_text = self._call_llm_with_retry(prompt)
            classifications = self._parse_llm_response(response_text, batch)
            
            # Validate response count and log missing
            missing_indices = [t.index for t in batch if t.index not in classifications]
            if missing_indices:
                self._log(f"    Warning: Missing classifications for indices: {missing_indices}")
            
            # Apply classifications
            for table in batch:
                if table.index in classifications:
                    c = classifications[table.index]
                    table.classification = c['class']
                    table.classification_reason = c['reason']
                    table.confidence = c.get('confidence', 'medium')
                else:
                    self._log(f"    Warning: No classification for table {table.index}, marking UNKNOWN")
                    table.classification = "UNKNOWN"
                    table.classification_reason = "Missing from LLM response"
            
        except Exception as e:
            self._log(f"    ERROR: Batch classification failed after retries: {e}", level=logging.ERROR)
            for table in batch:
                table.classification = "UNKNOWN"
                table.classification_reason = f"LLM error: {str(e)[:50]}"
    
    def _build_classification_prompt(self, tables: list[TableInfo]) -> str:
        """Build classification prompt with structured table info."""
        
        table_entries = []
        for t in tables:
            indicators = []
            if t.has_stars:
                indicators.append("stars")
            if t.has_se_pattern:
                indicators.append("SE_pattern")
            if t.has_coef_terms:
                indicators.append("coef_terms")
            if t.has_pvalue_pattern:
                indicators.append("p-value/test")
            
            entry = f"""
--- TABLE {t.index} ---
Number: {t.table_number}
Caption: {t.caption}
Section: {t.section}
Page: {t.page_idx}
Indicators: {', '.join(indicators) if indicators else 'none'}
Structure: {t.row_count} rows × {t.col_count} columns
Body sample:
{t.body_sample}
Context in document: {t.context[:300] if t.context else '[No context found]'}
"""
            table_entries.append(entry)
        
        prompt = f"""You are an expert at analyzing impact evaluation research papers. Classify each table.

=== CATEGORIES ===

**RESULTS**: Treatment effects, regression coefficients, ITT/ATE/LATE, DiD, RDD results, robustness checks, statistical tests comparing treatments
**DESCRIPTIVE**: Balance tables, summary stats, baseline characteristics, attrition, compliance, outcome definitions, variable descriptions
**SKIP**: Response codes, survey codebooks (numeric codes like -99, -98), acronym lists, empty formatting artifacts

=== FEW-SHOT EXAMPLES ==={FEW_SHOT_EXAMPLES}
=== KEY RULES ===

1. Stars (*) on "Difference" column in balance tables = DESCRIPTIVE (testing pre-treatment balance)
2. Stars (*) on "Treatment" row with (SE) below = RESULTS (treatment effect)
3. Columns labeled (1), (2), (3) with coefficients = RESULTS (regression specifications)
4. "Mean", "SD", "N" columns without treatment = DESCRIPTIVE
5. Section matters: Tables in "Results" section are likely RESULTS
6. Appendix tables: RESULTS if showing robustness, DESCRIPTIVE if additional balance checks
7. If caption says "Impact", "Effect", "Treatment" = likely RESULTS
8. If caption says "Summary", "Baseline", "Balance" = likely DESCRIPTIVE
9. **P-VALUE TABLES ARE RESULTS**: Tables with "Test: T1 = T2" or similar treatment comparison tests ARE RESULTS (they show statistical significance of treatment differences)
10. Tables showing only N (sample sizes) at bottom of results tables = RESULTS (continuation/footer)
11. **OUTCOME DEFINITION TABLES ARE DESCRIPTIVE**: Tables listing "Primary outcomes", "Secondary outcomes" with variable names and descriptions = DESCRIPTIVE (they define study measures, not survey codes)
12. **Only mark as SKIP** if the table contains: numeric response codes (-99, -98), acronym expansions, or is truly empty/broken

=== TABLES TO CLASSIFY ===
{''.join(table_entries)}

=== RESPONSE FORMAT ===
Return a JSON array. CRITICAL: Use the EXACT index number shown after "TABLE" (e.g., TABLE 25 → "index": 25).
Include confidence (low/medium/high).

[
  {{"index": <EXACT_TABLE_NUMBER_FROM_PROMPT>, "class": "RESULTS|DESCRIPTIVE|SKIP", "reason": "5-15 words", "confidence": "low|medium|high"}}
]

JSON:"""
        
        return prompt
    
    def _call_llm_with_retry(self, prompt: str) -> str:
        """Call LLM with exponential backoff retry."""
        last_error = None
        for attempt in range(self.MAX_RETRIES):
            try:
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0,
                )
                content = response.choices[0].message.content
                if content is None:
                    raise ValueError("LLM returned None content")
                return content
            except Exception as e:
                last_error = e
                wait_time = 2 ** attempt  # 1, 2, 4 seconds
                self._log(f"    LLM call failed (attempt {attempt + 1}/{self.MAX_RETRIES}): {e}")
                if attempt < self.MAX_RETRIES - 1:
                    self._log(f"    Retrying in {wait_time}s...")
                    time.sleep(wait_time)
        raise RuntimeError(f"LLM call failed after {self.MAX_RETRIES} retries: {last_error}")
    
    def _parse_llm_response(self, response_text: str, batch: Optional[list[TableInfo]] = None) -> dict:
        """Parse LLM JSON response with robust extraction and validation."""
        classifications = {}
        valid_indices = {t.index for t in batch} if batch else set()
        
        try:
            # Find JSON array by locating first '[' and last ']'
            start = response_text.find('[')
            end = response_text.rfind(']')
            
            if start == -1 or end == -1 or end <= start:
                raise ValueError("No JSON array found in response")
            
            json_text = response_text[start:end + 1]
            results = json.loads(json_text)
            
            for item in results:
                # Safely extract and validate index
                try:
                    idx = int(item.get('index'))
                except (TypeError, ValueError):
                    self._log(f"    Warning: Invalid index in LLM response: {item.get('index')}")
                    continue
                
                # Validate index is in current batch
                if valid_indices and idx not in valid_indices:
                    self._log(f"    Warning: Index {idx} not in current batch, skipping")
                    continue
                
                # Extract and validate class
                cls = str(item.get('class', 'UNKNOWN')).upper()
                if cls not in ['RESULTS', 'DESCRIPTIVE', 'SKIP']:
                    cls = 'UNKNOWN'
                
                # Extract reason and confidence
                reason = str(item.get('reason', ''))
                confidence = str(item.get('confidence', 'medium')).lower()
                if confidence not in ['low', 'medium', 'high']:
                    confidence = 'medium'
                
                classifications[idx] = {
                    'class': cls,
                    'reason': reason,
                    'confidence': confidence
                }
                
        except json.JSONDecodeError as e:
            self._log(f"    JSON parse error: {e}", level=logging.ERROR)
            self._log(f"    Response snippet: {response_text[:800]}")
        except ValueError as e:
            self._log(f"    Response format error: {e}", level=logging.ERROR)
            self._log(f"    Response snippet: {response_text[:800]}")
        
        return classifications
    
    # =========================================================================
    # STEP 3: RECOVERY PASS
    # =========================================================================
    
    def _step3_recovery_pass(self):
        """Re-classify uncertain tables with more context."""
        self._log("\n[STEP 3] Recovery pass...")
        
        # Find candidates: SKIP/UNKNOWN with results indicators OR low confidence OR p-value tables
        recovery_candidates = [
            t for t in self.tables
            if not t.is_continuation and t.classification != 'EMPTY' and (
                # SKIP/UNKNOWN with results indicators
                (t.classification in ('SKIP', 'UNKNOWN') and (t.has_stars or t.has_se_pattern or t.has_pvalue_pattern)) or
                # Low confidence classifications
                (t.confidence == 'low') or
                # DESCRIPTIVE with strong results indicators (potential misclass)
                (t.classification == 'DESCRIPTIVE' and t.has_stars and t.has_se_pattern and t.has_coef_terms) or
                # SKIP with p-value pattern (statistical tests are results!)
                (t.classification == 'SKIP' and t.has_pvalue_pattern)
            )
        ]
        
        if not recovery_candidates:
            self._log("  No candidates for recovery")
            return
        
        self._log(f"  Found {len(recovery_candidates)} candidates for recovery")
        
        # Process in batches
        for batch_start in range(0, len(recovery_candidates), self.batch_size):
            batch_end = min(batch_start + self.batch_size, len(recovery_candidates))
            batch = recovery_candidates[batch_start:batch_end]
            
            self._recover_batch(batch)
        
        # Update continuations
        for table in self.tables:
            if table.is_continuation and table.continuation_of >= 0:
                parent = self.tables[table.continuation_of]
                table.classification = parent.classification
        
        self._log_classification_summary("After Step 3 (Final)")
    
    def _recover_batch(self, batch: list[TableInfo]):
        """Recovery classification with extended body content."""
        
        table_entries = []
        for t in batch:
            # Get more body content for recovery
            soup = BeautifulSoup(t.html_body, 'html.parser') if t.html_body else None
            full_text = soup.get_text(separator=' ', strip=True)[:800] if soup else t.body_sample
            
            entry = f"""
--- TABLE {t.index} ---
Original classification: {t.classification} (confidence: {t.confidence})
Original reason: {t.classification_reason}
Caption: {t.caption}
Section: {t.section}
Has stars: {t.has_stars}, Has SE: {t.has_se_pattern}, Has coef terms: {t.has_coef_terms}, Has p-value/test: {t.has_pvalue_pattern}

EXTENDED BODY CONTENT:
{full_text}

Context: {t.context[:400] if t.context else '[None]'}
"""
            table_entries.append(entry)
        
        prompt = f"""You are reviewing tables that may have been misclassified. 

REVIEW CRITERIA:
- SKIP → RESULTS if: Has actual treatment coefficients with SEs (not just asterisks as footnote markers)
- DESCRIPTIVE → RESULTS if: Stars are on treatment coefficients (not balance test differences)
- Keep current classification if the original assessment was correct

Tables to review:
{''.join(table_entries)}

JSON response. CRITICAL: Use the EXACT index number shown after "TABLE" (e.g., TABLE 75 → "index": 75).
Include all tables, keeping or changing their classification:
[
  {{"index": <EXACT_TABLE_NUMBER_FROM_PROMPT>, "class": "RESULTS|DESCRIPTIVE|SKIP", "reason": "why kept/reclassified", "confidence": "medium|high"}}
]

JSON:"""
        
        try:
            response_text = self._call_llm_with_retry(prompt)
            classifications = self._parse_llm_response(response_text, batch)
            
            # Apply reclassifications
            for table in batch:
                if table.index in classifications:
                    new = classifications[table.index]
                    if new['class'] != table.classification:
                        old_class = table.classification
                        table.classification = new['class']
                        table.classification_reason = f"[Recovered] {new['reason']}"
                        table.confidence = new.get('confidence', 'medium')
                        self._log(f"    Recovered {table.index}: {old_class} → {new['class']}")
                    else:
                        # Update confidence if same class
                        if new.get('confidence') == 'high':
                            table.confidence = 'high'
            
        except Exception as e:
            self._log(f"    Recovery error: {e}", level=logging.ERROR)
    
    # =========================================================================
    # UTILITIES
    # =========================================================================
    
    def _log(self, msg: str, level: int = logging.INFO):
        """Log message using logging module."""
        if self.verbose:
            logger.log(level, msg)
    
    def _log_classification_summary(self, stage: str):
        """Log classification counts."""
        results = sum(1 for t in self.tables if t.classification == 'RESULTS')
        descriptive = sum(1 for t in self.tables if t.classification == 'DESCRIPTIVE')
        skip = sum(1 for t in self.tables if t.classification == 'SKIP')
        unknown = sum(1 for t in self.tables if t.classification == 'UNKNOWN')
        empty = sum(1 for t in self.tables if t.classification == 'EMPTY')
        
        high_conf = sum(1 for t in self.tables if t.confidence == 'high')
        low_conf = sum(1 for t in self.tables if t.confidence == 'low')
        
        self._log(f"\n  {stage}:")
        self._log(f"    RESULTS: {results}, DESCRIPTIVE: {descriptive}, SKIP: {skip}, EMPTY: {empty}, UNKNOWN: {unknown}")
        self._log(f"    Confidence: {high_conf} high, {len(self.tables) - high_conf - low_conf} medium, {low_conf} low")
    
    # =========================================================================
    # OUTPUT
    # =========================================================================
    
    def get_results_tables(self) -> list[TableInfo]:
        """Get tables classified as RESULTS."""
        return [t for t in self.tables if t.classification == 'RESULTS']
    
    def get_classification_summary(self) -> dict:
        """Get summary of classification results."""
        summary = {
            'total_tables': len(self.tables),
            'results': sum(1 for t in self.tables if t.classification == 'RESULTS'),
            'descriptive': sum(1 for t in self.tables if t.classification == 'DESCRIPTIVE'),
            'skip': sum(1 for t in self.tables if t.classification == 'SKIP'),
            'empty': sum(1 for t in self.tables if t.classification == 'EMPTY'),
            'unknown': sum(1 for t in self.tables if t.classification == 'UNKNOWN'),
            'continuations': sum(1 for t in self.tables if t.is_continuation),
            'high_confidence': sum(1 for t in self.tables if t.confidence == 'high'),
            'low_confidence': sum(1 for t in self.tables if t.confidence == 'low'),
        }
        # Add postprocessing stats if available
        if self.postprocessing_stats:
            summary['artifacts_removed'] = self.postprocessing_stats.get('artifacts_removed', 0)
            summary['tables_merged'] = self.postprocessing_stats.get('tables_merged', 0)
            summary['lot_repairs'] = self.postprocessing_stats.get('lot_repairs', 0)
        return summary
    
    def to_dataframe(self):
        """Export results to pandas DataFrame."""
        import pandas as pd
        
        rows = []
        for t in self.tables:
            rows.append({
                'index': t.index,
                'page': t.page_idx,
                'table_number': t.table_number,
                'caption': t.caption[:150],
                'section': t.section,
                'is_continuation': t.is_continuation,
                'classification': t.classification,
                'confidence': t.confidence,
                'reason': t.classification_reason,
                'has_stars': t.has_stars,
                'has_se': t.has_se_pattern,
                'has_pvalue': t.has_pvalue_pattern,
                'rows': t.row_count,
                'cols': t.col_count,
            })
        
        return pd.DataFrame(rows)


# =============================================================================
# Test
# =============================================================================

if __name__ == '__main__':
    from dotenv import load_dotenv
    import boto3
    
    # Load environment variables only when running as script
    load_dotenv()
    
    print("Loading document...")
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
    
    obj = r2.get_object(Bucket=BUCKET, Key=key)
    doc = json.loads(obj['Body'].read().decode('utf-8'))
    
    # Run classifier
    classifier = TableClassifierV3(doc, study_id="121058367", verbose=True)
    tables = classifier.run_pipeline()
    
    # Print summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    summary = classifier.get_classification_summary()
    for k, v in summary.items():
        print(f"  {k}: {v}")
    
    # Export to CSV
    df = classifier.to_dataframe()
    output_path = 'extraction_pipeline/outputs/classification_v3_test.csv'
    df.to_csv(output_path, index=False)
    print(f"\nSaved to: {output_path}")
    
    # Show some examples
    print("\n" + "=" * 80)
    print("SAMPLE RESULTS TABLES")
    print("=" * 80)
    results = classifier.get_results_tables()[:10]
    for t in results:
        print(f"\n{t.table_number} (page {t.page_idx}, {t.confidence} confidence)")
        print(f"  Caption: {t.caption[:80]}...")
        print(f"  Section: {t.section}")
        print(f"  Reason: {t.classification_reason}")
