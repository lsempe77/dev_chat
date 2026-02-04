# DevChat v2.0 - Setup & Status Tracker

**Last Updated:** February 2, 2026

> This document tracks **current implementation status** and configurations.  
> For future features, see [docs/ROADMAP.md](docs/ROADMAP.md).

---

## 📊 Current Status

### Infrastructure

| Component | Status | Details |
| --------- | ------ | ------- |
| Frontend (Vercel) | ✅ Live | <https://dev-chat-frontend.vercel.app/> |
| Backend (Railway) | ✅ Live | <https://3iechat.up.railway.app> |
| PDF Processing (Modal) | ✅ Working | MineRU + modal_lib + Contextual Retrieval |
| Vector DB (Qdrant) | ✅ Connected | chunks, hybrid search, binary quantization |
| Auth (Supabase) | ✅ Working | JWT auth, RLS policies |
| Storage (R2) | ✅ Working | Cloudflare R2 for PDFs |
| Observability (Langfuse) | ✅ Working | Full tracing |

### MinerU Post-Processing (NEW)

| Step | Status | Description |
|------|--------|-------------|
| 0.1 Empty Filter | ✅ Done | Remove tables with no body content |
| 0.2 Figure Detection | ✅ Done | Detect figures misclassified as tables |
| 0.3 Diagram Detection | ✅ Done | Detect single-row diagrams/legends |
| 0.4 Text Fragment | ✅ Done | Detect text fragments parsed as tables |
| 0.5 Split Merge | ✅ Done | Merge tables split across pages |
| 0.6 Header Graft | ✅ Done | Match orphan headers to body tables |
| 0.7 LLM Verify | ⚠️ Optional | LLM verification for edge cases |
| **0.8 LOT Cross-Ref** | ✅ Done | Use "List of Tables" for caption repair |

**Test Results (122182713):** 52 raw → 45 clean tables, 9 captions repaired

> Full docs: [docs/MINERU_POSTPROCESSING_PLAN.md](docs/MINERU_POSTPROCESSING_PLAN.md)

### Core Features

| Feature | Status | Notes |
| ------- | ------ | ----- |
| Multi-tenant RAG | ✅ Done | Users create/manage own projects |
| Document Upload | ✅ Done | Drag-drop, batch, deduplication |
| Hybrid Search | ✅ Done | Cohere embed-v4 + BM25 sparse |
| **Binary Quantization** | ✅ Done | Qdrant native BinaryQuantization, ~32x faster search |
| **HNSW Tuning** | ✅ Done | m=16, ef_construct=200 for better recall |
| **MMR Diversity** | ✅ Done | Maximal Marginal Relevance, lambda=0.7 |
| **Lost-in-Middle** | ✅ Done | Reorder chunks [1,3,5,7,8,6,4,2] pattern |
| **Multi-Query RAG-Fusion** | ✅ Done | 3 query variants + RRF fusion, +10-15% recall |
| **Embedding Cache** | ✅ Done | MD5 hash cache, 50-80% cost reduction |
| **Retrieval Metrics** | ✅ Done | Recall@K, NDCG, MRR logged to Langfuse |
| **Semantic Cache** | ✅ Done | Similar query matching (>0.95 cosine), reduces LLM calls |
| **Query Decomposition** | ✅ Done | Complex queries split into sub-queries, merged via RRF |
| **Step-Back Prompting** | ✅ Done | Specific questions get broader context query first |
| **Scalar Quantization** | ✅ Done | Configurable: binary (32x), scalar/int8 (4x), or none |

#### Quantization Options Reference

| Setting | Compression | Precision | Speed | When to Use |
|---------|-------------|-----------|-------|-------------|
| `binary` | ~32x | Good | Fastest | **Default** - Cohere embed-v4 is optimized for this |
| `scalar` | ~4x | Better | Fast | When precision is critical (medical/legal data) |
| `none` | 1x | Full | Slower | Small collections, maximum accuracy needed |

**To change:** Set `QDRANT_QUANTIZATION_TYPE=scalar` in `.env`, then delete collection and re-index.

