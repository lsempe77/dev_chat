# New Extraction Approach: Direct HTML Table Parsing

## Problem Solved

The previous LLM-based extraction collapsed multi-dimensional tables:
- **LLM extracted**: 3 outcomes (one row per outcome)
- **Should have extracted**: 18 outcomes (3 outcomes × 3 arms × 2 followups)

## Solution: Parse MineRU HTML Directly

**Key insight**: MineRU already extracts tables as structured HTML. We can parse this directly without using an LLM, which:
1. Preserves all table dimensions (treatment arms, followup periods)
2. Extracts correct table numbering from captions
3. Gets page numbers directly
4. 100% deterministic (no LLM variability)

## Results on Table 1: Primary Outcomes

| Metric | Ground Truth | Extracted | Match Rate |
|--------|--------------|-----------|------------|
| Total rows | 18 | 18 | 100% |
| Coefficients | 18 | 18 | 100% |
| Standard Errors | 18 | 14 exact | 77.8% |

The 4 SE mismatches are due to OCR artifacts where values shifted between rows.

## Extracted Fields

```python
{
    'study_id': 121058356,
    'author': 'Bossuroy',
    'table_number': 1,                           # From caption
    'table_caption': 'Table 1: Primary Outcomes', # Literal text
    'page_number': 44,                           # From MineRU page_idx
    'followup_period': 'Followup 1 (6 months)',  # Row group
    'treatment_arm': 'Capital',                  # Row label
    'outcome_name': 'Gross consumption...',      # Column header
    'coefficient': 0.15,
    'standard_error': 0.05,
    'significance': '***',
    'sample_size': 4405,
    'literal_cell_text': '0.15*** (0.05)'        # Raw OCR text
}
```

## Code Location

- [extract_table1_v1.py](extraction_pipeline/extract_table1_v1.py) - Main extraction script
- [table1_extracted_v1.csv](extraction_pipeline/table1_extracted_v1.csv) - Output

## How It Works

1. **Load MineRU JSON** from R2 storage
2. **Find table by caption** (e.g., "Table 1")
3. **Parse HTML** with BeautifulSoup
4. **Identify table structure**:
   - Header row → outcome names
   - "Followup X" rows → followup period
   - "Capital/Psychosocial/Full" → treatment arm
   - "Observations" → sample size
5. **Extract each cell** as a separate row
6. **Handle OCR quirks** (SE on next row, etc.)

## Comparison with LLM Approach

| Aspect | LLM Approach | Direct HTML Parsing |
|--------|--------------|---------------------|
| Rows extracted | 3 | 18 |
| Table numbering | Wrong ("Table 2") | Correct ("Table 1") |
| Dimensions preserved | No | Yes |
| Deterministic | No | Yes |
| Processing time | ~5 sec | <1 sec |
| Cost | API calls | Free |

## Next Steps

1. **Generalize** to other tables (Table 2, 3, etc.)
2. **Handle different table formats** (some papers have different structures)
3. **Add prose text extraction** for context
4. **Validate on other studies** in the dataset
