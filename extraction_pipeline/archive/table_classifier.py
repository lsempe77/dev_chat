"""
Table Classification Pipeline - Step-by-step logical approach.

STEP 1: Extract all table references from document content (markdown)
STEP 2: Match table HTML elements to their captions
STEP 3: Detect continuation tables (inherit parent caption)
STEP 4: Classify as RESULTS / DESCRIPTIVE / SKIP

Author: DevChat Pipeline
"""
import re
import json
from dataclasses import dataclass, field
from typing import Optional
from bs4 import BeautifulSoup


@dataclass
class TableReference:
    """A table reference found in document content."""
    table_number: str          # "Table 4.1", "Table A1", etc.
    caption: str               # Full caption text
    page_mentioned: int = -1   # Page where caption appears (if known)
    section: str = ""          # Section where table is referenced (e.g., "Results")
    

@dataclass 
class TableElement:
    """A table HTML element from the tables array."""
    index: int                 # Index in tables array
    page_idx: int              # Page where table appears
    html_body: str             # Raw HTML
    caption_field: str         # From table_caption field (may be empty)
    
    # Populated by matching step
    matched_caption: str = ""
    matched_table_number: str = ""
    is_continuation: bool = False
    continuation_of: int = -1  # Index of parent table
    
    # Populated by classification step
    classification: str = "UNKNOWN"  # RESULTS, DESCRIPTIVE, SKIP, UNKNOWN
    classification_reason: str = ""


