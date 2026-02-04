# Extraction Pipeline V3

> **STATUS:** ✅ Production-Ready (Last Updated: February 4, 2026)  
> **MODULAR:** Reorganized into focused modules for maintainability

Automated extraction of treatment effects from impact evaluation papers using a **hybrid rules + LLM** approach.

---

## 📁 Directory Structure

```
extraction_pipeline/
├── pipeline.py              # Orchestration (extract_all_tables, run_pipeline)
│
├── core/                    # Infrastructure
│   ├── config.py           # PipelineConfig, constants
│   ├── llm_client.py       # LLM calls with caching
│   ├── storage.py          # R2 client, load_mineru_json
│   ├── registry.py         # Document tracking
│   └── errors.py           # Error handling
│
├── parsing/                 # Text/cell parsing
│   ├── ocr.py              # fix_ocr_spacing
│   └── cells.py            # parse_cell_comprehensive
│
├── classification/          # Table classification
│   ├── rules.py            # classify_table_rules
│   ├── llm.py              # classify_table_llm, classify_all_tables_llm
│   ├── classifier.py       # classify_table (entry point)
│   └── classifier_v3.py    # TableClassifierV3 (few-shot, 88%+ accuracy)
│
├── extraction/              # Value extraction
│   ├── __init__.py         # Module exports
│   ├── metadata.py         # extract_metadata, extract_metadata_llm
│   ├── sample_sizes.py     # extract_sample_sizes_from_table/prose
│   ├── prose.py            # extract_effects_from_prose/figures
│   └── extractors/         # Table format handlers
│       ├── base.py         # detect_table_orientation
│       ├── standard.py     # extract_results_table
│       ├── transposed.py   # extract_transposed_table
│       ├── treatments_cols.py  # extract_treatments_in_cols_table
│       ├── outcomes_rows.py    # extract_outcomes_in_rows_se_split
│       └── comparison.py   # extract_comparison_format_table
│
├── enrichment/              # Post-extraction (imports from postprocessing)
│   ├── outcomes.py         # Outcome classification
│   ├── analysis_type.py    # Subgroup/spillover detection
│   └── context.py          # LLM outcome definitions
│
├── postprocessing/          # MinerU cleanup
│   ├── mineru.py           # 8-step artifact removal
│   ├── lot_parser.py       # List of Tables repair
│   └── effect_sizes.py     # Legacy (also in enrichment/)
│
├── batch/                   # Batch processing
│   ├── classify.py         # Batch classification
│   └── extract.py          # Batch value extraction
│
├── adapters/                # Schema conversion
│   └── schema_adapter.py   # DataFrame ↔ ExtractedEstimate
│
├── outputs/                 # Results
└── archive/                 # Old scripts
```

## 🚀 Quick Start

```bash
# Classify all tables in corpus
python -m extraction_pipeline.batch.classify

# Extract values from RESULTS tables
python -m extraction_pipeline.batch.extract

# Full pipeline for single study
python extraction_pipeline/pipeline.py --study_id 121058356
```

### Top 10 Studies by Rows Extracted

| Study ID | Rows | Tables | Notes |
|----------|------|--------|-------|
| 121430610 | 2,789 | 89 | Large BRAC multi-arm study |
| 121058367 | 1,064 | 177 | Comprehensive impact evaluation |
| 188437804 | 727 | 38 | - |
| 121058356 | 711 | 48 | Niger Graduation (reference study) |
| 121327437 | 527 | 27 | - |
| BRAC_Selim_2020 | 525 | 26 | BRAC longitudinal study |
| 122182713 | 482 | 52 | - |
| BRAC_Emran_2012 | 404 | 17 | - |
| BRAC_Bandiera_2009 | 323 | 20 | - |
| 121326829 | 315 | 37 | - |

---

## 📈 Pipeline Evolution (V3 → V6)

### V3 Baseline (January 2026)
- **Coverage:** 48/54 studies (89%)
- **Rows:** 3,351
- **Issues:** 6 studies with zero extraction

### V4 Improvements
- **Coverage:** 51/54 studies (94%)
- **Rows:** 10,698
- **New Features:**
  - `treatments_in_cols` parser for transposed tables
  - European number format support (commas → dots)
  - `outcomes_in_rows_se_split` parser for SE in separate rows

### V5 Multi-Language Support
- **Coverage:** 52/54 studies (96%)
- **Rows:** 10,551
- **New Features:**
  - Spanish keywords (Tratamiento, Efecto, Impacto)
  - French keywords (Traitement, Effet)
  - Portuguese keywords (Tratamento, Efeito)
  - Multi-language header detection

