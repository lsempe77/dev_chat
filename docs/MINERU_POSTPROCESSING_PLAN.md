# MinerU Parsing & Post-Processing Pipeline: Comprehensive Plan

## Executive Summary

Analysis of 20 processed PDFs (472 tables) reveals significant parsing artifacts:

| Artifact Type | Count | % of Tables | Impact |
|--------------|-------|-------------|--------|
| Empty body | 54 | 11.4% | **HIGH** - No data to extract |
| Single row | 11 | 2.3% | **MEDIUM** - Often diagrams/headers |
| Figure as table | 4 | 0.8% | **MEDIUM** - Wrong element type |
| Split tables | 2 | 0.4% | **LOW** - Need merging |

**Total artifacts: ~15% of all "tables" are not actual data tables.**

---

## Key MinerU Configuration Discoveries (Feb 2026)

From official MinerU documentation (v2.7.x):

### Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `MINERU_TABLE_MERGE_ENABLE` | `true` | **Built-in split table merging** - handles cross-page tables |
| `MINERU_TABLE_ENABLE` | `true` | Enable/disable table parsing |
| `MINERU_HYBRID_FORCE_PIPELINE_ENABLE` | `false` | Force small models for text (reduces VLM hallucinations) |

### Backend Options

| Backend | Accuracy | Speed | GPU Req |
|---------|----------|-------|---------|
| `pipeline` | Good | Fast | Moderate |
| `hybrid-auto-engine` | **High** | Slow | High (VLM) |
| `vlm-auto-engine` | Highest | Slowest | High (VLM) |

### Model Output Category IDs (model.json)

| ID | Type | Notes |
|----|------|-------|
| 3 | Figure | Should NOT be extracted as table |
| 5 | Table | Valid table body |
| 6 | Table caption | Caption text |

**Recommendation:** Start with `pipeline` + Level 1 filtering. Upgrade to `hybrid-auto-engine` if accuracy insufficient.

---

## Two-Level Improvement Strategy

### Level 1: MinerU Extraction (During GPU Processing)
Fix issues that can be detected during extraction to avoid storing bad data.
**Status: ✅ IMPLEMENTED** in `extraction.py`

### Level 2: Post-Processing (Before Classification)
Fix issues that require semantic understanding or cross-table context.
**Status: ✅ IMPLEMENTED** in `mineru_postprocessor.py` (Feb 2, 2026)

| Issue | Level 1 (MinerU) | Level 2 (Post-Process) |
|-------|------------------|------------------------|
| Empty tables | ✅ Implemented | ✅ Backup filter |
| Figure captions | ✅ Implemented | ✅ Regex detection |
| Single-row diagrams | ✅ Implemented | ✅ Pattern detection |
| Split tables | ✅ `MINERU_TABLE_MERGE_ENABLE=true` | ✅ Cross-page merge |
| Text fragments | ❌ | ✅ NLP detection |
| Orphan headers | ❌ | ✅ Header-body matching |
| **Caption repair** | ❌ | ✅ **Step 0.8: List of Tables** |
| **Missing detection** | ❌ | ⚠️ **Flagged only (no extraction)** |

### Level 2 Implementation Results (Feb 2, 2026)

**Batch test on 5 PDFs:**
- Input tables: 89
- Artifacts removed: 13 (14.6%)
- Figure misclassifications caught: 2
- Empty tables filtered: 11

**Full test on 122182713 with List of Tables (Feb 2, 2026):**
- Input: 52 raw tables
- Output: 45 clean tables
- Artifacts removed: 5 (empty, figures)
- Tables merged: 2 (split across pages)
- **Captions repaired: 9** (using List of Tables cross-reference)
  - Including corrupted caption: "nearly equal increases in livestock..." → "Table 14: Household income"

---

## Level 3: List of Tables Cross-Reference (✅ IMPLEMENTED)

**Status: ✅ IMPLEMENTED** - Feb 2, 2026

