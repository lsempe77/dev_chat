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

## 🔧 Function & Prompt Reference (For Review)

This section maps **ALL** functions and LLM prompts in the extraction pipeline for systematic code review.

---

### 📋 Complete Function Inventory

#### `pipeline.py` - Main Orchestration
| Function | Uses LLM | Description |
|----------|----------|-------------|
| `run_pipeline()` | ✅ | Main entry point - runs all stages |
| `extract_all_tables()` | ✅ | Extract from all tables in document |
| `_extract_by_orientation()` | ❌ | Route to correct extractor based on table format |
| `_filter_suspicious_rows()` | ❌ | Remove false positive extractions |
| `_extract_metadata_stage()` | ✅ | Run metadata extraction |
| `_fallback_extraction()` | ✅ | Prose/figure extraction when tables fail |
| `_enrich_with_metadata()` | ❌ | Add paper metadata to rows |
| `_extract_prose_sample_sizes()` | ✅ | Get sample sizes from prose |
| `_run_enrichment_stages()` | ✅ | Run outcome classification, context, analysis type |
| `_print_extraction_stats()` | ❌ | Print extraction summary |
| `_print_final_summary()` | ❌ | Print final pipeline summary |

#### `core/` - Infrastructure

| File | Function | Uses LLM | Description |
|------|----------|----------|-------------|
| `storage.py` | `get_r2_client()` | ❌ | Initialize R2 client |
| `storage.py` | `load_mineru_json()` | ❌ | Load MineRU JSON from R2 |
| `storage.py` | `list_available_studies()` | ❌ | List all studies in R2 |
| `storage.py` | `list_projects()` | ❌ | List R2 projects |
| `llm_client.py` | `call_llm()` | ✅ | Main LLM call with caching |
| `llm_client.py` | `sanitize_llm_response()` | ❌ | Clean markdown fences |
| `llm_client.py` | `parse_llm_json()` | ❌ | Parse JSON from response |
| `llm_client.py` | `validate_llm_json()` | ❌ | Validate against Pydantic schema |
| `llm_client.py` | `get_prompt_hash()` | ❌ | Hash for caching |
| `llm_client.py` | `get_cache()` | ❌ | Get cache instance |
| `llm_client.py` | `get_cached_llm_response()` | ❌ | Check cache |
| `llm_client.py` | `get_llm_client()` | ❌ | Get client singleton |
| `errors.py` | `get_accumulator()` | ❌ | Get error accumulator |
| `errors.py` | `set_accumulator()` | ❌ | Set error accumulator |
| `errors.py` | `reset_accumulator()` | ❌ | Reset error state |
| `registry.py` | `get_registry()` | ❌ | Get document registry |
| `registry.py` | `register_upload()` | ❌ | Register uploaded document |
| `registry.py` | `check_duplicate()` | ❌ | Check for duplicate uploads |
| `registry.py` | `compute_content_hash()` | ❌ | Hash content for dedup |
| `registry.py` | `compute_file_hash()` | ❌ | Hash file for dedup |

#### `classification/` - Table Classification

| File | Function | Uses LLM | Description |
|------|----------|----------|-------------|
| `rules.py` | `classify_table_rules()` | ❌ | Regex-based classification |
| `llm.py` | `classify_all_tables_llm()` | ✅ | Batch LLM classification |
| `llm.py` | `classify_table_llm()` | ✅ | Single-table LLM classification |
| `classifier.py` | `classify_table()` | ✅ | Entry point (rules → LLM fallback) |
| `classifier_v3.py` | `TableClassifierV3.run_pipeline()` | ✅ | Few-shot classifier (88%+ accuracy) |

#### `extraction/` - Value Extraction

| File | Function | Uses LLM | Description |
|------|----------|----------|-------------|
| `metadata.py` | `extract_metadata()` | ❌ | Basic metadata from MineRU |
| `metadata.py` | `extract_metadata_llm()` | ✅ | LLM-enhanced metadata |
| `sample_sizes.py` | `extract_sample_sizes_from_table()` | ❌ | Parse N rows from tables |
| `sample_sizes.py` | `extract_sample_sizes_from_prose()` | ✅ | LLM extraction from text |
| `prose.py` | `extract_effects_from_prose()` | ✅ | Extract from narrative text |
| `prose.py` | `extract_effects_from_figures()` | ✅ | Extract from figure captions |