### V6 Figure & Prose Extraction
- **Coverage:** 92/97 files (95%)
- **Rows:** 14,169
- **New Features:**
  - `extract_effects_from_figures()` - Extracts from figure captions
  - `extract_effects_from_prose()` - Narrative text extraction
  - Fallback cascade: Tables → Prose → Figures
  - Full R2 corpus support (97 files including BRAC studies)

---

## 🔍 Studies with Low/Zero Extraction (Explained)

### Zero Extraction Studies (5)

| Study | Tables | Issue | Action |
|-------|--------|-------|--------|
| BRAC_Ahmed_2009 | 5 | **Descriptive tables only** - Selection criteria, program components | Correct behavior |
| BRAC_Jalal_2013 | 3 | **Raw means table** - No regression coefficients | Correct behavior |
| 356305886 | 0 | **Overview document** - No quantitative data | Correct behavior |
| Raman_and_Howaida_2024 | 0 | **Review paper** - No original data | Correct behavior |
| Essential_for_Graduation.docx | 0 | **Word document** - Not a study | Correct behavior |

**Conclusion:** Zero extraction is CORRECT for these files - they don't contain treatment effect estimates.

### Low Extraction Studies (<10 rows)

| Study | Rows | Explanation |
|-------|------|-------------|
| 121058370 | 1 | Evaluation protocol/design, not results |
| BRAC_Siddiquee_2016 | 1 | Figure-based extraction (limited data) |
| BRAC_Haseen_2007 | 1 | Single outcome table |
| 121305126 | 2 | Pilot study with few outcomes |
| BRAC_Ara_2016 | 3 | Brief report |
| BRAC_Krishna_2012 | 3 | Short paper |
| 121058361 | 8 | Learning brief (figures extracted) |

---

## Architecture

```
PDF → MineRU (GPU) → JSON/HTML → Extraction Pipeline → CSV/JSON
                                        │
                                        ├── Stage 1: Metadata (rules + LLM)
                                        ├── Stage 2: Table filtering (BeautifulSoup + rules)
                                        ├── Stage 3: Classification (rules → LLM fallback)
                                        ├── Stage 4: Coefficient/SE/CI parsing (regex)
                                        ├── Stage 5: Significance parsing (rules → LLM fallback)
                                        ├── Stage 6: Enrichment (LLM - definitions, categories)
                                        └── Stage 7: Analysis type classification (LLM reasoning)
```

### Table Orientation Detection (4 Types)

| Type | Pattern | Example |
|------|---------|---------|
| `columns` | Outcomes in rows, treatments in columns | Standard format |
| `rows` | Treatments in rows, outcomes in columns | Transposed |
| `treatments_in_cols` | Treatment arms as column headers | Multi-arm studies |
| `outcomes_in_rows_se_split` | SE in separate row below coefficient | Split format |

---

## Output Schema (42 Columns)

The pipeline extracts **42 fields** achieving 100% QEX + OM parity:

| Category | Fields |
|----------|--------|
| **Identifiers** | `study_id`, `table_number`, `page_number` |
| **Paper Metadata** | `authors`, `year`, `country`, `study_design`, `is_experimental`, `follow_up_months`, `intervention_name` |
| **Table Context** | `table_caption`, `section`, `treatment_arm` |
| **Outcome** | `outcome_name`, `outcome_category`, `outcome_definition` |
| **Core Numeric** | `coefficient`, `standard_error`, `significance`, `p_value`, `p_value_text` |
| **CI Bounds** | `ci_lower`, `ci_upper` |
| **Sample Sizes** | `sample_size`, `n_treatment`, `n_control`, `n_clusters` |
| **Control Stats** | `control_mean`, `control_sd` |
| **Effect Sizes** | `cohens_d`, `hedges_g`, `effect_variance`, `effect_se` |
| **Analysis Types** | `is_main_effect`, `is_subgroup`, `subgroup_variable`, `is_spillover`, `spillover_type`, `is_cost_outcome`, `is_mechanism` |
| **Debug** | `literal_cell_text`, `t_statistic` |

---

## Usage

```bash
# Extract specific study
python pipeline.py --study_id 121058356

# Run full corpus extraction (all 97 files)
python run_full_corpus_v2.py

# Disable LLM classification (rules-only)
python pipeline.py --no-llm

# Disable LLM enrichment
python pipeline.py --no-enrich
```

## Output Files

**Per-study outputs:** `outputs/{study_id}/`
- `extracted_data.csv` - All extracted treatment effects (42 columns)
- `extracted_data.json` - Same data in JSON format
- `metadata.json` - Paper metadata

**Full corpus outputs:** `outputs/`
- `full_corpus_all_studies.csv` - Combined dataset (14,169 rows)
- `full_corpus_all_stats.csv` - Per-study statistics

---

## Hybrid Design Philosophy