### Implementation

Files:
- `extraction_pipeline/list_of_tables_parser.py` - Standalone parser
- `extraction_pipeline/mineru_postprocessor.py` - Step 0.8 integration

### The Problem

Many academic papers include a **"List of Tables"** section (typically in front matter). Example from 122182713:
```
Table 1: Treatment and control group assignment, by barangay......... ...17
Table 2: Number of households from baseline survey in endline sample . ...19
Table 3: Status of unreached households... ....19
...
Table 39: Log of monthly consumption and income and productive asset values...60
```

This list provides **ground truth** for:
1. Expected table numbers (1-39)
2. Correct captions
3. Page locations

### Issues This Would Fix

| Issue | Example | Solution |
|-------|---------|----------|
| **Wrong caption extracted** | "nearly equal increases in livestock expenses..." (should be Table 14) | Match page to List of Tables entry |
| **Missing table number** | `[No caption]` entries | Fill from List of Tables |
| **Figure misclassified as table** | "Figure 2: Treatment and control" | Cross-check: if in List of Tables → keep, else → remove |
| **Missing tables** | Table 35 not detected | Alert user + targeted re-extraction |
| **Duplicate detection** | Same table detected twice | Use List of Tables as deduplication reference |

### Implementation Plan

#### Step 1: Extract List of Tables from Markdown

```python
import re

def extract_list_of_tables(md_content: str) -> list[dict]:
    """
    Extract List of Tables from markdown.
    
    Returns:
        List of {"table_num": int, "caption": str, "page": int}
    """
    # Find "List of Tables" section
    lot_match = re.search(
        r'(List of Tables|LIST OF TABLES)(.*?)(List of Figures|LIST OF FIGURES|#|\n\n\n)',
        md_content, 
        re.IGNORECASE | re.DOTALL
    )
    if not lot_match:
        return []
    
    lot_text = lot_match.group(2)
    
    # Parse entries like "Table 14: Household income per month...35"
    pattern = r'Table\s+(\d+)[:\.]?\s*([^\.]+)\.{2,}\s*(\d+)'
    entries = []
    for match in re.finditer(pattern, lot_text):
        entries.append({
            "table_num": int(match.group(1)),
            "caption": match.group(2).strip(),
            "page": int(match.group(3))
        })
    
    return entries
```

#### Step 2: Match Detected Tables to Ground Truth

```python
def match_tables_to_lot(detected_tables: list, lot_entries: list) -> dict:
    """
    Match detected tables to List of Tables entries.
    
    Returns:
        {
            "matched": [(detected_idx, lot_entry), ...],
            "unmatched_detected": [detected_idx, ...],  # May be artifacts
            "missing_from_lot": [lot_entry, ...],  # Need re-extraction
        }
    """
    result = {"matched": [], "unmatched_detected": [], "missing_from_lot": []}
    
    lot_by_page = {e["page"]: e for e in lot_entries}
    matched_lot = set()
    
    for i, table in enumerate(detected_tables):
        page = table.get("page_idx", -1) + 1  # Convert 0-indexed to 1-indexed
        
        # Try to match by page
        if page in lot_by_page:
            result["matched"].append((i, lot_by_page[page]))
            matched_lot.add(page)
        else:
            result["unmatched_detected"].append(i)
    
    # Find missing tables
    for entry in lot_entries:
        if entry["page"] not in matched_lot:
            result["missing_from_lot"].append(entry)
    
    return result
```

#### Step 3: Repair Captions

```python
def repair_captions(tables: list, lot_entries: list) -> list:
    """
    Repair table captions using List of Tables as ground truth.
    """
    lot_by_page = {e["page"]: e for e in lot_entries}
    
    repaired = []
    for table in tables:
        page = table.get("page_idx", -1) + 1
        
        if page in lot_by_page:
            lot_entry = lot_by_page[page]
            current_caption = (table.get("table_caption", []) or [""])[0]
            expected_caption = f"Table {lot_entry['table_num']}: {lot_entry['caption']}"
            
            # If current caption looks wrong, repair it
            if not current_caption.startswith("Table"):
                table["table_caption"] = [expected_caption]
                table["_caption_repaired"] = True
                table["_original_caption"] = current_caption
        
        repaired.append(table)
    
    return repaired
```