#### `extraction/extractors/` - Table Format Handlers

| File | Function | Uses LLM | Description |
|------|----------|----------|-------------|
| `base.py` | `detect_table_orientation()` | ❌ | Detect table format type |
| `standard.py` | `extract_results_table()` | ❌ | Standard format (outcomes=rows) |
| `standard.py` | `is_treatment_row()` | ❌ | Check if row is treatment arm |
| `standard.py` | `normalize_treatment_arm()` | ❌ | **NEW** - Map T1/T2 to names |
| `transposed.py` | `extract_transposed_table()` | ❌ | Transposed format (Mean|SE|p) |
| `treatments_cols.py` | `extract_treatments_in_cols_table()` | ❌ | Multi-arm format (T1|T2|T3 cols) |
| `outcomes_rows.py` | `extract_outcomes_in_rows_se_split()` | ❌ | SE in separate row |
| `comparison.py` | `extract_comparison_format_table()` | ❌ | Comparison tables (T1 vs T2) |

#### `parsing/` - Text/Cell Parsing

| File | Function | Uses LLM | Description |
|------|----------|----------|-------------|
| `ocr.py` | `fix_ocr_spacing()` | ❌ | Clean MineRU OCR artifacts |
| `cells.py` | `parse_cell_comprehensive()` | ❌ | Extract coef/SE/CI/p-value |
| `cells.py` | `parse_coefficient_se()` | ❌ | Simplified coef+SE extraction |

#### `enrichment/` - Post-Extraction LLM

| File | Function | Uses LLM | Description |
|------|----------|----------|-------------|
| `outcomes.py` | `classify_outcomes()` | ✅ | Categorize outcomes |
| `context.py` | `enrich_with_context()` | ✅ | Add outcome definitions |
| `analysis_type.py` | `classify_analysis_type()` | ✅ | **IMPROVED** - Detect subgroups, spillovers |

#### `postprocessing/` - Calculations & Cleanup

| File | Function | Uses LLM | Description |
|------|----------|----------|-------------|
| `effect_sizes.py` | `calculate_cohens_d()` | ❌ | Cohen's d calculation |
| `effect_sizes.py` | `calculate_hedges_g()` | ❌ | Hedges' g (bias-corrected) |
| `effect_sizes.py` | `calculate_effect_variance()` | ❌ | Effect size variance |
| `effect_sizes.py` | `calculate_effect_sizes_for_row()` | ❌ | Calculate for single row |
| `effect_sizes.py` | `calculate_effect_sizes()` | ❌ | Main entry point |
| `effect_sizes.py` | `summarize_effect_sizes()` | ❌ | Summary statistics |
| `mineru.py` | `postprocess_mineru_doc()` | ❌ | 8-step artifact removal |
| `lot_parser.py` | `parse_list_of_tables()` | ❌ | Parse LoT from markdown |
| `lot_parser.py` | `match_tables_to_list()` | ❌ | Match tables to LoT entries |
| `lot_parser.py` | `repair_table_captions()` | ❌ | Fix missing captions |
| `lot_parser.py` | `analyze_tables_with_lot()` | ❌ | Full LoT analysis |

#### `adapters/` - Schema Conversion

| File | Function | Uses LLM | Description |
|------|----------|----------|-------------|
| `schema_adapter.py` | `row_to_extracted_estimate()` | ❌ | Convert row to Pydantic model |
| `schema_adapter.py` | `convert_dataframe_to_schema()` | ❌ | Convert DataFrame to models |
| `schema_adapter.py` | `validate_dataframe_columns()` | ❌ | Validate column presence |
| `schema_adapter.py` | `estimates_to_dataframe()` | ❌ | Models back to DataFrame |
| `schema_adapter.py` | `normalize_authors()` | ❌ | Normalize author format |
| `schema_adapter.py` | `safe_int/float/str/bool()` | ❌ | Safe type conversions |
| `supabase_loader.py` | `clean_value()` | ❌ | Clean NaN for database |
| `supabase_loader.py` | `row_to_db_record()` | ❌ | Convert to DB record |
| `supabase_loader.py` | `validate_record()` | ❌ | Validate before insert |
| `supabase_loader.py` | `SupabaseLoader.*` | ❌ | Upload to Supabase |

