# Extraction Pipeline V2: Unified Plan

## Goal
One pipeline that extracts everything from a paper:
- **Metadata** (title, authors, year, abstract)
- **Outcomes** (names, definitions, measurement details)
- **Effect Sizes** (coefficients, SE, sample size, significance)
- **Context** (treatment arms, followup periods, control group info)

## Key Insight from Our Work

| Task | Best Tool | Why |
|------|-----------|-----|
| **Table parsing** | BeautifulSoup | Preserves dimensions (18 rows vs 3) |
| **Finding text in prose** | LLM | Good at semantic search |
| **Metadata extraction** | Direct from MineRU JSON | Already structured |
| **Table identification** | Caption matching | Reliable, no LLM needed |

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    EXTRACTION PIPELINE V2                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐       │
│  │   Stage 1    │───▶│   Stage 2    │───▶│   Stage 3    │       │
│  │  Metadata    │    │   Tables     │    │   Context    │       │
│  │  (direct)    │    │ (BeautifulSoup)│   │   (LLM)     │       │
│  └──────────────┘    └──────────────┘    └──────────────┘       │
│                                                                  │
│  Input: MineRU JSON from R2                                     │
│  Output: Structured CSV/JSON with all fields                    │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Stage 1: Metadata Extraction (No LLM)

**Source**: MineRU JSON top-level fields

```python
{
    'study_id': from filename,
    'title': doc['title'],
    'authors': doc['authors'],
    'year': doc['year'],
    'abstract': doc['abstract'],
    'page_count': doc['page_count']
}
```

**Complexity**: Low - just read JSON fields

---

## Stage 2: Table Extraction (BeautifulSoup)

**Source**: `doc['tables']` - list of HTML tables

### Step 2a: Identify Results Tables
- Filter tables by caption containing: "Table", "Results", "Effects", "Outcomes"
- Skip figures (type != 'table')
- Skip balance/descriptive tables

### Step 2b: Parse Table Structure
For each results table:

1. **Header Row** → Outcome names (column headers)
2. **Row Labels** → Treatment arms (Capital, Psychosocial, Full, Treatment, Control)
3. **Section Headers** → Followup periods, subgroups
4. **Data Cells** → coefficient (SE) format

### Step 2c: Extract Each Cell
Output one row per cell:

```python
{
    'study_id': 121058356,
    'table_number': 1,
    'table_caption': 'Table 1: Primary Outcomes',
    'page_number': 44,
    'outcome_name': 'Gross consumption (daily, USD/adult eq.)',
    'treatment_arm': 'Capital',
    'followup_period': 'Followup 1 (6 months)',
    'coefficient': 0.15,
    'standard_error': 0.05,
    'significance': '***',
    'sample_size': 4405,
    'control_mean': 1.95,
    'control_sd': 1.12,
    'literal_cell_text': '0.15*** (0.05)'
}
```

**Complexity**: Medium - requires parsing different table formats

---

## Stage 3: Context Enrichment (LLM)

**Source**: `doc['content']` - full prose text

### Tasks for LLM:
1. **Outcome definitions** - What does "Food security (raw sum)" mean?
2. **Measurement details** - Units, scales, timing
3. **Treatment descriptions** - What was each treatment arm?
4. **Sample description** - Who was studied, where, when?

### LLM Prompt Strategy:
```
Given this paper text and extracted outcome names, find:
1. Definition of each outcome
2. How each outcome was measured
3. What each treatment arm received
```

**Output**: Enriched metadata per outcome

**Complexity**: Low-Medium - LLM is good at this

---

## Data Flow

```
R2 Storage (MineRU JSON)
    │
    ▼
┌───────────────────┐
│  load_mineru()    │
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐     ┌────────────────────┐
│ Stage 1: Metadata │────▶│ metadata.json      │
└─────────┬─────────┘     └────────────────────┘
          │
          ▼
┌───────────────────┐     ┌────────────────────┐
│ Stage 2: Tables   │────▶│ extracted_data.csv │
│ (BeautifulSoup)   │     │ (one row per cell) │
└─────────┬─────────┘     └────────────────────┘
          │
          ▼
┌───────────────────┐     ┌────────────────────┐
│ Stage 3: Context  │────▶│ enriched_data.csv  │
│ (LLM on prose)    │     │ (with definitions) │
└───────────────────┘     └────────────────────┘
```

---

## File Structure

```
extraction_pipeline/
├── pipeline_v2.py          # Main orchestrator
├── stage1_metadata.py      # Metadata extraction
├── stage2_tables.py        # BeautifulSoup table parsing
├── stage3_context.py       # LLM prose extraction
├── table_patterns.py       # Common table format handlers
├── utils.py                # R2 loading, parsing helpers
└── outputs/
    └── 121058356/
        ├── metadata.json
        ├── tables_raw.json
        ├── extracted_data.csv
        └── enriched_data.csv
```

---

## Questions for Discussion

### 1. Table Format Generalization
Different papers have different table structures:
- **Bossuroy**: 3 columns (outcomes) × 3 arms × 2 followups
- **Others**: May have outcomes in rows, treatments in columns

**Options**:
a) Build format detectors for common patterns
b) Use LLM to identify table structure, then BeautifulSoup to parse
c) Manual mapping per paper (not scalable)

**Recommendation**: Option (b) - LLM identifies structure, BeautifulSoup extracts

### 2. What Tables to Extract?
- All tables? (may include descriptive/balance tables)
- Only numbered "Table X"?
- Only tables with specific keywords in caption?

**Recommendation**: Tables with "effect", "outcome", "result", "impact" in caption

### 3. Cohen's d Calculation
When to calculate Cohen's d?
- Stage 2 (during extraction)?
- Post-processing step?

**Recommendation**: Separate post-processing (needs complete data)

### 4. Ground Truth Validation
How to validate extraction quality?
- Use your manual table1_121058356.csv as test case
- Expand GT to other tables in same paper?

---

## Implementation Order

1. **[TODAY]** `stage2_tables.py` - Generalize Table 1 parser to handle multiple tables
2. **[NEXT]** `stage1_metadata.py` - Simple metadata extraction
3. **[THEN]** `stage3_context.py` - LLM for prose context
4. **[FINALLY]** `pipeline_v2.py` - Orchestrate all stages

---

## Success Metrics

For Bossuroy paper (121058356):

| Metric | Target |
|--------|--------|
| Tables identified | All numbered tables |
| Rows extracted | 100% of data cells |
| Coefficient accuracy | 100% |
| SE accuracy | >90% |
| Metadata complete | Title, authors, year, abstract |

---

## Your Feedback Needed

1. **Agree with 3-stage architecture?**
2. **Which tables should we extract?** (all vs results-only)
3. **Stage 3 priority?** (LLM enrichment now or later?)
4. **Other papers to test on?** (beyond Bossuroy)