### Expected Impact

Based on 122182713 analysis:
- **52 detected "tables"**
- **39 actual tables** (from List of Tables)
- **~13 artifacts** (figures, duplicates, text fragments)

With Level 3:
- ✅ Remove 13 artifacts (25% reduction in noise)
- ✅ Fix corrupted captions (e.g., "nearly equal increases...")
- ✅ Fill `[No caption]` entries
- ✅ Detect 0 missing tables (if any)


**Files:**
- `extraction_pipeline/mineru_postprocessor.py` - Main module
- Integrated into `table_classifier_v3.py` as Step -1

---

## Level 1: MinerU Extraction Improvements (✅ IMPLEMENTED)

### Implementation Status

**File:** `infrastructure/modal_lib/extraction.py`

All Level 1 improvements have been implemented:

1. **Environment variables set:**
   ```python
   os.environ.setdefault("MINERU_TABLE_MERGE_ENABLE", "true")
   os.environ.setdefault("MINERU_TABLE_ENABLE", "true")
   ```

2. **Empty table filter:** Skips tables with no body content

3. **Figure detection:** Uses regex `\b(figure|fig\.?)\s*\d` on captions

4. **Single-row filter:** Skips tables with <2 rows (unless caption says "Table N")

5. **Extraction metadata:** Each table now includes:
   ```python
   item["_extraction_meta"] = {
       "row_count": N,
       "col_count": M,
       "text_length": L,
       "is_figure_caption": bool,
       "extraction_timestamp": "ISO datetime",
   }
   ```

6. **Debug output:** `save_debug_output=True` saves raw model.json

### New Return Fields

```python
{
    "tables": [...],           # Filtered valid tables
    "figures_detected": [...], # Tables that were actually figures
    "artifacts_filtered": [...], # Metadata about filtered items
    "extraction_config": {
        "table_merge_enabled": "true",
        "min_table_rows": 2,
        "backend": "pipeline",
    },
}
```

---

## Level 1 Code Reference (OLD - FOR REFERENCE ONLY)

# Improved code:
tables = []
if isinstance(content_list, list):
    for item in content_list:
        if isinstance(item, dict) and item.get("type") == "table":
            # Filter out empty tables at extraction time
            body = item.get("table_body", "")
            if body and body.strip() and body != "<table></table>":
                tables.append(item)
            else:
                print(f"  Filtered empty table on page {item.get('page_idx', '?')}")
```

### 1.2 Filter Figure-Tables During Extraction

```python
import re

FIGURE_PATTERN = re.compile(r'\b(figure|fig\.?)\s*\d', re.IGNORECASE)

def is_likely_figure(item: dict) -> bool:
    """Check if a 'table' is actually a figure based on caption."""
    caption_list = item.get("table_caption", [])
    caption = caption_list[0] if caption_list else ""
    return bool(FIGURE_PATTERN.search(caption))

# In extraction:
tables = []
figures = []  # New: track figures separately
if isinstance(content_list, list):
    for item in content_list:
        if isinstance(item, dict) and item.get("type") == "table":
            body = item.get("table_body", "")
            if not body or not body.strip():
                continue  # Skip empty
            
            if is_likely_figure(item):
                figures.append(item)  # Save as figure, not table
                print(f"  Detected figure: {caption[:50]}")
            else:
                tables.append(item)
```

### 1.3 Add Minimum Row Threshold

```python
from bs4 import BeautifulSoup

MIN_TABLE_ROWS = 2  # Tables with <2 rows are likely artifacts