| Reranking | ✅ Done | Cohere rerank-v3.5 |
| Claim Ledger Synthesis | ✅ Done | Two-pass extraction with citations |
| MiniCheck Verification | ✅ Done | Post-hoc NLI grounding |
| PDF Citation Highlighting | ✅ Done | PyMuPDF with page numbers |
| Contextual Retrieval | ✅ Done | Claude mentions 49% fewer retrieval failures |
| Parent-Child Chunking | ✅ Done | Small chunks search, parent context |
| Study Design Classification | ✅ Done | 22 types |
| Chat History | ✅ Done | Persistent with response caching |
| Zotero Integration | ✅ Done | Sync collections, import PDFs |
| Bibliography Import | ✅ Done | RIS/BibTeX/CSV with matching |
| Tutorial Series | ✅ Posts 1-10 | 50-part learning path in `tutorials/` |
| | 🚧 Posts 11-50 | Document processing, RAG, synthesis, production |

### Admin Panel

| Tab | Status | Features |
| --- | ------ | -------- |
| Overview | ✅ Done | Stats, costs, projections |
| Users & RAGs | ✅ Done | User list, RAG projects |
| Quality | ✅ Done | Langfuse integration, baseline metrics |
| Documents | ✅ Done | Upload, list, delete |
| Processing | ✅ Done | Job status, trigger processing |
| Metadata | ✅ Done | Edit metadata with PDF viewer |

### Per-RAG Settings

| Feature | Status | Notes |
| ------- | ------ | ----- |
| Model Selection | ✅ Done | Per-RAG model selection working |
| Context Prompts | ✅ Done | Domain instructions per RAG |
| Custom Prompts | ✅ Done | Override extraction/synthesis |
| Prompt History | ✅ Done | Max 10 versions with restore |

### Extraction Pipeline

> **Active:** `extraction_pipeline/pipeline.py` (monolith), `extraction_pipeline/cli_v2.py` (modular CLI)  
> **Modular Core:** `extraction_pipeline/core/`, `extraction_pipeline/adapters/`, `extraction_pipeline/postprocessing/`  
> **Archived:** All v1-v17 and extractor.py variants in `archive/extraction_pipeline_old/`  
> **Full docs:** See [extraction_pipeline/README.md](extraction_pipeline/README.md)

| Pipeline | Status | Performance | Notes |
| -------- | ------ | ----------- | ----- |
| **V2 SOTA** (production) | ✅ Active | 100% coefficient coverage, 42 columns | Hybrid rules + LLM, 9-stage process |
| **Modular Refactor** | ✅ Done | Same performance, better maintainability | See "Modular Architecture" below |
| V11 (bulk, archived) | ⚠️ Deprecated | 71.3% recall, 43 studies | Superseded by V2 SOTA |

#### Modular Architecture (January 2026)

Refactored from monolithic `pipeline.py` into composable modules:

| Module | Location | Purpose |
| ------ | -------- | ------- |
| **Core** | `extraction_pipeline/core/` | Infrastructure: errors, LLM client, storage, config |
| **Adapters** | `extraction_pipeline/adapters/` | Schema conversion (DataFrame ↔ Pydantic) |
| **Postprocessing** | `extraction_pipeline/postprocessing/` | Effect sizes, outcome classification |

**Key Improvements:**

| Area | Before | After |
| ---- | ------ | ----- |
| Error handling | `print()` + silent failures | Structured `ErrorAccumulator` with stage context |
| LLM responses | Ad-hoc JSON parsing | Centralized `sanitize_llm_response()`, `parse_llm_json()` |
| Schema mapping | Inconsistent field names | `ColumnNames` constants, `normalize_authors()` |
| Effect sizes | Implicit assumptions | Explicit `effect_size_assumption` column |
| LLM costs | Repeated calls | File-based cache with `get_prompt_hash()` |
| CLI | Basic flags | Comprehensive `--no-prose`, `--no-figures`, `--fast`, `--minimal` |

