"""
MinerU Post-Processing Module

Level 2 post-processing to clean MinerU parsing artifacts BEFORE classification.
Handles issues that require semantic understanding or cross-table context.

Pipeline:
  0.1 Empty Filter     - Remove tables with no body content
  0.2 Figure Detection - Detect figures misclassified as tables
  0.3 Diagram Detection - Detect single-row diagrams/legends
  0.4 Text Fragment    - Detect text fragments parsed as tables
  0.5 Split Merge      - Merge tables split across pages
  0.6 Header Graft     - Match orphan headers to body tables
  0.7 LLM Verify       - LLM verification for edge cases (optional)
  0.8 LOT Cross-Ref    - Use List of Tables for caption repair (optional)

Author: DevChat Pipeline
"""
import re
import json
import os
import logging
from dataclasses import dataclass, field
from typing import Optional
from bs4 import BeautifulSoup
from collections import defaultdict

logger = logging.getLogger(__name__)

# =============================================================================
# REGEX PATTERNS
# =============================================================================

# Figure detection patterns
FIGURE_PATTERNS = [
    re.compile(r'\bfigure\s*\d', re.IGNORECASE),
    re.compile(r'\bfig\.?\s*\d', re.IGNORECASE),
    re.compile(r'\bfigura\s*\d', re.IGNORECASE),  # Spanish
    re.compile(r'\bfigure\s*[A-Z]\d', re.IGNORECASE),  # Figure A1
]

# Table number extraction
TABLE_NUMBER_PATTERNS = [
    re.compile(r'(Table|Tableau|Tabla|Tabelle)\s*([\dA-Z]+\.?\d*[a-z]?)', re.IGNORECASE),
]

# Text fragment patterns (paragraph text that shouldn't be a table)
TEXT_FRAGMENT_PATTERNS = [
    re.compile(r'Table\s*\d+[:\)]\s*\d+\)', re.IGNORECASE),  # "Table 3: 3). In Amhara..."
    re.compile(r'\.\s*\d+\s+percent', re.IGNORECASE),         # Embedded statistics
    re.compile(r'\b(households|women|children|percent)\b.*\b(were|had|showed|reported)\b', re.IGNORECASE),
    re.compile(r'[.!?]\s+[A-Z][a-z]+\s+\w+\s+\w+', re.IGNORECASE),  # Sentence structure
]

# Diagram/legend patterns (single-row non-data tables)
DIAGRAM_PATTERNS = [
    re.compile(r'(\w+\s*(=|:)\s*\w+.*){2,}'),  # "Code = Description" repeated
    re.compile(r'(baseline|midline|endline)\s*.*\d{4}', re.IGNORECASE),  # Timeline
    re.compile(r'(T\d|C\d|Control|Treatment)\s*[:=→]', re.IGNORECASE),  # Treatment arm diagram
]

# Header row indicators
HEADER_WORDS = [
    'variable', 'outcome', 'treatment', 'control', 'mean', 'sd', 'se',
    'n', 'obs', 'coefficient', 'coef', 'p-value', 'panel', 'column',
    'specification', 'model', 'dependent', 'independent', 'baseline',
]

# Continuation indicators
CONTINUATION_PATTERNS = [
    re.compile(r'\bcont\.?\b', re.IGNORECASE),
    re.compile(r'\bcontinued\b', re.IGNORECASE),
    re.compile(r'—\s*continued', re.IGNORECASE),
    re.compile(r'–\s*continued', re.IGNORECASE),
]


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class ArtifactResult:
    """Result of artifact detection."""
    is_artifact: bool
    artifact_type: str = ""  # EMPTY, FIGURE, DIAGRAM, TEXT_FRAGMENT, ORPHAN_HEADER
    confidence: float = 0.0
    reason: str = ""


@dataclass
class MergeCandidate:
    """Candidate for table merging."""
    index1: int
    index2: int
    table_number: str
    confidence: float
    reason: str


@dataclass 
class PostProcessingResult:
    """Result of post-processing a document."""
    clean_tables: list
    artifacts: list
    merged_tables: list
    grafted_headers: list
    stats: dict