def count_table_rows(body: str) -> int:
    """Count rows in table HTML."""
    if not body:
        return 0
    soup = BeautifulSoup(body, 'html.parser')
    return len(soup.find_all('tr'))

# In extraction:
for item in content_list:
    if isinstance(item, dict) and item.get("type") == "table":
        body = item.get("table_body", "")
        
        # Skip empty
        if not body or not body.strip():
            continue
        
        # Skip figures
        if is_likely_figure(item):
            figures.append(item)
            continue
        
        # Skip single-row artifacts (but keep if has meaningful caption)
        rows = count_table_rows(body)
        caption = get_caption(item)
        if rows < MIN_TABLE_ROWS and not re.match(r'Table\s*\d', caption):
            print(f"  Filtered {rows}-row artifact: {caption[:40]}")
            continue
        
        tables.append(item)
```

### 1.4 Store Metadata for Post-Processing

Add extraction metadata to help post-processing:

```python
# Enrich each table with extraction metadata
for item in tables:
    body = item.get("table_body", "")
    soup = BeautifulSoup(body, 'html.parser') if body else None
    
    item["_extraction_meta"] = {
        "row_count": len(soup.find_all('tr')) if soup else 0,
        "col_count": max(len(row.find_all(['td', 'th'])) for row in soup.find_all('tr')) if soup else 0,
        "text_length": len(soup.get_text(strip=True)) if soup else 0,
        "has_header_row": has_header_structure(soup),
        "extraction_timestamp": datetime.now().isoformat(),
    }
```

---

## Level 2: Post-Processing (Existing Plan)

This section covers what was previously Phase 1-4:

| Artifact Type | Count | % of Tables | Impact |
|--------------|-------|-------------|--------|
| Empty body | 54 | 11.4% | **HIGH** - No data to extract |
| Single row | 11 | 2.3% | **MEDIUM** - Often diagrams/headers |
| Figure as table | 4 | 0.8% | **MEDIUM** - Wrong element type |
| Split tables | 2 | 0.4% | **LOW** - Need merging |

**Total artifacts: ~15% of all "tables" are not actual data tables.**

---

## Phase 1: Rule-Based Pre-Filtering (Immediate)

### 1.1 Empty Body Filter
**Pattern:** `table_body == '' or table_body is None`
**Action:** Mark as `ARTIFACT_EMPTY`
**Confidence:** 100% accurate

```python
def is_empty_artifact(table: dict) -> bool:
    body = table.get('table_body', '')
    return not body or body.strip() == '' or body == '<table></table>'
```

### 1.2 Figure Detection
**Pattern:** Caption contains "Figure", "Fig.", "Fig " (case-insensitive)
**Action:** Mark as `ARTIFACT_FIGURE`
**Confidence:** 95% accurate

```python
FIGURE_PATTERNS = [
    re.compile(r'\bfigure\s*\d', re.IGNORECASE),
    re.compile(r'\bfig\.?\s*\d', re.IGNORECASE),
]

def is_figure_artifact(table: dict) -> bool:
    caption = get_caption(table)
    return any(p.search(caption) for p in FIGURE_PATTERNS)
```

### 1.3 Single-Row Diagram Detection
**Pattern:** 
- Only 1 row
- Text looks like legend/timeline (contains ":", multiple short items)
- No numeric data

**Action:** Mark as `ARTIFACT_DIAGRAM`
**Confidence:** 80% accurate

```python
def is_diagram_artifact(table: dict) -> bool:
    rows = count_rows(table)
    if rows != 1:
        return False
    
    text = get_table_text(table)
    # Timeline pattern: "Baseline Aug 2022 | Midline Dec 2023"
    # Legend pattern: "-97=Refuse -98=Don't know"
    if re.search(r'(\w+\s*(=|:)\s*\w+.*){2,}', text):
        return True
    return False