**New CLI Usage:**
```bash
# Single study extraction
python -m extraction_pipeline.cli_v2 --study_id 121058356

# Fast mode (no LLM)
python -m extraction_pipeline.cli_v2 --study_id 121058356 --fast

# List studies in default project
python -m extraction_pipeline.cli_v2 --list

# List all RAG projects with documents
python -m extraction_pipeline.cli_v2 --list-projects

# Extract ALL studies in a project (batch mode)
python -m extraction_pipeline.cli_v2 --all

# Extract from a specific project
python -m extraction_pipeline.cli_v2 --all --project-id abc123-def456

# Tables only, no fallbacks
python -m extraction_pipeline.cli_v2 --study_id 121058356 --no-prose --no-figures

# Minimal mode (basic parsing only)
python -m extraction_pipeline.cli_v2 --study_id 121058356 --minimal

# Clear LLM cache
python -m extraction_pipeline.cli_v2 --study_id 121058356 --clear-cache
```

**Multi-Tenant Support:**
- Each RAG project has its own document corpus at `rags/{project_id}/outputs/json/`
- Default project: `0816e8d3-ab23-417c-bf3f-e45531411c73` (graduation corpus, 97 documents)
- Use `--project-id` to target different projects
- Batch extraction with `--all` saves manifest CSV per project

### Document Registry (R2 Management)

> **Location:** `extraction_pipeline/document_registry.py`, `extraction_pipeline/r2_utils.py`  
> **Audit Tool:** `scripts/audit_r2_documents.py`

| Feature | Status | Notes |
| ------- | ------ | ----- |
| Document Inventory | ✅ Done | 97 files → 91 unique studies |
| Variant Detection | ✅ Done | Appendix, translation, supplement parsing |
| Content Deduplication | ✅ Done | Hash-based duplicate detection |
| Metadata Extraction | ✅ Done | Study ID, doc type, language from filenames |
| Audit CLI | ✅ Done | `--scan`, `--report`, `--export` commands |

**Document Types:**
| Type | Count | Detection |
|------|-------|-----------|
| Main | 88 | Default if no variant suffix |
| Appendix | 9 | `_app`, `_appendix`, `_supp` in filename |
| Translation | 2 | `_Spanish`, `_es`, `_English` in filename |

**Multi-Variant Studies (6):**
| Study | Variants | Type |
|-------|----------|------|
| 121058369 | 2 | Main + Appendix |
| 121058373 | 2 | Main + Appendix |
| 121354848 | 2 | Main + Appendix |
| 121498842 | 2 | Spanish + English |
| 122182711 | 2 | Spanish + English |
| BRAC_Ahmed_2009 | 2 | Two different papers |

**Usage:**
```bash
# List documents with variant info
python extraction_pipeline/r2_utils.py

# Full audit with dedup analysis
python scripts/audit_r2_documents.py --scan --report

# Export extraction manifest
python scripts/audit_r2_documents.py --export manifest.csv
```

**Pipeline Architecture (7 Stages):**
| Stage | Method | Purpose |
|-------|--------|--------|
| 1. Metadata | Rules + LLM | Extract title, authors, year, country, study_design |
| 2. Table Filter | Rules + regex | Filter results tables using BeautifulSoup |
| 3. Classification | Rules → LLM | Classify ambiguous tables |
| 4. Parsing | Regex + LLM | Extract coefficient, SE, CI, t-stat, N from cells |
| 5. Significance | Rules → LLM | Parse stars, symbols, p-values (`SignificanceParser`) |
| 6. Enrichment | LLM | Add outcome definitions, categories |
| 7. Analysis Types | LLM reasoning | Classify main effect / subgroup / spillover / mechanism |

**Recent Milestones (January 29, 2026):**
- ✅ **Pilot V4 Complete:** 51/54 studies (94%), 10,698 quality rows
- ✅ P3: SE-split parser (handles SE in separate rows + European number format)
- ✅ P2: Transposed table detection (outcomes-in-rows format)
- ✅ P1: Suspicious row filter (removed ~800 noise rows)
- ✅ Treatments-in-columns parser (treatment groups as column headers)
- ✅ Full QEX parity: 30/30 extractable fields
- ✅ Full OM parity: Analysis type classification (Stage 7)
- ✅ 42 total output columns
- ✅ Effect size calculation: Cohen's d, Hedges' g, variance
- ✅ LLM-based outcome categorization
- ✅ Prose fallback for sample sizes