#### `batch/` - Batch Processing

| File | Function | Uses LLM | Description |
|------|----------|----------|-------------|
| `classify.py` | `run_batch_classification()` | ✅ | Classify all tables in corpus |
| `classify.py` | `process_single_pdf()` | ✅ | Process one PDF |
| `classify.py` | `list_all_json_files()` | ❌ | List all JSONs in R2 |
| `classify.py` | `extract_study_id_from_key()` | ❌ | Parse study ID from path |
| `extract.py` | `run_batch_extraction()` | ✅ | Extract from all RESULTS tables |
| `extract.py` | `load_document()` | ❌ | Load document from R2 |
| `extract.py` | `extract_table_by_index()` | ❌ | Extract single table |
| `extract.py` | `find_latest_results_csv()` | ❌ | Find classification results |

---

### Stage 1: Metadata Extraction

| Function | File | Uses LLM | Description |
|----------|------|----------|-------------|
| `extract_metadata()` | `extraction/metadata.py` | ❌ | Basic extraction from MineRU JSON |
| `extract_metadata_llm()` | `extraction/metadata.py` | ✅ | LLM-enhanced metadata extraction |

**Prompt 1: Metadata Extraction** ([metadata.py#L52](extraction/metadata.py))
```
Extract metadata from this academic paper. Return ONLY a JSON object with these fields.
If a field cannot be determined, use null.

PAPER TEXT: {first 4000 chars}
ABSTRACT: {abstract}

Return JSON with:
{
  "authors": "...", "year": 2021, "country": "...", "countries_list": [...],
  "study_design": "RCT", "is_experimental": true, "intervention_name": "...",
  "follow_up_months": 18, "sample_description": "..."
}
```
**🔍 Improvement Opportunities:**
- Add examples for edge cases (multi-country studies, cluster-RCTs)
- Add structured output schema validation
- Extract DOI/publication venue

---

### Stage 2: Table Classification

| Function | File | Uses LLM | Description |
|----------|------|----------|-------------|
| `classify_table_rules()` | `classification/rules.py` | ❌ | Regex-based classification |
| `classify_table_llm()` | `classification/llm.py` | ✅ | Single-table LLM classification |
| `classify_all_tables_llm()` | `classification/llm.py` | ✅ | Batch classification with context |
| `TableClassifierV3.run_pipeline()` | `classification/classifier_v3.py` | ✅ | Few-shot classifier (88%+ accuracy) |

**Prompt 2: Batch Table Classification** ([llm.py#L38](classification/llm.py))
```
You are an expert at analyzing academic impact evaluation papers.

TASK: Identify which tables contain TREATMENT EFFECT ESTIMATES...

WHAT TO EXTRACT (mark as "results"):
- Regression tables showing causal impact estimates (ITT, ATT, LATE, DiD)
- Tables with coefficients and standard errors in parentheses...

WHAT TO SKIP (mark as "descriptive"):
- Sample composition tables, Balance tables, Summary statistics...

{table_list with previews}

Return a JSON object mapping each table ID to either "results" or "descriptive".
```
**🔍 Improvement Opportunities:**
- Add cost-effectiveness tables as RESULTS
- Handle mechanism/mediator tables explicitly
- Add confidence scores to output

**Prompt 3: Few-Shot Classification** ([classifier_v3.py#L880](classification/classifier_v3.py))
```
You are an expert at analyzing impact evaluation research papers. Classify each table.

=== CATEGORIES ===
**RESULTS**: Treatment effects, regression coefficients, ITT/ATE/LATE...
**DESCRIPTIVE**: Balance tables, summary stats, baseline characteristics...
**SKIP**: Response codes, survey codebooks, empty artifacts

=== FEW-SHOT EXAMPLES ===
{examples}

=== KEY RULES ===
1. Stars (*) on "Difference" column in balance tables = DESCRIPTIVE
2. Stars (*) on "Treatment" row with (SE) below = RESULTS
3. Columns labeled (1), (2), (3) with coefficients = RESULTS
... (12 rules total)

=== TABLES TO CLASSIFY ===
{table entries with body samples}
```
**🔍 Improvement Opportunities:**
- Add more few-shot examples for edge cases (appendix tables, Spanish tables)
- Tune confidence thresholds
- Add chain-of-thought reasoning

---

### Stage 3: Cell Parsing (Rules Only)

| Function | File | Uses LLM | Description |
|----------|------|----------|-------------|
| `parse_cell_comprehensive()` | `parsing/cells.py` | ❌ | Extract coef/SE/CI/p-value from cell |
| `parse_coefficient_se()` | `parsing/cells.py` | ❌ | Simplified coef+SE extraction |
| `fix_ocr_spacing()` | `parsing/ocr.py` | ❌ | Clean MineRU OCR artifacts |

**Regex Patterns Used:**
- Coefficient: `-?\d+\.?\d*` (after removing brackets/parens/stars)
- SE in parens: `\(([^)]+)\)` then extract number
- CI bounds: `\[(-?\d+\.?\d*)\s*,\s*(-?\d+\.?\d*)\]`
- European format: `\d+,\d{1,3}` → convert comma to dot
- Stars: `[\*†‡§]+`

**🔍 Improvement Opportunities:**
- Handle negative coefficients with en-dash (`−`) vs hyphen (`-`)
- Add support for percentage expressions (`15pp`, `12%`)
- Extract clustered SEs explicitly

---

### Stage 4: Table Value Extraction

| Function | File | Uses LLM | Description |
|----------|------|----------|-------------|
| `extract_results_table()` | `extractors/standard.py` | ❌ | Standard format (outcomes=rows, treatments=cols) |
| `extract_transposed_table()` | `extractors/transposed.py` | ❌ | Transposed format (Mean Effect | SE | p-value) |
| `extract_treatments_in_cols_table()` | `extractors/treatments_cols.py` | ❌ | Multi-arm format (T1 | T2 | T3 columns) |
| `extract_outcomes_in_rows_se_split()` | `extractors/outcomes_rows.py` | ❌ | SE in separate row below coefficient |
| `extract_comparison_format_table()` | `extractors/comparison.py` | ❌ | Comparison tables (T1 vs T2) |
| `detect_table_orientation()` | `extractors/base.py` | ❌ | Detect which extractor to use |

**Treatment Arm Keywords** (multi-language):
```python
TREATMENT_KEYWORDS = [
    # English
    'capital', 'psychosocial', 'full', 'treatment', 'treated', 'program',
    'cct', 'grant', 'training', 'coaching', 'savings', 'stipend', 'transfer',
    # Spanish
    'tratamiento', 'tratado', 'grupo tratamiento', 'beneficiario',
    # French
    'traitement', 'traité', 'groupe traitement', 'bénéficiaire',
    # Portuguese
    'tratamento', 'tratado', 'grupo tratamento', 'beneficiário',
]
```

**🔍 Improvement Opportunities:**
- Add dynamic orientation detection based on header analysis
- Handle merged cells better
- Add treatment arm normalization (T1, T2 → descriptive names)

---

### Stage 5: Fallback Extraction (Prose & Figures)

| Function | File | Uses LLM | Description |
|----------|------|----------|-------------|
| `extract_effects_from_prose()` | `extraction/prose.py` | ✅ | Extract from narrative text |
| `extract_effects_from_figures()` | `extraction/prose.py` | ✅ | Extract from figure captions |

**Prompt 4: Prose Effect Extraction** ([prose.py#L62](extraction/prose.py))
```
Extract ALL treatment effect estimates from this research paper text.

TEXT: {combined sections: abstract, results, conclusion}

For each effect mentioned, extract:
1. outcome_name, 2. treatment_arm, 3. coefficient, 4. standard_error,
5. p_value, 6. significance, 7. ci_lower, 8. ci_upper,
9. effect_type, 10. source_sentence

Return as JSON array. Only include effects with numeric coefficients.
```
**🔍 Improvement Opportunities:**
- Add few-shot examples for complex sentence structures
- Handle qualitative descriptions ("large positive effect")
- Extract comparison groups explicitly

**Prompt 5: Figure Effect Extraction** ([prose.py#L162](extraction/prose.py))
```
Extract treatment effect estimates from these figure descriptions and captions.

FIGURE CONTEXTS: {figure captions + surrounding text}

For each effect mentioned, extract:
1. outcome_name, 2. treatment_arm, 3. coefficient, 4. standard_error,
5. p_value, 6. significance, 7. ci_lower, 8. ci_upper,
9. effect_direction, 10. effect_description, 11. figure_reference

Return as JSON array. Include effects even if only qualitative.
```
**🔍 Improvement Opportunities:**
- Add graph description understanding
- Extract from forest plot patterns
- Handle coefficient plots

---

### Stage 6: Sample Size Extraction

| Function | File | Uses LLM | Description |
|----------|------|----------|-------------|
| `extract_sample_sizes_from_table()` | `extraction/sample_sizes.py` | ❌ | Parse N rows from tables |
| `extract_sample_sizes_from_prose()` | `extraction/sample_sizes.py` | ✅ | LLM extraction from text |

**Prompt 6: Sample Size from Prose** ([sample_sizes.py#L135](extraction/sample_sizes.py))
```
Extract sample sizes from this research paper text.

TEXT: {first 15k chars}

Find and return:
1. N_treatment - number of individuals/units in treatment group
2. N_control - number of individuals/units in control group
3. N_total - total sample size
4. N_clusters - number of clusters if cluster-randomized

Return in this format:
n_treatment: NUMBER or UNKNOWN
n_control: NUMBER or UNKNOWN
n_total: NUMBER or UNKNOWN
n_clusters: NUMBER or UNKNOWN
```
**🔍 Improvement Opportunities:**
- Handle attrition-adjusted sample sizes
- Extract by follow-up wave
- Handle panel data (N x T observations)

---

### Stage 7: Enrichment (LLM-Heavy)

| Function | File | Uses LLM | Description |
|----------|------|----------|-------------|
| `classify_outcomes()` | `enrichment/outcomes.py` | ✅ | Categorize outcomes (income, health, etc.) |
| `enrich_with_context()` | `enrichment/context.py` | ✅ | Add outcome definitions from paper |
| `classify_analysis_type()` | `enrichment/analysis_type.py` | ✅ | Detect subgroups, spillovers, mechanisms |

**Prompt 7: Outcome Classification** ([outcomes.py#L40](enrichment/outcomes.py))
```
Classify these outcome variables into categories.

CATEGORIES: {domain-specific list}

OUTCOMES:
- {outcome1}
- {outcome2}
...

INSTRUCTIONS:
1. Classify EVERY outcome into the most appropriate category
2. Use exact category names from the list above
3. If unsure, use "Other" or the closest matching category

Return format (one per line, must classify ALL):
outcome_name|category
```
**🔍 Improvement Opportunities:**
- Add confidence scores
- Use hierarchical categories (Income → Wage Income, Business Income)
- Cache common outcome mappings

**Prompt 8: Outcome Definitions** ([context.py#L21](enrichment/context.py))
```
Given this paper excerpt and list of outcome variables, provide brief definitions.

OUTCOME VARIABLES:
- {outcome1}
- {outcome2}
...

PAPER TEXT: {first 15k chars}

For each outcome, provide a one-sentence definition based on the paper.
Format each line as: outcome_name|definition

Only include outcomes you can find definitions for in the text.
```
**🔍 Improvement Opportunities:**
- Add measurement unit extraction
- Link to survey questions if available
- Add index composition (e.g., "food security index = sum of 5 items")

**Prompt 9: Analysis Type Classification** ([analysis_type.py#L54](enrichment/analysis_type.py)) ✅ ENHANCED
```
You are an expert at analyzing impact evaluation research papers.

Classify each result row into categories:

1. MAIN EFFECT (primary treatment effect on full sample)?
2. SUBGROUP analysis (by gender, asset_quartile, region, etc.)?
   - Use STANDARDIZED variables: gender, asset_quartile, age_group, baseline_outcome, education, region, urban_rural
3. SPILLOVER analysis (effects on non-beneficiaries)?
4. COST-EFFECTIVENESS analysis?
5. MECHANISM/MEDIATOR analysis?
6. ROBUSTNESS CHECK (placebo, IV, bounds)?
7. ESTIMAND TYPE (ITT, ATT, LATE, TOT)?

TREATMENT ARMS IN CAPTION: {from caption}
TABLES TO CLASSIFY: {table contexts}

Return JSON with fields: main_effect, subgroup, subgroup_var, spillover,
spillover_type, cost, mechanism, is_robustness, estimand_type

Examples included for consistent output format.
```
**✅ Implemented Improvements:**
- Standardized subgroup variable vocabulary
- Added robustness check detection
- Added estimand type (ITT/ATT/LATE/TOT)
- 8 example outputs in prompt

---

### Stage 8: Effect Size Calculation (Rules Only)

| Function | File | Uses LLM | Description |
|----------|------|----------|-------------|
| `calculate_cohens_d()` | `postprocessing/effect_sizes.py` | ❌ | d = coefficient / SD |
| `calculate_hedges_g()` | `postprocessing/effect_sizes.py` | ❌ | Bias-corrected SMD |
| `calculate_effect_variance()` | `postprocessing/effect_sizes.py` | ❌ | Variance of effect size |
| `calculate_effect_sizes()` | `postprocessing/effect_sizes.py` | ❌ | Main entry point for all calculations |

**Formulas:**
- Cohen's d: `d = coefficient / control_sd`
- Hedges' g: `g = J * d` where `J = 1 - 3/(4*(n-2) - 1)`
- Effect variance: `v = (n_t + n_c)/(n_t * n_c) + d²/(2*(n_t + n_c))`

**🔍 Improvement Opportunities:**
- Add clustered SE adjustment
- Calculate partial eta-squared from F-statistics
- Add log-odds ratio conversions

---

## 📊 LLM Call Summary

| Stage | # Prompts | When Called | Cost Impact |
|-------|-----------|-------------|-------------|
| Metadata | 1 | Every study | Low |
| Classification | 1-2 | Every study (batch) | Medium |
| Prose/Figures | 2 | Only if tables fail | Low (fallback) |
| Sample Sizes | 1 | Only if not in tables | Low (fallback) |
| Enrichment | 3 | Every study | **High** |

**Total LLM Calls per Study:** 4-7 (depending on fallbacks)
**Model:** `anthropic/claude-3.5-haiku` via OpenRouter

---

## 🎯 Priority Improvement Areas

### High Impact (Accuracy)
1. ✅ **Few-shot classification examples** - Added 6 new edge cases to `classifier_v3.py`:
   - Spanish regression tables, French effect tables
   - Appendix heterogeneity tables, cost-effectiveness analysis
   - Attrition analysis, mechanism analysis
2. ✅ **Treatment arm normalization** - Added `normalize_treatment_arm()` in `standard.py`:
   - Maps T1/T2 to descriptive names from caption patterns
   - Supports multiple pattern formats (T1=Cash, T1: Cash, (T1) Cash)
   - Multi-language support (Spanish, French, Portuguese)
3. ✅ **Subgroup variable extraction** - Enhanced `classify_analysis_type()` prompt:
   - Added standardized vocabulary (gender, asset_quartile, region, etc.)
   - New fields: `is_robustness`, `estimand_type`
   - 8 example outputs in prompt for consistency

### Medium Impact (Coverage)
4. **Spanish/Portuguese prompts** - Translate enrichment prompts
5. **Figure understanding** - Add diagram/chart interpretation
6. **Merged cell handling** - Better table structure parsing

### Low Impact (Polish)
7. **Confidence scores** - Add to all classifications
8. **Caching optimization** - Share outcome classifications across studies
9. **Structured outputs** - Use JSON mode for all LLM calls

---

## Related Documentation

- [ROADMAP.md](../docs/ROADMAP.md) - Future plans for extraction pipeline
- [SETUP_TRACKER.md](../SETUP_TRACKER.md) - Current implementation status
- [schemas.py](../src/extraction/schemas.py) - Data schemas (RAG, SCREENING, FULL modes)