```

### 1.4 Text Fragment Detection
**Pattern:**
- Caption contains paragraph text (sentence with verb)
- ≤2 rows
- Caption matches pattern like "Table X: Y). Some text about households..."

**Action:** Mark as `ARTIFACT_TEXT_FRAGMENT`
**Confidence:** 70% accurate

```python
TEXT_FRAGMENT_PATTERNS = [
    re.compile(r'Table\s*\d+[:\)]\s*\d+\)', re.IGNORECASE),  # "Table 3: 3). In Amhara..."
    re.compile(r'\.\s*\d+\s+percent', re.IGNORECASE),         # Embedded statistics
    re.compile(r'\b(households|women|children|percent)\b.*\b(were|had|showed)\b', re.IGNORECASE),
]

def is_text_fragment(table: dict) -> bool:
    caption = get_caption(table)
    rows = count_rows(table)
    
    if rows > 2 or len(caption) < 50:
        return False
    
    return any(p.search(caption) for p in TEXT_FRAGMENT_PATTERNS)
```

---

## Phase 2: Split Table Merging (Rule-Based)

### 2.1 Detection Algorithm
```python
def detect_split_tables(tables: list[dict]) -> list[tuple[int, int]]:
    """Find tables that should be merged."""
    
    # Group by table number
    by_number = defaultdict(list)
    for i, t in enumerate(tables):
        num = extract_table_number(t)
        if num:
            by_number[num].append((i, t))
    
    merge_pairs = []
    for num, entries in by_number.items():
        if len(entries) < 2:
            continue
        
        # Sort by page
        entries.sort(key=lambda x: x[1].get('page_idx', 0))
        
        for j in range(len(entries) - 1):
            idx1, t1 = entries[j]
            idx2, t2 = entries[j + 1]
            
            # Check if likely split
            if should_merge(t1, t2):
                merge_pairs.append((idx1, idx2))
    
    return merge_pairs


def should_merge(t1: dict, t2: dict) -> bool:
    """Determine if two table fragments should be merged."""
    
    page1 = t1.get('page_idx', 0)
    page2 = t2.get('page_idx', 0)
    
    # Must be on same or consecutive pages
    if abs(page2 - page1) > 1:
        return False
    
    # Check for "(cont.)" or "(continued)" in caption
    caption2 = get_caption(t2).lower()
    if 'cont' in caption2 or 'continued' in caption2:
        return True
    
    # Check if first table ends without conclusion
    # (e.g., last row is data, not a footer like "N" or "Observations")
    rows1 = get_table_rows(t1)
    if rows1:
        last_row = rows1[-1]
        # If last row looks like data (has numbers), likely continues
        if re.search(r'\d+\.\d+', last_row):
            return True
    
    return False
```

### 2.2 Merge Strategy
```python
def merge_tables(t1: dict, t2: dict) -> dict:
    """Merge two table fragments into one."""
    
    # Combine HTML bodies
    soup1 = BeautifulSoup(t1.get('table_body', ''), 'html.parser')
    soup2 = BeautifulSoup(t2.get('table_body', ''), 'html.parser')
    
    # Get all rows from both
    rows1 = soup1.find_all('tr')
    rows2 = soup2.find_all('tr')
    
    # Check if t2 has a header row that duplicates t1's header
    if rows1 and rows2:
        header1_text = rows1[0].get_text(strip=True)
        header2_text = rows2[0].get_text(strip=True)
        
        # If headers match, skip t2's header
        if similar_text(header1_text, header2_text, threshold=0.8):
            rows2 = rows2[1:]
    
    # Append t2's rows to t1
    table_tag = soup1.find('table')
    for row in rows2:
        table_tag.append(row)
    
    # Return merged table with t1's metadata
    merged = t1.copy()
    merged['table_body'] = str(soup1)
    merged['_merged_from'] = [t1.get('index'), t2.get('index')]
    
    return merged