**Pilot Results (54 studies):**
| Metric | V1 | V2 | V3 | V4 (current) | Change |
|--------|-----|-----|-----|--------------|--------|
| Studies with data | 18 (33%) | 39 (72%) | 48 (89%) | **51 (94%)** | +183% |
| Quality rows | 4,197 | 5,536 | 3,351 | **10,698** | +155% |
| Zero-extraction | 36 (67%) | 15 (28%) | 6 (11%) | **3 (6%)** | -92% |

**Table Orientation Parsers:**
| Parser | Format | Example |
|--------|--------|---------|
| Standard | Treatments in rows, outcomes in columns | Most common |
| Transposed | Outcomes in rows, stats (effect, SE, p) in columns | Effect/SE/pval headers |
| Treatments-in-cols | Outcomes in rows, treatment groups in columns | Group 1/Group 2 headers |
| SE-split | Coefficients in one row, SE in next row | European format tables |

**Remaining Zero-Row Studies (3):**
| Cause | Count | Notes |
|-------|-------|-------|
| MineRU parsing (0 tables) | 1 | Re-process PDF |
| Policy brief (no results) | 1 | Only 1 table, descriptive |
| Spanish language | 1 | Not yet supported |

### Extraction Schema

> **Location:** `src/extraction/schemas.py` (Pydantic schemas), `src/extraction/significance.py` (significance parser)
> 
> **✅ Full QEX + OM Parity:** 42 columns extracted

| Component | Description | Fields |
| --------- | ----------- | ------ |
| `CoreNumericFields` | Effect size, SE, CI, p-value, N | 22 fields |
| `StudyMetadata` | Authors, year, country, design | 11 fields |
| `OutcomeMetadata` | Outcome name, domain, type, unit | 7 fields |
| `InterventionMetadata` | Name, type, control, duration | 8 fields |
| `SourceLocation` | Page, table, row, column | 8 fields |
| `StandardizedEffectSize` | Cohen's d, Hedges' g (calculated) | 9 fields |
| `AnalysisTypeFields` | Main effect, subgroup, spillover, mechanism | 7 fields |
| `DomainSpecificFields` | Custom fields per topic | Flexible |
| **`SignificanceParser`** | Stars, symbols, p-values → mapped | Hybrid rules + LLM |
| **`row_to_extracted_estimate()`** | Convert pipeline dict → ExtractedEstimate | Utility function |

**Pipeline Output Fields (42 columns):**
| Category | Fields |
|----------|--------|
| Identifiers | `study_id`, `table_number`, `page_number` |
| Paper Metadata | `authors`, `year`, `country`, `study_design`, `is_experimental`, `follow_up_months`, `intervention_name` |
| Table Context | `table_caption`, `section`, `treatment_arm` |
| Outcome | `outcome_name`, `outcome_category`, `outcome_definition` |
| Core Numeric | `coefficient`, `standard_error`, `significance`, `p_value`, `p_value_text` |
| CI Bounds | `ci_lower`, `ci_upper` |
| Sample Sizes | `sample_size`, `n_treatment`, `n_control`, `n_clusters` |
| Control Stats | `control_mean`, `control_sd` |
| Effect Sizes | `cohens_d`, `hedges_g`, `effect_variance`, `effect_se` |
| Analysis Types | `is_main_effect`, `is_subgroup`, `subgroup_variable`, `is_spillover`, `spillover_type`, `is_cost_outcome`, `is_mechanism` |
| Debug | `literal_cell_text`, `t_statistic` |

**Field Coverage (Study 121058356 - Niger Graduation):**
| Field | Coverage | Notes |
|-------|----------|-------|
| coefficient, SE, authors, year, country, study_design | 100% | Paper-level fields |
| p_value | 63% | Significance stars mapped |
| sample_size | 85% | From Observations rows |
| control_mean, control_sd | 81-94% | From table footer |
| cohens_d | 90% | Calculated where SD available |
| hedges_g | 52% | Needs N treatment/control |
| outcome_category | 66% | LLM classification |
| ci_lower, ci_upper | 0% | Study doesn't report CI (parser ready) |

**Domain Configs Available:** graduation, education, health, agriculture, aquaculture, WASH, nutrition, social_protection, generic

**Extraction Modes:**
- `RAG` - 11 key fields for chat synthesis
- `SCREENING` - 7 fields for title/abstract
- `FULL` - All fields for systematic review




### Quality Metrics (Baseline)