class TableClassifier:
    """
    Multi-step table classification pipeline.
    """
    
    def __init__(self, doc: dict, verbose: bool = False):
        self.doc = doc
        self.verbose = verbose
        self.content = doc.get('content', '')
        self.tables_raw = doc.get('tables', [])
        
        # Outputs
        self.table_references: list[TableReference] = []
        self.table_elements: list[TableElement] = []
        
    def run_pipeline(self) -> list[TableElement]:
        """Execute full classification pipeline."""
        self._log("=" * 80)
        self._log("TABLE CLASSIFICATION PIPELINE")
        self._log("=" * 80)
        
        # Step 1: Extract table references from content
        self._step1_extract_references()
        
        # Step 2: Parse table elements and match to captions
        self._step2_match_captions()
        
        # Step 3: Detect continuation tables
        self._step3_detect_continuations()
        
        # Step 4: Classify tables
        self._step4_classify()
        
        return self.table_elements
    
    # =========================================================================
    # STEP 1: Extract all table references from document content
    # =========================================================================
    
    def _step1_extract_references(self):
        """
        Parse markdown content to find all table mentions WITH CONTEXT.
        
        The context around the table mention is the ONLY reliable signal:
        - "Table 3 presents our main results..." → RESULTS
        - "We test for balance in Table 2..." → DESCRIPTIVE  
        - "Table 1 shows baseline characteristics..." → DESCRIPTIVE
        """
        self._log("\n[STEP 1] Extracting table references WITH CONTEXT...")
        
        if not self.content:
            self._log("  WARNING: No content field in document!")
            return
        
        # Find all table mentions with surrounding context (100 chars before, 200 after)
        # This captures the sentence where the table is mentioned
        pattern = r'.{0,100}(Table\s+[\dA-Z]+\.?\d*[a-z]?)[:\.]?\s*([^\n]{0,200})'
        
        seen_tables = {}  # table_number -> TableReference
        
        for match in re.finditer(pattern, self.content, re.IGNORECASE):
            context_before = match.group(0)[:100]
            table_num = match.group(1)
            context_after = match.group(2)
            
            full_context = (context_before + ' ' + context_after).lower()
            
            # Normalize table number
            table_num_norm = re.sub(r'\s+', ' ', table_num.strip())
            key = table_num_norm.lower()
            
            # Classify based on CONTEXT (not table structure!)
            context_class = self._classify_from_context(full_context)
            
            # Get caption if present (text right after "Table X:")
            caption = context_after.strip()[:150] if context_after else ''
            
            # Keep best classification for each table
            if key not in seen_tables:
                seen_tables[key] = TableReference(
                    table_number=table_num_norm,
                    caption=caption,
                    section=context_class  # Using section field for context-based class
                )
            else:
                # Update if we found a clearer context signal
                existing = seen_tables[key]
                if existing.section == 'UNKNOWN' and context_class != 'UNKNOWN':
                    existing.section = context_class
                # Keep longer caption
                if len(caption) > len(existing.caption):
                    existing.caption = caption
        
        self.table_references = list(seen_tables.values())
        
        # Count classifications
        results_count = sum(1 for r in self.table_references if r.section == 'RESULTS')
        desc_count = sum(1 for r in self.table_references if r.section == 'DESCRIPTIVE')
        unknown_count = sum(1 for r in self.table_references if r.section == 'UNKNOWN')
        
        self._log(f"  Found {len(self.table_references)} unique table references")
        self._log(f"    - RESULTS (from context): {results_count}")
        self._log(f"    - DESCRIPTIVE (from context): {desc_count}")
        self._log(f"    - UNKNOWN: {unknown_count}")
    
    def _classify_from_context(self, context: str) -> str:
        """
        Classify table based on the surrounding text context.
        This is the MOST RELIABLE signal.
        """
        context = context.lower()
        
        # =====================================================================
        # RESULTS indicators in context
        # =====================================================================
        results_context = [
            # Explicit results language
            r'main\s+results?', r'our\s+results?', r'key\s+results?',
            r'presents?\s+(?:the\s+)?results?', r'shows?\s+(?:the\s+)?results?',
            r'reports?\s+(?:the\s+)?results?', r'displays?\s+(?:the\s+)?results?',
            
            # Treatment effects
            r'treatment\s+effects?', r'program\s+effects?', r'intervention\s+effects?',
            r'causal\s+effects?', r'impacts?\s+of', r'effects?\s+of\s+(?:the\s+)?(?:program|treatment|intervention)',
            
            # Estimation language
            r'estimates?\s+(?:of|from)', r'regression\s+results?',
            r'itt\s+estimates?', r'ate\s+estimates?', r'late\s+estimates?',
            r'(?:ols|iv|2sls|did|rdd)\s+(?:results?|estimates?)',
            
            # Robustness/heterogeneity
            r'robustness', r'heterogen', r'subgroup\s+(?:analysis|results?)',
            r'specification', r'sensitivity',
            
            # Spanish
            r'resultados?\s+(?:principales?|del\s+programa)',
            r'efectos?\s+del\s+(?:tratamiento|programa)',
            r'impactos?\s+del',
        ]
        
        for pattern in results_context:
            if re.search(pattern, context):
                return 'RESULTS'
        
        # =====================================================================
        # DESCRIPTIVE indicators in context
        # =====================================================================
        descriptive_context = [
            # Balance/baseline
            r'balance\s+(?:test|table|check)', r'tests?\s+for\s+balance',
            r'baseline\s+(?:characteristics?|statistics?|comparisons?)',
            r'pre-?treatment\s+(?:characteristics?|means?)',
            r'pre-?intervention',
            
            # Summary/descriptive
            r'summary\s+statistics?', r'descriptive\s+statistics?',
            r'sample\s+(?:characteristics?|description|statistics?)',
            r'demographic\s+(?:characteristics?|information)',
            r'socioeconomic\s+(?:characteristics?|variables?)',
            
            # Attrition/compliance
            r'attrition', r'compliance', r'take-?up',
            r'sample\s+(?:size|composition|selection)',
            
            # Comparison language (for balance)
            r'compares?\s+(?:treatment|control)\s+(?:and|groups?)',
            r'(?:treatment|control)\s+(?:group\s+)?means?',
            
            # Spanish  
            r'características\s+(?:de\s+la\s+muestra|basales?)',
            r'estadísticas?\s+descriptivas?',
            r'balance\s+de\s+(?:grupos?|muestras?)',
        ]
        
        for pattern in descriptive_context:
            if re.search(pattern, context):
                return 'DESCRIPTIVE'
        
        return 'UNKNOWN'
        
    def _detect_results_section_tables(self):
        """Find tables mentioned in results-like sections.
        
        Handles grey literature, appendices, and non-standard structures.
        Looks for: Results, Findings, Impact, Analysis, Empirical, Appendix, etc.
        """
        # Multiple section patterns for different document types
        results_section_patterns = [
            r'(?:^|\n)#+\s*(?:\d+\.?\s*)?Results?\b',
            r'(?:^|\n)#+\s*(?:\d+\.?\s*)?Findings?\b',
            r'(?:^|\n)#+\s*(?:\d+\.?\s*)?Impact\s+(?:Analysis|Evaluation|Assessment)',
            r'(?:^|\n)#+\s*(?:\d+\.?\s*)?Empirical\s+(?:Results|Analysis|Findings)',
            r'(?:^|\n)#+\s*(?:\d+\.?\s*)?(?:Main|Key)\s+(?:Results|Findings)',
            r'(?:^|\n)#+\s*(?:\d+\.?\s*)?Treatment\s+Effects?',
            r'(?:^|\n)#+\s*(?:\d+\.?\s*)?Program\s+(?:Impact|Effects?)',
            r'(?:^|\n)#+\s*(?:\d+\.?\s*)?Regression\s+(?:Results|Analysis)',
            r'(?:^|\n)#+\s*(?:\d+\.?\s*)?Econometric\s+(?:Results|Analysis)',
            # Appendix tables are often results!
            r'(?:^|\n)#+\s*(?:\d+\.?\s*)?(?:Statistical\s+)?Appendix',
            r'(?:^|\n)#+\s*(?:\d+\.?\s*)?Appendix\s*[A-Z]?\s*[:\.]?\s*(?:Results|Tables)',
            # Spanish
            r'(?:^|\n)#+\s*(?:\d+\.?\s*)?Resultados?\b',
            r'(?:^|\n)#+\s*(?:\d+\.?\s*)?Impacto\b',
            # Portuguese  
            r'(?:^|\n)#+\s*(?:\d+\.?\s*)?Resultados?\b',
            # French
            r'(?:^|\n)#+\s*(?:\d+\.?\s*)?Résultats?\b',
        ]
        
        tables_in_results_sections = set()
        
        for pattern in results_section_patterns:
            for match in re.finditer(pattern, self.content, re.IGNORECASE):
                section_start = match.end()
                # Find next section (any heading)
                next_section = re.search(r'(?:^|\n)#+\s', self.content[section_start:])
                section_end = section_start + next_section.start() if next_section else len(self.content)
                section_text = self.content[section_start:section_end]
                
                # Find tables mentioned in this section
                for table_match in re.finditer(r'Table\s+([\dA-Z]+\.?\d*[a-z]?)', section_text, re.IGNORECASE):
                    tables_in_results_sections.add(f"table {table_match.group(1).lower()}")
        
        if tables_in_results_sections:
            self._log(f"  Tables in results/findings/appendix sections: {len(tables_in_results_sections)}")
        else:
            self._log("  No standard results sections found (will rely on content analysis)")
        
        # Mark table references
        for ref in self.table_references:
            key = ref.table_number.lower()
            if key in tables_in_results_sections:
                ref.section = "Results"
    
    # =========================================================================
    # STEP 2: Parse table elements and match to captions
    # =========================================================================
    
    def _step2_match_captions(self):
        """Match table HTML elements to their captions."""
        self._log("\n[STEP 2] Matching table elements to captions...")
        
        # Parse all table elements
        for i, table in enumerate(self.tables_raw):
            caption_list = table.get('table_caption', [])
            caption_field = ' '.join(caption_list).strip() if caption_list else ''
            
            elem = TableElement(
                index=i,
                page_idx=table.get('page_idx', -1),
                html_body=table.get('table_body', ''),
                caption_field=caption_field
            )
            self.table_elements.append(elem)
        
        self._log(f"  Parsed {len(self.table_elements)} table elements")
        
        # Build lookup from table number -> TableReference
        ref_lookup = {}
        for ref in self.table_references:
            key = ref.table_number.lower()
            ref_lookup[key] = ref
        
        # Match each table element
        matched_count = 0
        for elem in self.table_elements:
            # Try 1: Use caption_field if present
            if elem.caption_field and len(elem.caption_field) > 10:
                table_num_match = re.search(
                    r'(Table\s+[\dA-Z]+\.?\d*[a-z]?)',
                    elem.caption_field,
                    re.IGNORECASE
                )
                if table_num_match:
                    elem.matched_table_number = table_num_match.group(1)
                    elem.matched_caption = elem.caption_field
                    
                    # Also get section info from references
                    key = elem.matched_table_number.lower()
                    if key in ref_lookup:
                        ref = ref_lookup[key]
                        if ref.section:
                            elem.classification_reason += f"In {ref.section} section. "
                    
                    matched_count += 1
                    continue
            
            # Try 2: Look for table number in HTML body
            if elem.html_body:
                soup = BeautifulSoup(elem.html_body, 'html.parser')
                text = soup.get_text(separator=' ', strip=True)[:500]
                
                table_num_match = re.search(
                    r'(Table\s+[\dA-Z]+\.?\d*[a-z]?)',
                    text,
                    re.IGNORECASE
                )
                if table_num_match:
                    table_num = table_num_match.group(1)
                    key = table_num.lower()
                    
                    if key in ref_lookup:
                        elem.matched_table_number = table_num
                        elem.matched_caption = f"{table_num}: {ref_lookup[key].caption}"
                        elem.classification_reason += "Caption from content. "
                        
                        if ref_lookup[key].section:
                            elem.classification_reason += f"In {ref_lookup[key].section} section. "
                        
                        matched_count += 1
        
        no_caption = sum(1 for e in self.table_elements if not e.matched_caption)
        self._log(f"  Matched captions: {matched_count}")
        self._log(f"  Without caption: {no_caption}")
    
    # =========================================================================
    # STEP 3: Detect continuation tables
    # =========================================================================
    
    def _step3_detect_continuations(self):
        """Identify tables that are continuations of previous tables."""
        self._log("\n[STEP 3] Detecting continuation tables...")
        
        continuation_count = 0
        
        for i, elem in enumerate(self.table_elements):
            if elem.matched_caption:
                continue  # Already has caption, not a continuation
            
            if i == 0:
                continue  # First table can't be continuation
            
            prev = self.table_elements[i - 1]
            
            # Rule 1: Same page as previous table with caption
            if elem.page_idx == prev.page_idx and prev.matched_caption:
                elem.is_continuation = True
                elem.continuation_of = i - 1
                elem.matched_caption = f"[Continuation] {prev.matched_caption}"
                elem.matched_table_number = prev.matched_table_number
                elem.classification_reason += "Same page as captioned table. "
                continuation_count += 1
                continue
            
            # Rule 2: Previous table was also continuation (chain)
            if prev.is_continuation:
                parent_idx = prev.continuation_of
                parent = self.table_elements[parent_idx]
                elem.is_continuation = True
                elem.continuation_of = parent_idx
                elem.matched_caption = f"[Continuation] {parent.matched_caption}"
                elem.matched_table_number = parent.matched_table_number
                elem.classification_reason += "Part of multi-page table. "
                continuation_count += 1
                continue
            
            # Rule 3: Check for "(continued)" text in body
            if elem.html_body:
                soup = BeautifulSoup(elem.html_body, 'html.parser')
                text = soup.get_text(separator=' ', strip=True)[:200].lower()
                if 'continued' in text or 'cont.' in text:
                    # Find most recent captioned table
                    for j in range(i - 1, -1, -1):
                        if self.table_elements[j].matched_caption and not self.table_elements[j].is_continuation:
                            elem.is_continuation = True
                            elem.continuation_of = j
                            elem.matched_caption = f"[Continuation] {self.table_elements[j].matched_caption}"
                            elem.matched_table_number = self.table_elements[j].matched_table_number
                            elem.classification_reason += "Has 'continued' text. "
                            continuation_count += 1
                            break
        
        self._log(f"  Identified {continuation_count} continuation tables")
    
    # =========================================================================
    # STEP 4: Classify tables
    # =========================================================================
    
    def _step4_classify(self):
        """Classify each table as RESULTS, DESCRIPTIVE, or SKIP."""
        self._log("\n[STEP 4] Classifying tables...")
        
        for elem in self.table_elements:
            self._classify_single_table(elem)
        
        # Summary
        results = sum(1 for e in self.table_elements if e.classification == 'RESULTS')
        descriptive = sum(1 for e in self.table_elements if e.classification == 'DESCRIPTIVE')
        skip = sum(1 for e in self.table_elements if e.classification == 'SKIP')
        unknown = sum(1 for e in self.table_elements if e.classification == 'UNKNOWN')
        
        self._log(f"  RESULTS: {results}")
        self._log(f"  DESCRIPTIVE: {descriptive}")
        self._log(f"  SKIP: {skip}")
        self._log(f"  UNKNOWN: {unknown}")
    
    def _classify_single_table(self, elem: TableElement):
        """
        Classify table using CONTEXT-FIRST approach.
        
        Priority:
        1. Context from document text (MOST RELIABLE)
        2. Caption keywords (secondary)
        3. Table structure (LAST RESORT - often ambiguous)
        """
        caption_lower = elem.matched_caption.lower() if elem.matched_caption else ''
        
        # =================================================================
        # STEP A: Quick SKIP checks
        # =================================================================
        skip_keywords = [
            'table of contents', 'abbreviation', 'acronym', 'glossary',
            'survey', 'questionnaire', 'codebook', 'variable list',
        ]
        if any(kw in caption_lower for kw in skip_keywords):
            elem.classification = 'SKIP'
            elem.classification_reason = "Caption indicates non-data table."
            return
        
        # =================================================================
        # STEP B: USE CONTEXT-BASED CLASSIFICATION (from Step 1)
        # This is the MOST RELIABLE signal
        # =================================================================
        
        # Look up table in references to get context-based classification
        table_num_lower = elem.matched_table_number.lower() if elem.matched_table_number else ''
        
        for ref in self.table_references:
            if ref.table_number.lower() == table_num_lower:
                if ref.section == 'RESULTS':
                    elem.classification = 'RESULTS'
                    elem.classification_reason = "Document context indicates results table."
                    return
                elif ref.section == 'DESCRIPTIVE':
                    elem.classification = 'DESCRIPTIVE'
                    elem.classification_reason = "Document context indicates descriptive table."
                    return
                # else UNKNOWN, continue to other checks
                break
        
        # =================================================================
        # STEP C: Caption-based classification (secondary signal)
        # =================================================================
        
        # Results captions
        results_caption_keywords = [
            'impact of', 'effect of', 'treatment effect', 'regression result',
            'program effect', 'intervention effect', 'causal effect',
            'itt estimate', 'ate estimate', 'main result', 'heterogen',
            'robustness', 'specification', 'did result', 'rdd result',
            'impacto', 'efecto del', 'resultados',  # Spanish
        ]
        if any(kw in caption_lower for kw in results_caption_keywords):
            elem.classification = 'RESULTS'
            elem.classification_reason = "Caption indicates results."
            return
        
        # Descriptive captions
        descriptive_caption_keywords = [
            'balance', 'baseline characteristic', 'summary statistic',
            'descriptive', 'pre-treatment', 'sample characteristic',
            'demographic', 'socioeconomic', 'attrition', 'compliance',
            'sample composition', 'características', 'estadísticas descriptivas',
        ]
        if any(kw in caption_lower for kw in descriptive_caption_keywords):
            elem.classification = 'DESCRIPTIVE'
            elem.classification_reason = "Caption indicates descriptive."
            return
        
        # =================================================================
        # STEP D: Structure analysis (LAST RESORT - often ambiguous!)
        # =================================================================
        
        structure = self._analyze_table_structure(elem.html_body)
        
        # Only use structure if we have VERY strong signals
        # Model columns (1), (2), (3) WITHOUT balance columns → likely regression
        if structure.get('has_model_columns') and not structure.get('has_balance_columns'):
            if structure.get('has_stars'):
                elem.classification = 'RESULTS'
                elem.classification_reason = "Structure: model columns with stars, no balance columns."
                return
        
        # =================================================================
        # STEP E: No caption → SKIP
        # =================================================================
        if not elem.matched_caption or elem.matched_caption == '[No caption]':
            elem.classification = 'SKIP'
            elem.classification_reason = "No caption, cannot classify."
            return
        
        # =================================================================
        # STEP F: Default to UNKNOWN (needs manual review or LLM)
        # =================================================================
        elem.classification = 'UNKNOWN'
        elem.classification_reason = "Context and caption ambiguous."
    
    def _has_significance_stars(self, html: str) -> bool:
        """Check for significance stars (*, **, ***) next to coefficients."""
        if not html:
            return False
        
        # Pattern: number followed by 1-3 asterisks
        # Examples: 0.287***, -0.15**, 0.05 *
        if re.search(r'-?\d+\.\d+\s*\*{1,3}(?!\*)', html):
            return True
        
        return False
    
    def _analyze_table_structure(self, html: str) -> dict:
        """
        Analyze table structure to distinguish regression from descriptive.
        
        KEY INSIGHT: Both can have stars! 
        - Descriptive: stars on difference between group MEANS (balance tables)
        - Regression: stars on COEFFICIENTS
        
        Returns dict with signals for classification.
        """
        if not html:
            return {'analyzable': False}
        
        soup = BeautifulSoup(html, 'html.parser')
        text = soup.get_text(separator=' ', strip=True)
        text_lower = text.lower()
        
        signals = {
            'analyzable': True,
            'has_stars': bool(re.search(r'-?\d+\.\d+\s*\*{1,3}(?!\*)', html)),
        }
        
        # Check column headers (first row or thead)
        headers = []
        thead = soup.find('thead')
        if thead:
            headers = [th.get_text(strip=True).lower() for th in thead.find_all(['th', 'td'])]
        else:
            first_row = soup.find('tr')
            if first_row:
                headers = [cell.get_text(strip=True).lower() for cell in first_row.find_all(['th', 'td'])]
        
        header_text = ' '.join(headers)
        
        # =====================================================================
        # REGRESSION TABLE signals (looking for MODEL specifications)
        # =====================================================================
        
        # Model specification columns: (1), (2), (3) OR "Model 1", "OLS", "IV"
        model_headers = [
            '(1)', '(2)', '(3)', '(4)', '(5)', '(6)', '(7)', '(8)',
            'model 1', 'model 2', 'model 3', 'model 4',
            'ols', 'iv', '2sls', 'fe', 'fixed effect', 're', 'random effect',
            'specification', 'baseline', 'full controls', 'controls',
        ]
        has_model_columns = any(h in header_text for h in model_headers)
        
        # Treatment effect row labels (in rows, not headers)
        treatment_row_patterns = [
            r'\btreatment\b', r'\btreated?\b', r'\bprogram\b', r'\bintervention\b',
            r'\btreatment\s*[×x]\s*post\b', r'\bdid\b', r'\bpost\s*[×x]\s*treat',
            r'\bitt\b', r'\bate\b', r'\blate\b', r'\btot\b',
            r'\baverage\s+effect\b', r'\btreatment\s+effect\b',
            r'\btratamiento\b', r'\bimpacto\b',  # Spanish
        ]
        has_treatment_rows = any(re.search(p, text_lower) for p in treatment_row_patterns)
        
        # =====================================================================
        # BALANCE/DESCRIPTIVE TABLE signals
        # =====================================================================
        
        # Group comparison columns: Treatment vs Control (descriptive)
        balance_headers = [
            'treatment', 'control', 'treated', 'untreated',
            'comparison', 'difference', 'diff', 't-stat', 't-test',
            'treatment group', 'control group', 'comparison group',
        ]
        has_balance_columns = sum(1 for h in balance_headers if h in header_text) >= 2
        
        # Summary statistic columns
        summary_headers = ['mean', 'std', 'sd', 'std.', 'n', 'obs', 'min', 'max', 'median']
        has_summary_columns = sum(1 for h in summary_headers if h in header_text) >= 2
        
        # Variable names as row labels (demographic/socioeconomic)
        variable_row_patterns = [
            r'\bage\b', r'\beducation\b', r'\bincome\b', r'\bfemale\b', r'\bmale\b',
            r'\bmarried\b', r'\bhousehold\s+size\b', r'\bassets?\b', r'\bwealth\b',
            r'\bliteracy\b', r'\bemployment\b', r'\bchildren\b',
        ]
        variable_row_count = sum(1 for p in variable_row_patterns if re.search(p, text_lower))
        has_demographic_rows = variable_row_count >= 3
        
        # =====================================================================
        # SCORING
        # =====================================================================
        
        regression_score = 0
        descriptive_score = 0
        
        # Regression signals
        if has_model_columns:
            regression_score += 3  # Strong: (1), (2), (3) columns
        if has_treatment_rows:
            regression_score += 2  # Treatment as a ROW (not column header)
        
        # Descriptive signals  
        if has_balance_columns:
            descriptive_score += 3  # Strong: Treatment/Control as COLUMNS
        if has_summary_columns:
            descriptive_score += 2
        if has_demographic_rows:
            descriptive_score += 2
        
        # Stars alone are NOT informative (both types can have them)
        # Only use stars if no other signals
        
        signals['has_model_columns'] = has_model_columns
        signals['has_treatment_rows'] = has_treatment_rows
        signals['has_balance_columns'] = has_balance_columns
        signals['has_summary_columns'] = has_summary_columns
        signals['has_demographic_rows'] = has_demographic_rows
        signals['regression_score'] = regression_score
        signals['descriptive_score'] = descriptive_score
        signals['net_score'] = regression_score - descriptive_score  # Positive = regression
        
        return signals
    
    def _log(self, msg: str):
        """Print log message if verbose."""
        if self.verbose:
            print(msg)
    
    # =========================================================================
    # Output methods
    # =========================================================================
    
    def get_results_tables(self) -> list[TableElement]:
        """Get tables classified as RESULTS."""
        return [e for e in self.table_elements if e.classification == 'RESULTS']
    
    def get_classification_summary(self) -> dict:
        """Get summary of classification results."""
        return {
            'total_tables': len(self.table_elements),
            'total_references': len(self.table_references),
            'results': sum(1 for e in self.table_elements if e.classification == 'RESULTS'),
            'descriptive': sum(1 for e in self.table_elements if e.classification == 'DESCRIPTIVE'),
            'skip': sum(1 for e in self.table_elements if e.classification == 'SKIP'),
            'unknown': sum(1 for e in self.table_elements if e.classification == 'UNKNOWN'),
            'continuations': sum(1 for e in self.table_elements if e.is_continuation),
            'matched_captions': sum(1 for e in self.table_elements if e.matched_caption and '[Continuation]' not in e.matched_caption),
        }
    
    def to_dataframe(self):
        """Export classification to pandas DataFrame."""
        import pandas as pd
        
        rows = []
        for elem in self.table_elements:
            rows.append({
                'index': elem.index,
                'page': elem.page_idx,
                'table_number': elem.matched_table_number or f'Table{elem.index + 1}',
                'caption': elem.matched_caption[:200] if elem.matched_caption else '[No caption]',
                'is_continuation': elem.is_continuation,
                'continuation_of': elem.continuation_of if elem.is_continuation else '',
                'classification': elem.classification,
                'reason': elem.classification_reason,
            })
        
        return pd.DataFrame(rows)


# =============================================================================
# Test on a single document
# =============================================================================

if __name__ == '__main__':
    import boto3
    import os
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
    
    # Test with the sample document
    key = 'rags/0816e8d3-ab23-417c-bf3f-e45531411c73/outputs/json/1f44cd8c70b8_PDFs_of_included_programs_121058367.json'
    
    print("Loading document...")
    response = r2.get_object(Bucket=BUCKET, Key=key)
    doc = json.loads(response['Body'].read().decode('utf-8'))
    
    # Run pipeline
    classifier = TableClassifier(doc, verbose=True)
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
    print("CLASSIFICATION DETAILS (first 30 rows)")
    print("=" * 80)
    print(df.head(30).to_string(index=False))
    
    # Save
    df.to_csv('extraction_pipeline/outputs/classification_test.csv', index=False)
    print("\nSaved to: extraction_pipeline/outputs/classification_test.csv")