| Stage | Primary Method | Fallback | Why |
|-------|---------------|----------|-----|
| Metadata | Rules + LLM | - | LLM extracts author, country, study design |
| Table Filter | Rules + regex | - | Caption patterns are predictable |
| Classification | Rules | **LLM** | Ambiguous tables need reasoning |
| Parsing | Regex | - | Coefficient/SE formats are standard |
| Significance | Rules | **LLM** | Novel symbols need interpretation |
| Enrichment | **LLM** | - | Semantic understanding required |
| Analysis Types | **LLM** | - | Reasoning about table context |

**Benefits:**
- **Fast**: Rules handle 90%+ of cases instantly
- **Cost-effective**: LLM only called when needed
- **Accurate**: LLM handles edge cases rules miss
- **Deterministic**: Same input → same output (mostly)

---

## Field Coverage (Study 121058356 - Niger Graduation)

| Field | Coverage | Notes |
|-------|----------|-------|
| coefficient, SE, authors, year, country, study_design | **100%** | Paper-level fields |
| significance, is_experimental, follow_up_months | **100%** | From metadata extraction |
| p_value | 63% | Significance stars mapped |
| sample_size | 85% | From Observations rows |
| control_mean, control_sd | 81-94% | From table footer |
| cohens_d | 90% | Calculated where SD available |
| hedges_g | 52% | Needs N treatment/control |
| outcome_category | 66% | LLM classification |
| ci_lower, ci_upper | 0% | Study doesn't report CI (parser ready) |

---

## Significance Parser

The pipeline includes a sophisticated significance parser (`src/extraction/significance.py`) that:

1. **Rule-based parsing** (fast, free):
   - Star notation: `*`, `**`, `***` → p<0.05, p<0.01, p<0.001
   - Symbols: `†`, `‡`, `§` → configurable p-values
   - Explicit: `p<.05`, `p=0.023`, `p>.10`
   - Text: `NS`, `n.s.`, `not significant`

2. **Footnote extraction**: Parses table footnotes to update mappings
   - `"*** p<.005"` → Updates `***` mapping to 0.005

3. **LLM fallback** (for ambiguous cases):
   - Unknown symbols (e.g., `◊`, `●`)
   - Complex footnotes ("significant at conventional levels")
   - Low-confidence rule-based results

---

## Table Classification Rules

1. **Figure** → Skip (caption contains "figure")
2. **Descriptive** → Skip (balance, baseline, attrition, definition, etc.)
3. **Has "table"** → Extract
4. **Unknown** → LLM classification

---

## Files

**Active:**
- `pipeline.py` - **Production script** - Use this for all extraction
- `r2_utils.py` - R2 storage utilities (list/load all studies)
- `outputs/` - Extracted data per study (CSV + JSON)
- `README.md` - This documentation

**Run Scripts:**
- `../run_full_corpus_v2.py` - Full corpus extraction (all 97 files)
- `../run_pilot_v4.py` - Pilot extraction (54 numeric IDs)

**Supporting Modules:**
- `../src/extraction/significance.py` - Significance parser (rules + LLM)
- `../src/extraction/schemas.py` - Pydantic schemas for extraction

**Archived (Do Not Use):**
- `../archive/extraction_pipeline_old/` - Contains 35+ deprecated scripts

---

## Dependencies

```
beautifulsoup4
pandas
boto3
openai (for OpenRouter)
python-dotenv
```

## Configuration

**Required Environment Variables:**
```bash
OPENROUTER_API_KEY=sk-or-...          # For LLM calls
CLOUDFLARE_ACCOUNT_ID=...              # For R2 storage
R2_ACCESS_KEY_ID=...                   # R2 credentials
R2_SECRET_ACCESS_KEY=...               # R2 credentials
```

**LLM Model:** `anthropic/claude-3.5-haiku` via OpenRouter (fast, cost-effective)

---

## R2 Storage Structure

The pipeline reads from Cloudflare R2 bucket `devchat-pdfs`:

```
devchat-pdfs/
├── rags/0816e8d3-ab23-417c-bf3f-e45531411c73/
│   ├── outputs/
│   │   ├── json/     # 97 MinerU JSON files
│   │   └── md/       # 97 Markdown files
│   └── input-pdfs/   # Original PDFs
└── input-pdfs/       # Upload folder
```

**Study Types:**
- **56 numeric IDs** (e.g., `121058356`)
- **36 BRAC/named studies** (e.g., `BRAC_Bandiera_2017`)

---

## Related Documentation

- [ROADMAP.md](../docs/ROADMAP.md) - Future plans for extraction pipeline
- [SETUP_TRACKER.md](../SETUP_TRACKER.md) - Current implementation status
- [schemas.py](../src/extraction/schemas.py) - Data schemas (RAG, SCREENING, FULL modes)