| Metric | Score | Target |
| ------ | ----- | ------ |
| Faithfulness | 66.47% | 70%+ |
| Citation Recall | 98.86% | 70%+ ✅ |
| Citation Precision | 98.86% | 70%+ ✅ |
| Avg Latency | 12,193ms | - |

---

## Sphinx Documentation - PENDING

Sphinx autodoc setup is complete in `docs/sphinx/`. 

### To Enable GitHub Pages (requires GitHub Pro for private repos):

1. **Upgrade to GitHub Pro** (private repo requirement)
   - Go to: https://github.com/settings/billing/plans

2. **Enable GitHub Pages**
   - Go to: Settings → Pages
   - Source: Select "GitHub Actions"
   - The workflow `.github/workflows/docs.yml` will auto-deploy on push

3. **Access docs at:** `https://lsempe77.github.io/dev_chat/`

### Build Locally:
```bash
cd docs/sphinx
sphinx-build -b html source build/html
# Open build/html/index.html
```

### What's Documented:
- `src/` - Core library (agents, generation, retrieval, ingestion)
- `api/` - FastAPI routes and schemas
- `extraction_pipeline/` - Table extraction
- `infrastructure/` - Modal deployment
- `evaluation/` - Test and validation scripts
- `scripts/` - Utility scripts

---

## 📁 Repository Structure

```text
devchat_v2_sota/
├── api/                    # FastAPI backend
│   └── routes/             # API endpoints
├── src/                    # Core Python libraries
│   ├── agents/             # DevChatAgent
│   ├── generation/         # ClaimLedgerSynthesizer
│   ├── ingestion/          # Chunking, study design
│   ├── extraction/         # Schemas + SignificanceParser
│   └── config/             # Study designs, costs
├── frontend/               # Next.js app
│   └── src/components/     # React components
├── infrastructure/         
│   ├── modal_mineru.py     # Entry point (~230 lines)
│   └── modal_lib/          # 8 modules (chunking, embedding, etc.)
├── extraction_pipeline/    # ✅ ACTIVE: Treatment effect extraction
│   ├── pipeline.py         # Production script (hybrid rules + LLM)
│   └── outputs/            # Extracted data per study
├── evaluation/             # RAGAS, MiniCheck, test cases
├── scripts/                # Utility scripts
├── docs/                   # ROADMAP.md, EVALUATION.md
└── archive/                # ⚠️ Deprecated code (DO NOT USE)
    └── extraction_pipeline_old/  # 35+ old extraction scripts (v1-v17)
```

---

## 🔧 Key Configurations

### Environment Variables

```text
SUPABASE_URL, SUPABASE_SERVICE_KEY
QDRANT_URL, QDRANT_API_KEY
OPENROUTER_API_KEY
COHERE_API_KEY
CLOUDFLARE_R2_* (access key, secret, bucket, URL)
LANGFUSE_* (host, public/secret key)
```

### SQL Migrations

| Migration | Status | Purpose |
| --------- | ------ | ------- |
| 001_usage_logs.sql | ✅ Applied | Usage tracking |
| 002_model_config.sql | ✅ Applied | Per-RAG model selection |
| 002_evaluation_runs.sql | ✅ Applied | Langfuse evaluation tracking |
| 003_prompt_config.sql | ✅ Applied | Custom prompts |

---

## 📚 Documentation

| Document | Purpose |
| -------- | ------- |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Future features + priorities |
| [docs/EVALUATION.md](docs/EVALUATION.md) | Evaluation framework |
| [docs/EXTRACTION.md](docs/EXTRACTION.md) | Data extraction validation |
| [extraction_pipeline/README.md](extraction_pipeline/README.md) | Table extraction pipeline |
| [infrastructure/README.md](infrastructure/README.md) | Infrastructure setup guide |
| CHANGELOG.md | Version history |

---

## 🔗 Links

| Resource | URL |
| -------- | --- |
| Production | <https://dev-chat-frontend.vercel.app/> |
| API Health | <https://3iechat.up.railway.app/health> |
| Modal App | <https://modal.com/apps/3ieimpact/main/deployed/devchat-mineru> |
| Langfuse | <https://cloud.langfuse.com/> |
| Supabase | <https://supabase.com/dashboard> |

