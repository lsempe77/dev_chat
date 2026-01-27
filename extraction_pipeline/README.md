# Extraction Pipeline V2 SOTA

> **STATUS:** ✅ Production-Ready (Last Updated: January 15, 2026)  
> **USE THIS:** This is the ONLY active extraction pipeline. All previous versions (v1-v17, extractor.py) are archived in `archive/extraction_pipeline_old/`

Automated extraction of treatment effects from impact evaluation papers using BeautifulSoup HTML parsing and LLM classification.

## Overview

This pipeline extracts structured data from MineRU-processed PDFs stored in R2:
- **Stage 1**: Metadata extraction (title, authors, year)
- **Stage 2**: Table extraction using BeautifulSoup (preserves table dimensions)
- **Stage 3**: Rules-based + LLM classification (results vs descriptive tables)
- **Stage 4**: LLM enrichment (outcome definitions)

## Why BeautifulSoup?

The LLM was collapsing multi-dimensional tables. For example, Table 1 in Bossuroy et al. has:
- 3 outcomes × 3 treatment arms × 2 followup periods = **18 rows**

But the LLM was extracting only 3 rows (one per outcome). BeautifulSoup parses the HTML directly and preserves the full structure.

## Usage

```bash
# Extract specific study
python pipeline.py --study_id 121058356

# Disable LLM classification (rules-only)
python pipeline.py --no-llm

# Disable LLM enrichment
python pipeline.py --no-enrich
```

## Output

Results are saved to `outputs/{study_id}/`:
- `extracted_data.csv` - All extracted treatment effects
- `extracted_data.json` - Same data in JSON format
- `metadata.json` - Paper metadata

## Columns

| Column | Description |
|--------|-------------|
| study_id | Paper identifier |
| table_number | Table 1, Table A.6, etc. |
| table_caption | Full caption text |
| page_number | Page in PDF |
| section | Followup period or panel |
| treatment_arm | Capital, Psychosocial, Full, etc. |
| outcome_name | Dependent variable |
| coefficient | Treatment effect estimate |
| standard_error | SE in parentheses |
| significance | *, **, *** |
| sample_size | N observations |
| control_mean | Control group mean |
| control_sd | Control group SD |
| outcome_definition | LLM-enriched definition |

## Performance on Bossuroy (121058356)

| Metric | Value |
|--------|-------|
| Tables Found | 48 |
| Tables Extracted | 24 |
| Total Rows | 763 |
| Unique Outcomes | 117 |
| Coefficient Coverage | 100% |
| SE Coverage | 93.1% |
| Table 1 Match vs GT | 18/18 (100%) |

## Table Classification Rules

1. **Figure** → Skip (caption contains "figure")
2. **Descriptive** → Skip (balance, baseline, attrition, definition, etc.)
3. **Has "table"** → Extract
4. **Unknown** → LLM classification

## Files

**Active (Current Directory):**
- `pipeline.py` - **Production script** - Use this for all extraction
- `outputs/` - Extracted data per study (CSV + JSON)
- `README.md` - This documentation

**Archived (Do Not Use):**
- `../archive/extraction_pipeline_old/` - Contains 35+ deprecated scripts:
  - `extractor.py`, `extractor_v10.py` through `extractor_v17d.py`
  - `pipeline_v2.py` (superseded by pipeline.py)
  - Various analysis and debug scripts from development phase
  - All `v9-v17` experimental versions that led to this final version

## Dependencies

- beautifulsoup4
- pandas
- boto3
- openai (for OpenRouter)
- python-dotenv

## Configuration

Uses OpenRouter API via `OPENROUTER_API_KEY` in `.env`. Model: `anthropic/claude-3.5-haiku`