# =============================================================================
# MAIN POST-PROCESSOR CLASS
# =============================================================================

class MinerUPostProcessor:
    """
    Post-process MinerU parsed tables to remove artifacts and fix issues.
    
    Usage:
        processor = MinerUPostProcessor(doc)
        result = processor.process()
        clean_tables = result.clean_tables
    """
    
    def __init__(
        self, 
        doc: dict,
        md_content: str = "",  # Full markdown for LOT cross-reference
        min_table_rows: int = 2,
        enable_llm_verify: bool = False,
        enable_lot_crossref: bool = True,  # List of Tables caption repair
        verbose: bool = True,
    ):
        self.doc = doc
        self.tables_raw = doc.get('tables', [])
        self.content = doc.get('content', '')
        self.md_content = md_content  # For List of Tables parsing
        self.min_table_rows = min_table_rows
        self.enable_llm_verify = enable_llm_verify
        self.enable_lot_crossref = enable_lot_crossref
        self.verbose = verbose
        
        # Results
        self.clean_tables = []
        self.artifacts = []
        self.merged_tables = []
        self.grafted_headers = []
        self.lot_repairs = []  # List of Tables caption repairs
        
    def process(self) -> PostProcessingResult:
        """Execute full post-processing pipeline."""
        self._log("=" * 70)
        self._log("MINERU POST-PROCESSOR")
        self._log("=" * 70)
        self._log(f"Input: {len(self.tables_raw)} tables")
        
        # Create working copy with indices
        tables = []
        for i, t in enumerate(self.tables_raw):
            t_copy = t.copy()
            t_copy['_original_index'] = i
            tables.append(t_copy)
        
        # Step 0.1: Empty filter
        tables = self._filter_empty(tables)
        
        # Step 0.2: Figure detection
        tables = self._filter_figures(tables)
        
        # Step 0.3: Diagram detection
        tables = self._filter_diagrams(tables)
        
        # Step 0.4: Text fragment detection
        tables = self._filter_text_fragments(tables)
        
        # Step 0.5: Split table merging
        tables = self._merge_split_tables(tables)
        
        # Step 0.6: Header grafting
        tables = self._graft_orphan_headers(tables)
        
        # Step 0.7: LLM verification (optional)
        if self.enable_llm_verify:
            tables = self._llm_verify_ambiguous(tables)
        
        # Step 0.8: List of Tables cross-reference (optional)
        if self.enable_lot_crossref and self.md_content:
            tables = self._apply_lot_crossref(tables)
        
        self.clean_tables = tables
        
        # Summary
        self._log("-" * 70)
        self._log(f"Output: {len(self.clean_tables)} clean tables")
        self._log(f"Artifacts removed: {len(self.artifacts)}")
        self._log(f"Tables merged: {len(self.merged_tables)}")
        self._log(f"Headers grafted: {len(self.grafted_headers)}")
        if self.lot_repairs:
            self._log(f"Captions repaired (LOT): {len(self.lot_repairs)}")
        
        return PostProcessingResult(
            clean_tables=self.clean_tables,
            artifacts=self.artifacts,
            merged_tables=self.merged_tables,
            grafted_headers=self.grafted_headers,
            stats={
                'input_count': len(self.tables_raw),
                'output_count': len(self.clean_tables),
                'artifacts_removed': len(self.artifacts),
                'tables_merged': len(self.merged_tables),
                'headers_grafted': len(self.grafted_headers),
                'lot_repairs': len(self.lot_repairs),
            }
        )
    
    # =========================================================================
    # STEP 0.1: EMPTY FILTER
    # =========================================================================
    
    def _filter_empty(self, tables: list) -> list:
        """Remove tables with no body content."""
        self._log("\n[0.1] Filtering empty tables...")
        
        clean = []
        for t in tables:
            result = self._is_empty_artifact(t)
            if result.is_artifact:
                self._add_artifact(t, result)
            else:
                clean.append(t)
        
        removed = len(tables) - len(clean)
        self._log(f"  Removed {removed} empty tables")
        return clean
    
    def _is_empty_artifact(self, table: dict) -> ArtifactResult:
        """Check if table has no meaningful content."""
        body = table.get('table_body', '')
        
        if not body or body.strip() == '':
            return ArtifactResult(True, 'EMPTY', 1.0, 'No body content')
        
        if body.strip() == '<table></table>':
            return ArtifactResult(True, 'EMPTY', 1.0, 'Empty table tags')
        
        # Check for minimal content
        soup = BeautifulSoup(body, 'html.parser')
        text = soup.get_text(strip=True)
        
        if len(text) < 10:
            return ArtifactResult(True, 'EMPTY', 0.9, f'Only {len(text)} chars of text')
        
        return ArtifactResult(False)
    
    # =========================================================================
    # STEP 0.2: FIGURE DETECTION
    # =========================================================================
    
    def _filter_figures(self, tables: list) -> list:
        """Remove figures misclassified as tables."""
        self._log("\n[0.2] Detecting figures...")
        
        clean = []
        for t in tables:
            result = self._is_figure_artifact(t)
            if result.is_artifact:
                self._add_artifact(t, result)
            else:
                clean.append(t)
        
        removed = len(tables) - len(clean)
        self._log(f"  Removed {removed} figures")
        return clean
    
    def _is_figure_artifact(self, table: dict) -> ArtifactResult:
        """Check if table is actually a figure based on caption."""
        caption = self._get_caption(table)
        body = table.get('table_body', '')
        
        # Check caption for figure patterns
        for pattern in FIGURE_PATTERNS:
            if pattern.search(caption):
                # Make sure it's not "Figure in Table X" or similar
                if not re.search(r'table\s*\d', caption, re.IGNORECASE):
                    return ArtifactResult(
                        True, 'FIGURE', 0.95, 
                        f'Caption contains figure reference: {caption[:50]}'
                    )
        
        # Check body for figure indicators
        if body:
            soup = BeautifulSoup(body, 'html.parser')
            body_text = soup.get_text(strip=True)[:200]
            
            for pattern in FIGURE_PATTERNS:
                if pattern.search(body_text):
                    return ArtifactResult(
                        True, 'FIGURE', 0.85,
                        f'Body starts with figure reference: {body_text[:50]}'
                    )
        
        return ArtifactResult(False)
    
    # =========================================================================
    # STEP 0.3: DIAGRAM DETECTION
    # =========================================================================
    
    def _filter_diagrams(self, tables: list) -> list:
        """Remove single-row diagrams/legends."""
        self._log("\n[0.3] Detecting diagrams/legends...")
        
        clean = []
        for t in tables:
            result = self._is_diagram_artifact(t)
            if result.is_artifact:
                self._add_artifact(t, result)
            else:
                clean.append(t)
        
        removed = len(tables) - len(clean)
        self._log(f"  Removed {removed} diagrams/legends")
        return clean
    
    def _is_diagram_artifact(self, table: dict) -> ArtifactResult:
        """Check if table is a diagram or legend."""
        body = table.get('table_body', '')
        caption = self._get_caption(table)
        
        if not body:
            return ArtifactResult(False)
        
        rows = self._count_rows(body)
        
        # Only check single-row tables (unless caption says "Table X")
        if rows > 1:
            return ArtifactResult(False)
        
        # If caption explicitly says "Table N", keep it
        if re.search(r'Table\s*\d', caption, re.IGNORECASE):
            return ArtifactResult(False)
        
        # Check for diagram patterns
        soup = BeautifulSoup(body, 'html.parser')
        text = soup.get_text(strip=True)
        
        for pattern in DIAGRAM_PATTERNS:
            if pattern.search(text):
                return ArtifactResult(
                    True, 'DIAGRAM', 0.8,
                    f'Single-row diagram pattern: {text[:50]}'
                )
        
        # Check if it looks like a timeline (dates/periods)
        if re.search(r'\b(20\d{2}|baseline|midline|endline)\b.*\b(20\d{2}|baseline|midline|endline)\b', text, re.IGNORECASE):
            return ArtifactResult(
                True, 'DIAGRAM', 0.75,
                f'Timeline diagram: {text[:50]}'
            )
        
        return ArtifactResult(False)
    
    # =========================================================================
    # STEP 0.4: TEXT FRAGMENT DETECTION
    # =========================================================================
    
    def _filter_text_fragments(self, tables: list) -> list:
        """Remove text fragments misclassified as tables."""
        self._log("\n[0.4] Detecting text fragments...")
        
        clean = []
        for t in tables:
            result = self._is_text_fragment(t)
            if result.is_artifact:
                self._add_artifact(t, result)
            else:
                clean.append(t)
        
        removed = len(tables) - len(clean)
        self._log(f"  Removed {removed} text fragments")
        return clean
    
    def _is_text_fragment(self, table: dict) -> ArtifactResult:
        """Check if table is a text fragment."""
        body = table.get('table_body', '')
        caption = self._get_caption(table)
        
        rows = self._count_rows(body)
        
        # Only check small tables
        if rows > 3:
            return ArtifactResult(False)
        
        # Check caption for paragraph text patterns
        for pattern in TEXT_FRAGMENT_PATTERNS:
            if pattern.search(caption):
                return ArtifactResult(
                    True, 'TEXT_FRAGMENT', 0.7,
                    f'Caption contains paragraph text: {caption[:60]}'
                )
        
        # Check if body looks like paragraph text
        if body:
            soup = BeautifulSoup(body, 'html.parser')
            text = soup.get_text(strip=True)
            
            # Long text with few cells = probably paragraph
            cells = len(soup.find_all(['td', 'th']))
            if len(text) > 200 and cells < 5:
                return ArtifactResult(
                    True, 'TEXT_FRAGMENT', 0.6,
                    f'Long text ({len(text)} chars) with few cells ({cells})'
                )
        
        return ArtifactResult(False)
    
    # =========================================================================
    # STEP 0.5: SPLIT TABLE MERGING
    # =========================================================================
    
    def _merge_split_tables(self, tables: list) -> list:
        """Merge tables that were split across pages."""
        self._log("\n[0.5] Merging split tables...")
        
        # Find merge candidates
        candidates = self._find_merge_candidates(tables)
        
        if not candidates:
            self._log("  No split tables found")
            return tables
        
        self._log(f"  Found {len(candidates)} merge candidates")
        
        # Track which tables have been merged
        merged_indices = set()
        result_tables = []
        
        # Process merges
        for candidate in candidates:
            if candidate.index1 in merged_indices or candidate.index2 in merged_indices:
                continue
            
            t1 = tables[candidate.index1]
            t2 = tables[candidate.index2]
            
            merged = self._merge_two_tables(t1, t2)
            merged['_merged_from'] = [t1.get('_original_index'), t2.get('_original_index')]
            
            self.merged_tables.append({
                'table_number': candidate.table_number,
                'indices': [candidate.index1, candidate.index2],
                'reason': candidate.reason,
            })
            
            # Replace t1 with merged, mark t2 as merged
            tables[candidate.index1] = merged
            merged_indices.add(candidate.index2)
            
            self._log(f"  Merged: {candidate.table_number} ({candidate.reason})")
        
        # Filter out merged tables
        result_tables = [t for i, t in enumerate(tables) if i not in merged_indices]
        
        self._log(f"  Merged {len(self.merged_tables)} table pairs")
        return result_tables
    
    def _find_merge_candidates(self, tables: list) -> list[MergeCandidate]:
        """Find tables that should be merged."""
        candidates = []
        
        # Group by table number
        by_number = defaultdict(list)
        for i, t in enumerate(tables):
            num = self._extract_table_number(t)
            if num:
                by_number[num.lower()].append((i, t))
        
        for num, entries in by_number.items():
            if len(entries) < 2:
                continue
            
            # Sort by page
            entries.sort(key=lambda x: x[1].get('page_idx', 0))
            
            for j in range(len(entries) - 1):
                idx1, t1 = entries[j]
                idx2, t2 = entries[j + 1]
                
                # Check if likely split
                result = self._should_merge(t1, t2)
                if result[0]:
                    candidates.append(MergeCandidate(
                        index1=idx1,
                        index2=idx2,
                        table_number=num,
                        confidence=result[1],
                        reason=result[2],
                    ))
        
        return candidates
    
    def _should_merge(self, t1: dict, t2: dict) -> tuple[bool, float, str]:
        """Determine if two tables should be merged."""
        page1 = t1.get('page_idx', 0)
        page2 = t2.get('page_idx', 0)
        
        # Must be on same or consecutive pages
        if abs(page2 - page1) > 1:
            return (False, 0, '')
        
        caption2 = self._get_caption(t2).lower()
        
        # Check for continuation indicators in caption
        for pattern in CONTINUATION_PATTERNS:
            if pattern.search(caption2):
                return (True, 0.95, 'Caption has continuation indicator')
        
        # Check if second table has no caption (orphan continuation)
        if not caption2 or caption2 == '[no caption]':
            # Check if columns match
            cols1 = self._count_cols(t1.get('table_body', ''))
            cols2 = self._count_cols(t2.get('table_body', ''))
            if cols1 > 0 and cols2 > 0 and abs(cols1 - cols2) <= 1:
                return (True, 0.7, 'No caption, similar column count')
        
        return (False, 0, '')
    
    def _merge_two_tables(self, t1: dict, t2: dict) -> dict:
        """Merge two table fragments."""
        body1 = t1.get('table_body', '')
        body2 = t2.get('table_body', '')
        
        soup1 = BeautifulSoup(body1, 'html.parser')
        soup2 = BeautifulSoup(body2, 'html.parser')
        
        rows1 = soup1.find_all('tr')
        rows2 = soup2.find_all('tr')
        
        # Check if t2 has duplicate header
        if rows1 and rows2:
            header1_text = rows1[0].get_text(strip=True)
            header2_text = rows2[0].get_text(strip=True)
            
            if self._similar_text(header1_text, header2_text, 0.8):
                rows2 = rows2[1:]  # Skip duplicate header
        
        # Append rows to t1
        table_tag = soup1.find('table')
        if table_tag:
            for row in rows2:
                table_tag.append(row)
        
        merged = t1.copy()
        merged['table_body'] = str(soup1)
        
        return merged
    
    # =========================================================================
    # STEP 0.6: HEADER GRAFTING
    # =========================================================================
    
    def _graft_orphan_headers(self, tables: list) -> list:
        """Match orphan headers to body tables."""
        self._log("\n[0.6] Grafting orphan headers...")
        
        orphan_headers = []
        body_tables = []
        
        for i, t in enumerate(tables):
            rows = self._count_rows(t.get('table_body', ''))
            caption = self._get_caption(t)
            
            # Orphan header: 1 row, no caption, looks like header
            if rows == 1 and (not caption or caption == '[no caption]'):
                text = self._get_table_text(t)
                if self._looks_like_header(text):
                    orphan_headers.append((i, t))
                else:
                    body_tables.append((i, t))
            else:
                body_tables.append((i, t))
        
        if not orphan_headers:
            self._log("  No orphan headers found")
            return tables
        
        self._log(f"  Found {len(orphan_headers)} potential orphan headers")
        
        # Track grafted headers
        grafted_indices = set()
        
        for header_idx, header in orphan_headers:
            for body_idx, body in body_tables:
                if self._can_graft(header, body):
                    # Graft header onto body
                    tables[body_idx] = self._prepend_header(body, header)
                    grafted_indices.add(header_idx)
                    
                    self.grafted_headers.append({
                        'header_index': header_idx,
                        'body_index': body_idx,
                    })
                    
                    self._log(f"  Grafted header {header_idx} to body {body_idx}")
                    break
        
        # Remove grafted headers
        result = [t for i, t in enumerate(tables) if i not in grafted_indices]
        
        self._log(f"  Grafted {len(self.grafted_headers)} headers")
        return result
    
    def _looks_like_header(self, text: str) -> bool:
        """Check if text looks like a table header."""
        text_lower = text.lower()
        matches = sum(1 for word in HEADER_WORDS if word in text_lower)
        return matches >= 2
    
    def _can_graft(self, header: dict, body: dict) -> bool:
        """Check if header can be grafted to body."""
        page_h = header.get('page_idx', 0)
        page_b = body.get('page_idx', 0)
        
        # Header must be on same page or page before
        if page_h > page_b or page_b - page_h > 1:
            return False
        
        # Column count should match
        cols_h = self._count_cols(header.get('table_body', ''))
        cols_b = self._count_cols(body.get('table_body', ''))
        
        return cols_h > 0 and cols_b > 0 and abs(cols_h - cols_b) <= 1
    
    def _prepend_header(self, body: dict, header: dict) -> dict:
        """Prepend header row to body table."""
        body_html = body.get('table_body', '')
        header_html = header.get('table_body', '')
        
        soup_body = BeautifulSoup(body_html, 'html.parser')
        soup_header = BeautifulSoup(header_html, 'html.parser')
        
        header_rows = soup_header.find_all('tr')
        table_tag = soup_body.find('table')
        
        if table_tag and header_rows:
            # Insert header at beginning
            first_row = table_tag.find('tr')
            for row in reversed(header_rows):
                if first_row:
                    first_row.insert_before(row)
                else:
                    table_tag.insert(0, row)
        
        result = body.copy()
        result['table_body'] = str(soup_body)
        result['_header_grafted'] = True
        
        return result
    
    # =========================================================================
    # STEP 0.7: LLM VERIFICATION (Optional)
    # =========================================================================
    
    def _llm_verify_ambiguous(self, tables: list) -> list:
        """Use LLM to verify ambiguous tables."""
        self._log("\n[0.7] LLM verification (skipped - not enabled)")
        # TODO: Implement LLM verification for edge cases
        return tables
    
    # =========================================================================
    # HELPER METHODS
    # =========================================================================
    
    def _get_caption(self, table: dict) -> str:
        """Extract caption from table."""
        caption_list = table.get('table_caption', [])
        if caption_list:
            return ' '.join(caption_list).strip()
        return '[no caption]'
    
    def _extract_table_number(self, table: dict) -> str:
        """Extract table number (e.g., 'Table 4', 'Table A.1')."""
        caption = self._get_caption(table)
        
        for pattern in TABLE_NUMBER_PATTERNS:
            match = pattern.search(caption)
            if match:
                return f"Table {match.group(2)}"
        
        # Also check body
        body = table.get('table_body', '')
        if body:
            soup = BeautifulSoup(body, 'html.parser')
            text = soup.get_text(strip=True)[:100]
            for pattern in TABLE_NUMBER_PATTERNS:
                match = pattern.search(text)
                if match:
                    return f"Table {match.group(2)}"
        
        return ''
    
    def _count_rows(self, body: str) -> int:
        """Count rows in table HTML."""
        if not body:
            return 0
        soup = BeautifulSoup(body, 'html.parser')
        return len(soup.find_all('tr'))
    
    def _count_cols(self, body: str) -> int:
        """Count columns in table HTML."""
        if not body:
            return 0
        soup = BeautifulSoup(body, 'html.parser')
        rows = soup.find_all('tr')
        if not rows:
            return 0
        return max(len(row.find_all(['td', 'th'])) for row in rows)
    
    def _get_table_text(self, table: dict) -> str:
        """Get plain text content of table."""
        body = table.get('table_body', '')
        if not body:
            return ''
        soup = BeautifulSoup(body, 'html.parser')
        return soup.get_text(separator=' ', strip=True)
    
    def _similar_text(self, text1: str, text2: str, threshold: float) -> bool:
        """Check if two texts are similar."""
        if not text1 or not text2:
            return False
        
        # Simple word overlap similarity
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        
        if not words1 or not words2:
            return False
        
        overlap = len(words1 & words2)
        similarity = overlap / max(len(words1), len(words2))
        
        return similarity >= threshold
    
    # =========================================================================
    # STEP 0.8: LIST OF TABLES CROSS-REFERENCE
    # =========================================================================
    
    def _apply_lot_crossref(self, tables: list) -> list:
        """
        Use List of Tables to repair missing/corrupted captions.
        
        Parses the "List of Tables" section from the document front matter
        and uses it to validate and repair captions.
        """
        self._log("\n[0.8] List of Tables cross-reference...")
        
        try:
            from extraction_pipeline.list_of_tables_parser import (
                parse_list_of_tables,
                match_tables_to_list,
                repair_table_captions,
            )
        except ImportError:
            self._log("  [SKIP] list_of_tables_parser not available")
            return tables
        
        # Parse List of Tables from markdown
        lot = parse_list_of_tables(self.md_content)
        
        if not lot.found_section:
            self._log("  No 'List of Tables' section found")
            return tables
        
        self._log(f"  Found {lot.expected_table_count} tables in List of Tables")
        
        # Match detected tables to LOT entries
        match_result = match_tables_to_list(tables, lot)
        
        self._log(f"  Matched: {len(match_result.matched)} tables")
        self._log(f"  Missing: {len(match_result.missing_tables)} tables")
        self._log(f"  Captions to repair: {len(match_result.caption_repairs)}")
        
        # Apply caption repairs
        if match_result.caption_repairs:
            tables = repair_table_captions(tables, match_result)
            self.lot_repairs = match_result.caption_repairs
            
            for repair in match_result.caption_repairs[:5]:  # Log first 5
                self._log(f"    Page {repair['page']}: '{repair['current_caption'][:30]}...' → '{repair['expected_caption'][:40]}...'")
        
        return tables
    
    def _add_artifact(self, table: dict, result: ArtifactResult):
        """Add artifact to tracking list."""
        self.artifacts.append({
            'original_index': table.get('_original_index', -1),
            'page': table.get('page_idx', -1),
            'type': result.artifact_type,
            'confidence': result.confidence,
            'reason': result.reason,
            'caption': self._get_caption(table)[:60],
        })
    
    def _log(self, msg: str):
        """Print log message if verbose."""
        if self.verbose:
            print(msg)