```

---

## Phase 3: LLM-Assisted Artifact Detection (For Edge Cases)

For tables that pass rule-based filters but have ambiguous characteristics:

### 3.1 LLM Verification Prompt
```python
ARTIFACT_VERIFICATION_PROMPT = """
You are analyzing a table extracted from an academic PDF. Determine if this is an actual data table or an artifact.

TABLE CAPTION: {caption}
TABLE CONTENT (first 5 rows):
{body_preview}

QUESTION: Is this an actual data table that could contain research results, or is it one of these artifacts?
- FIGURE: A diagram/chart mistakenly extracted as a table
- LEGEND: A legend, key, or code list
- TEXT: A text fragment that isn't a table
- NAVIGATION: Table of contents, index, or page reference
- ACTUAL_TABLE: A real data table

Respond with JSON:
{{"type": "ACTUAL_TABLE" or "FIGURE" or "LEGEND" or "TEXT" or "NAVIGATION", "confidence": 0.0-1.0, "reason": "brief explanation"}}
"""
```

### 3.2 When to Use LLM
Only invoke LLM for tables that:
- Pass all rule-based filters
- Have ambiguous characteristics:
  - ≤3 rows but has caption
  - Caption mentions both table and figure
  - Single row but appears to have data

---

## Phase 4: Header-Body Matching (Advanced)

For tables where header is detected separately from body:

### 4.1 Problem Pattern
```
[Table index=3] No caption, 1 row: "Module | Respondent | Baseline | Midline"
[Table index=4] Caption "Table 2.2", 43 rows: actual data
```

### 4.2 Solution: Header Grafting
```python
def graft_orphan_headers(tables: list[dict]) -> list[dict]:
    """Match orphan headers (1-row tables) to their bodies."""
    
    orphan_headers = []
    body_tables = []
    
    for i, t in enumerate(tables):
        rows = count_rows(t)
        caption = get_caption(t)
        
        # Orphan header: 1 row, no caption, looks like header
        if rows == 1 and not caption:
            text = get_table_text(t)
            if looks_like_header(text):
                orphan_headers.append((i, t))
            else:
                body_tables.append((i, t))
        else:
            body_tables.append((i, t))
    
    # Try to match orphans to bodies
    for header_idx, header in orphan_headers:
        for body_idx, body in body_tables:
            if can_graft(header, body):
                body = prepend_header(body, header)
                # Mark header as merged
                tables[header_idx]['_merged_into'] = body_idx
                break
    
    # Filter out merged headers
    return [t for t in tables if '_merged_into' not in t]


def looks_like_header(text: str) -> bool:
    """Check if text looks like a table header."""
    # Headers typically have:
    # - Short segments separated by whitespace
    # - Common header words
    header_words = ['variable', 'outcome', 'treatment', 'control', 
                    'mean', 'sd', 'n', 'coefficient', 'se', 'p-value']
    text_lower = text.lower()
    return any(w in text_lower for w in header_words)


def can_graft(header: dict, body: dict) -> bool:
    """Check if header can be grafted to body."""
    # Same page or consecutive
    page_diff = abs(body.get('page_idx', 0) - header.get('page_idx', 0))
    if page_diff > 1:
        return False
    
    # Header comes before body
    if header.get('page_idx', 0) > body.get('page_idx', 0):
        return False
    
    # Column count should match
    header_cols = count_cols(header)
    body_cols = count_cols(body)
    return abs(header_cols - body_cols) <= 1