# =============================================================================
# CONVENIENCE FUNCTION
# =============================================================================

def postprocess_mineru_doc(
    doc: dict, 
    md_content: str = "",
    enable_lot_crossref: bool = True,
    verbose: bool = True
) -> PostProcessingResult:
    """
    Convenience function to post-process a MinerU document.
    
    Args:
        doc: MinerU JSON document with 'tables' and 'content' fields
        md_content: Full markdown content for List of Tables parsing
        enable_lot_crossref: Use List of Tables for caption repair
        verbose: Print progress messages
    
    Returns:
        PostProcessingResult with clean_tables and stats
    """
    processor = MinerUPostProcessor(
        doc, 
        md_content=md_content,
        enable_lot_crossref=enable_lot_crossref,
        verbose=verbose
    )
    return processor.process()


# =============================================================================
# TEST
# =============================================================================

if __name__ == '__main__':
    import boto3
    from dotenv import load_dotenv
    
    load_dotenv()
    
    # Initialize R2 client
    account_id = os.environ.get('CLOUDFLARE_ACCOUNT_ID')
    r2 = boto3.client(
        's3',
        endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ.get('R2_ACCESS_KEY_ID'),
        aws_secret_access_key=os.environ.get('R2_SECRET_ACCESS_KEY'),
    )
    BUCKET = 'devchat-pdfs'
    
    # Test with Bossuroy paper (has figure-as-table issue)
    key = 'rags/0816e8d3-ab23-417c-bf3f-e45531411c73/outputs/json/8d23199222c8_PDFs_of_included_programs_121058356.json'
    
    print("Loading document...")
    response = r2.get_object(Bucket=BUCKET, Key=key)
    doc = json.loads(response['Body'].read().decode('utf-8'))
    
    print(f"Raw tables: {len(doc.get('tables', []))}")
    
    # Run post-processor
    result = postprocess_mineru_doc(doc, verbose=True)
    
    print("\n" + "=" * 70)
    print("POST-PROCESSING COMPLETE")
    print("=" * 70)
    print(f"Clean tables: {result.stats['output_count']}")
    print(f"Artifacts removed: {result.stats['artifacts_removed']}")
    
    print("\nArtifacts detected:")
    for artifact in result.artifacts:
        print(f"  [{artifact['type']}] Page {artifact['page']}: {artifact['caption']}")