```

---

## Implementation Priority

### Priority 1: MinerU Extraction Fixes (Week 1)
**Impact: Eliminates ~12% artifacts at source**

1. Add empty table filter in `extraction.py`
2. Add figure detection in `extraction.py`  
3. Add extraction metadata
4. Deploy updated Modal function
5. **Decision: Re-process all PDFs or apply post-processing to existing?**

### Priority 2: Post-Processing Module (Week 1-2)
**Impact: Catches remaining ~3% artifacts**

1. Create `mineru_postprocessor.py`
2. Implement text fragment detection
3. Implement diagram detection
4. Integration with `table_classifier_v3.py`

### Priority 3: Split Table Merging (Week 2)
**Impact: Improves data completeness**

1. Detect split tables by table number
2. Implement merge logic
3. Handle header deduplication

### Priority 4: Header-Body Matching (Week 3)
**Impact: Fixes fragmented tables**

1. Detect orphan headers
2. Match to body tables
3. Graft headers

### Priority 5: LLM Edge Case Handler (Week 3-4)
**Impact: Catches edge cases**

1. Design verification prompt
2. Implement selective calling
3. Add caching

---

## Recommended Approach

### Option A: Fix MinerU + Re-Process (Recommended if <100 PDFs)
- Update `extraction.py` with filters
- Re-deploy Modal function
- Re-process all PDFs
- **Pros:** Clean data, simpler pipeline
- **Cons:** GPU cost, time

### Option B: Post-Processing Only (Recommended if >100 PDFs)
- Keep existing parsed data
- Apply comprehensive post-processing
- **Pros:** No re-processing cost
- **Cons:** More complex pipeline

### Option C: Hybrid (Recommended)
- Update MinerU for **future** PDFs
- Apply post-processing to **existing** PDFs
- Gradually migrate as PDFs are re-processed
- **Pros:** Best of both worlds
- **Cons:** Two code paths temporarily

---

## Files to Create/Modify

### New Files
1. `extraction_pipeline/mineru_postprocessor.py` - Post-processing module
2. `extraction_pipeline/artifact_patterns.py` - Regex patterns
3. `extraction_pipeline/tests/test_postprocessor.py` - Unit tests

### Modified Files
1. `infrastructure/modal_lib/extraction.py` - Add filters
2. `extraction_pipeline/table_classifier_v3.py` - Integrate post-processor
3. `extraction_pipeline/batch_classify_v3.py` - Add post-processing step

---

## New Pipeline Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                     MinerU JSON Input                                │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│  STEP 0: Post-Processing (NEW)                                       │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐   │
│  │ 0.1 Empty Filter │→ │ 0.2 Figure Det.  │→ │ 0.3 Diagram Det. │   │
│  └──────────────────┘  └──────────────────┘  └──────────────────┘   │
│           │                    │                     │               │
│           ▼                    ▼                     ▼               │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐   │
│  │ 0.4 Text Frag.   │→ │ 0.5 Split Merge  │→ │ 0.6 Header Graft │   │
│  └──────────────────┘  └──────────────────┘  └──────────────────┘   │
│           │                                                          │
│           ▼                                                          │
│  ┌──────────────────┐                                                │
│  │ 0.7 LLM Verify   │  (only for ambiguous cases)                   │
│  └──────────────────┘                                                │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│  STEP 1: Parse Clean Tables                                          │
│  (existing table_classifier_v3 logic)                                │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│  STEP 2: LLM Classification                                          │
│  (RESULTS / DESCRIPTIVE / SKIP)                                      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Expected Improvements

After implementing this pipeline:

| Metric | Before | After (Expected) |
|--------|--------|------------------|
| Artifacts passed to classifier | ~15% | <1% |
| False EMPTY classifications | 88 | ~20 (real empty) |
| False SKIP classifications | 165 | ~50 (real skips) |
| RESULTS precision | ~90% | ~98% |
| Split tables merged | 0 | All detected |

---

## Files to Create

1. `extraction_pipeline/mineru_postprocessor.py` - Main post-processing module
2. `extraction_pipeline/tests/test_postprocessor.py` - Unit tests
3. `extraction_pipeline/artifact_patterns.py` - Regex patterns and rules

---

## Next Steps

1. **Approve this plan** or request modifications
2. **Start with Phase 1** - Rule-based pre-filtering
3. **Re-run batch classification** after Phase 1 to measure improvement
4. **Iterate** based on new ground truth review
