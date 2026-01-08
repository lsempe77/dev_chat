# DevChat v2.0 - Setup & Progress Tracker

**Created:** December 17, 2025  
**Last Updated:** January 8, 2026  
**Status:** ✅ Production | ✅ Multi-Tenant | ✅ Hybrid Search | ✅ Contextual Retrieval

---

## 📊 Quick Status Dashboard

| Component | Status | Details |
|-----------|--------|---------|
| **Frontend (Vercel)** | ✅ Live | https://dev-chat-frontend.vercel.app/ |
| **Backend (Railway)** | ✅ Live | https://3iechat.up.railway.app |
| **PDF Processing (Modal)** | ✅ Working | MinerU + modular modal_lib + Contextual Retrieval |
| **Vector DB (Qdrant)** | ✅ Connected | Per-project collections with hybrid search |
| **Auth (Supabase)** | ✅ Working | JWT auth, RLS policies |
| **Multi-Tenant RAG** | ✅ Done | Users create/manage own projects |

---

## 🎯 Completed Features

### Core Platform
- [x] Multi-tenant RAG with Supabase auth
- [x] Per-user RAG projects with isolated Qdrant collections
- [x] Public RAG sharing via slugs
- [x] Document upload (drag-drop, batch, deduplication)
- [x] PDF processing pipeline (Modal + MinerU)

### Search & Retrieval
- [x] Hybrid search (dense + sparse vectors)
- [x] Cohere embed-v4 embeddings (1536 dims)
- [x] BM25-style sparse vectors
- [x] Cohere rerank-v3.5
- [x] Metadata filtering (year, country, sector)
- [x] **Contextual Retrieval** (Anthropic's 49% improvement) - Added Jan 8, 2026

### Metadata Pipeline
- [x] CrossRef/OpenAlex automatic enrichment
- [x] LLM gap-fill for domain fields
- [x] Metadata review UI with PDF viewer
- [x] Hallucination prevention (0.8 similarity threshold)
- [x] Item types (article, book, report, thesis, etc.)

### Citation Quality
- [x] Claim Ledger synthesis (grounded responses)
- [x] Page-aware chunking (256 words)
- [x] Clickable citations → PDF page
- [x] Post-hoc verification (NLI-based)
- [x] PDF citation highlighting (PyMuPDF yellow highlights)
- [x] Inline PDF viewer (replaces Evidence panel)

### Evaluation Framework
- [x] Test cases with ground truth (`evaluation/test_cases.json`)
- [x] RAGAS evaluator (faithfulness, answer relevancy)
- [x] MiniCheck evaluator (claim-level verification)
- [x] ReliableRAG evaluator (citation precision/recall)
- [x] Claim Ledger evaluation scripts
- [x] Post-hoc verification testing

### UI/UX
- [x] Dashboard with Documents/Metadata/Settings tabs
- [x] Side-by-side metadata editor with PDF viewer
- [x] "Mark as reviewed" checkbox
- [x] Compact panel layout when narrow
- [x] Chat history persistence (Supabase)
- [x] Chat history response caching (citations, studies, evidenceHealth)
- [x] Compare modal (side-by-side study comparison)
- [x] View PDF in citations (correct R2 paths)
- [x] Evidence snippet card with copy-to-clipboard

### Backend
- [x] Processing jobs tracking with progress
- [x] Admin authentication (API key + session)

---

## 📈 Citation Quality Metrics

| Metric | Score | Target | Status |
|--------|-------|--------|--------|
| **Faithfulness** | 0.699 | 0.70+ | Not good enough |
| **Citation Recall** | 1.000 | 0.70 | ✅ Perfect |
| **Citation Precision** | 1.000 | 0.70 | ✅ Perfect |
| **Overall Score** | 0.900 | N/A | ✅ Excellent |

See `archive/CITATION_IMPROVEMENT_PLAN.md` for full journey documentation.

---

## 🔧 Infrastructure

| Service | Provider | Notes |
|---------|----------|-------|
| Frontend | Vercel | Auto-deploy from GitHub |
| Backend | Railway | FastAPI, auto-deploy |
| Database | Supabase | PostgreSQL + Auth |
| Vectors | Qdrant Cloud | EU region |
| PDF Processing | Modal | T4 GPU, MinerU 2.6.8 |
| Storage | Cloudflare R2 | PDFs + outputs |
| Embeddings | Cohere | embed-v4 |
| LLM | OpenRouter | GPT-4o, GPT-4o-mini |
| Observability | Langfuse | Full tracing |

---

## 📁 Repository Structure

```
devchat_v2_sota/
├── api/                    # FastAPI backend routes
├── src/                    # Core Python libraries
├── frontend/               # Next.js app
├── infrastructure/         # Modal, Docker
│   ├── modal_mineru.py     # Entry point (~230 lines)
│   └── modal_lib/          # Modular pipeline (8 modules)
│       ├── config.py       # App, image, secrets
│       ├── extraction.py   # MinerU PDF extraction
│       ├── chunking.py     # Page-aware chunking
│       ├── embedding.py    # Dense + sparse vectors
│       ├── indexing.py     # Qdrant upsert
│       ├── metadata.py     # Enrichment pipeline
│       ├── processing.py   # Full orchestration
│       └── utils.py        # Logging, helpers
├── evaluation/             # Citation metrics & tests
├── scripts/                # Active utility scripts
│   └── archive/           # Old scripts (reference)
├── docs/                   # Documentation
├── archive/                # Historical files
├── README.md               # Main readme
├── SETUP_TRACKER.md        # This file
└── CHANGELOG.md            # Version history
```

---

## 🚧 TODO (Future)

### High Priority
- [x] Admin authentication (protect `/admin` routes) ✅ Done
- [x] Processing status WebSocket (real-time updates) ✅ Code ready (polling fallback works)
- [x] **Bibliography Import System** ✅ Phases 1-3 complete
- [x] **3ie Admin Panel** ✅ Phases 1-5 complete (Overview, Langfuse, Users & RAGs, Quality)
- [x] **Quality Monitoring** (Phase 5) ✅ Complete with baseline metrics
- [x] **Modal Pipeline Refactoring** ✅ Complete (modal_lib/ package, 8 modules, .spawn() for async)
- [] **Security** (https://medium.com/data-science-collective/5-ways-your-ai-agent-will-get-hacked-and-how-to-stop-each-one-f4069efba029)


### Medium Priority
- [x] **Study Design Classification** ✅ Complete
  - [x] StudyDesign enum with 22 types (RCT, DiD, qualitative, etc.)
  - [x] LLM classifier with Qdrant full-text fallback
  - [x] Batch classification script: `scripts/run_study_design_classification.py`
  - [x] Frontend badge component: `StudyDesignBadge.tsx`
  - [x] 96 documents classified (81 with design, 15 unknown)
  - [ ] Integrate into ingestion pipeline (auto-classify on ingest)
  - [ ] Add study design filter dropdown in Evidence panel
- [x] **Per-RAG Model Selection** ✅ Code Complete ⚠️ *Untested - needs SQL migration + end-to-end testing*
  - [x] Add `model_config` JSONB to `rag_projects` table (provider, model, reasoning_model, temperature)
  - [x] Settings tab UI: dropdown for provider (OpenAI, Claude, Gemini) + models
  - [x] Pass model config to DevChatAgent/ClaimLedgerSynthesizer at query time
  - [x] Backend endpoints: GET/PATCH `/rags/{id}/model-config`, GET `/rags/models/available`
  - [x] Cost tracking per model for accurate projections
  - [ ] **Deploy:** Run `scripts/migrations/002_model_config.sql` in Supabase
  - [ ] **Test:** Verify model switching works end-to-end
- [x] **Context Prompts & Prompt Customization** ✅ Partially Tested
  - [x] Add `context_prompt` field to `rag_projects` (domain instructions)
  - [x] Add `custom_prompts` JSONB for extraction/synthesis override
  - [x] Settings UI with textarea + warning alerts (collapsible advanced section)
  - [x] Pass context prompt and custom prompts to ClaimLedgerSynthesizer
  - [x] Prompt reset to defaults option
  - [x] Safety feature: `acknowledge_risk` required for custom prompt changes
  - [x] Backend endpoints: GET/PATCH/DELETE `/rags/{id}/prompts/*`
  - [x] **Deploy:** SQL columns exist in Supabase (`custom_prompts` JSONB)
  - [x] Prompts save/load correctly via API
  - [x] Prompt history feature added (max 10 versions with restore)
  - [ ] **Test:** Verify custom prompts affect synthesis output (needs query with relevant docs)
- [ ] Advanced search filters in chat
- [x] Export citations (CSV, JSON, BibTeX) ✅ Done

### Quality Improvements (Post Phase 5)
- [ ] Improve faithfulness (currently 66.47%) via prompt tuning in Langfuse
- [ ] Add user feedback tracking (👍/👎 on responses)
- [ ] Create A/B experiments for synthesis prompts
- [ ] Expand golden test suite (currently 8 queries)

### Feature Improvements (See FURTHER_IMPROVEMENTS.md)
- [x] PDF Citation Highlighting (4h) - PyMuPDF text highlighting ✅ Done
- [x] Study Design Classification (8h) - RCT vs quasi-exp vs observational ✅ Done
- [ ] **Document Enrichment Pipeline (58h)** - Structured extraction for quantitative queries:
  - [ ] Study Design Integration (2h) - Hook into Modal ingest pipeline
  - [ ] Geographic Extraction (4h) - Countries, regions, urban/rural
  - [ ] Intervention Extraction (6h) - Type, amount, duration, target population
  - [ ] Methods Extraction (6h) - Sample sizes, timeline, pre-registration
  - [ ] Effect Size Extraction (12h) - Parse result tables, validate ranges
  - [ ] Quantitative Query Agent (10h) - Filter/aggregate/compare structured data
  - [ ] Validation & Review UI (8h) - Confidence badges, human-in-the-loop
  - [ ] Frontend filters (10h) - Filter by design, country, intervention
- [ ] Smart Citations (12h) - Scite-style support/contrast classification
- [ ] Consensus Meter (16h) - Visual evidence agreement display
- [ ] Systematic Review Workflow (40h) - Elicit-style automation
- [ ] Research Reports (30h) - Auto-generated literature reviews

### RAG Techniques & Architecture
See **[FURTHER_IMPROVEMENTS.md](FURTHER_IMPROVEMENTS.md)** for comprehensive roadmap including:

| Status | Technique | Priority |
|--------|-----------|----------|
| ✅ Have | Hybrid Search (Dense + Sparse) | - |
| ✅ Have | Cohere Reranking | - |
| ✅ Have | Two-Pass Claim Ledger (ALCE) | - |
| ✅ Have | Post-Hoc MiniCheck Verification | - |
| 🔴 Gap | Contextual Retrieval (Anthropic) | High |
| 🔴 Gap | Parent-Child Chunking | High |
| 🔴 Gap | Contextual Summarization (RCS) | High |
| 🔴 Gap | Agentic RAG (Multi-Step) | High |
| 🟡 Future | RAPTOR, GraphRAG, Late Chunking | Low |

**Verdict:** 70% SOTA, missing 4 key innovations (~48h to implement)

---

## 🎛️ 3ie Admin Panel (Detailed Plan)

### Overview
A comprehensive admin dashboard for 3ie staff to monitor costs, usage, users, RAGs, and system health.

### Current State Analysis

| Component | Status | Notes |
|-----------|--------|-------|
| Admin auth | ✅ Done | Password + session tokens (in-memory) |
| Document management | ✅ Done | Upload, list, delete, metadata edit |
| Processing jobs | ✅ Done | View status, trigger processing |
| Service health | ✅ Done | R2, Qdrant, LLM, Cohere status |
| Metrics tracking | ✅ Done | Supabase `usage_logs` table |
| Cost tracking | ✅ Done | Per-model pricing, projections |
| Langfuse integration | ✅ Done | Full tracing in agents |
| User management | ✅ Done | Read-only view + Supabase link |
| Overview dashboard | ✅ Done | Stats, costs, quick links |

### Implementation Phases

#### Phase 1: Persistent Usage Metrics (Foundation) ✅ DONE
**Goal:** Never lose usage data, track costs accurately

- [x] Created `usage_logs` SQL migration: `scripts/migrations/001_usage_logs.sql`
  - Full table schema with RLS policies
  - Indexes for performance
  - `daily_usage_summary` and `user_usage_summary` views
- [x] Added cost config in `src/config/costs.py`:
  - `ModelPricing` dataclass with `calculate_cost()` method
  - Pricing for GPT-4o, GPT-4o-mini, embed-v4, rerank-v3.5
- [x] Created `UsageLogger` class in `src/utils/usage_logger.py`:
  - Async batch logging with configurable buffer size
  - Fallback to in-memory when DB unavailable
  - Convenience functions: `log_query()`, `log_llm_call()`, `log_embedding_call()`, etc.
- [x] Integrated logging in `src/agents/devchat_agent.py`:
  - Logs every query with tokens, latency, and metadata
  - Logs cache hits separately (zero cost)
- [x] Added admin usage endpoints in `api/routes/admin/usage.py`:
  - `GET /admin/usage/summary` - Period summary with daily/model breakdown
  - `GET /admin/usage/costs` - Cost projection (daily avg → monthly/annual)
  - `GET /admin/usage/pricing` - Current model pricing config
  - `POST /admin/usage/flush` - Force flush buffered events

**Status:** Complete - Run `scripts/migrations/001_usage_logs.sql` in Supabase to activate

**Effort:** ~4 hours

#### Phase 2: Langfuse Observability Integration ✅ DONE
**Goal:** Full tracing of LLM calls, prompt debugging, quality monitoring

- [x] Install Langfuse SDK: `pip install langfuse` (v3.5.0)
- [x] Create `src/utils/langfuse_client.py` with v3 SDK API:
  - `create_trace()` - manual trace creation for async code
  - `add_span_to_trace()` - retrieval/reranking spans
  - `add_generation_to_trace()` - LLM generation tracking
  - `@observe_llm` decorator for LLM calls
  - `@observe_embedding` decorator for embedding calls
  - `@observe_retrieval` decorator for retrieval calls
- [x] Add tracing to `DevChatAgent.chat()`:
  - Creates trace at start with query metadata
  - Logs retrieval span (count, hyde_used, latency)
  - Logs reranking span (in/out counts, threshold)
  - Logs synthesis generation (model, tokens, latency)
  - Updates trace with output and flushes on completion
- [x] Add Langfuse dashboard link to admin UI

#### Phase 3: Admin Overview Dashboard (UI) ✅ DONE
**Goal:** At-a-glance view of system health and costs

New tab: **Overview** (first tab in admin)

| Section | Metrics |
|---------|---------|
| **Today's Stats** | Queries, tokens, cost ($), active users |
| **This Month** | Same metrics, cumulative |
| **Top Users** | Top 5 by query count/cost |
| **Top RAGs** | Top 5 by query count/documents |
| **System Health** | Services status, processing queue |
| **Recent Activity** | Last 10 queries (user, RAG, cost) |

Components:
- [x] `OverviewTab.tsx` - main dashboard component with stats cards
- [x] `StatsCard` - reusable metric card (inline component)
- [x] `ModelUsageCard` - model breakdown with progress bars
- [x] `CostProjectionCard` - daily/monthly/annual projections
- [x] `AccessControlInfo` - explains admin auth system
- [ ] `UsageChart.tsx` - daily usage over time (recharts) - OPTIONAL
- [x] Frontend API functions in `admin-api/index.ts`:
  - `getUsageSummary()` - aggregate stats with daily/model breakdown
  - `getCostProjection()` - cost projections
  - `getModelPricing()` - current pricing config
  - `flushUsageBuffer()` - force flush events

**Status:** Complete - Overview tab now first tab in Admin panel

#### Phase 4: User & RAG Management ✅ DONE
**Goal:** View all users, their RAGs, usage, and take action

New tab: **Users & RAGs**

| Feature | Description |
|---------|-------------|
| User list | Email, created, last active, query count, cost |
| RAG list per user | Name, docs, chunks, status, last query |
| Usage details | Click user → see their usage history |
| Actions | Manage in Supabase dashboard (link provided) |

Components:
- [x] `UsersTab.tsx` - user list with stats and RAG projects
- [x] Read-only monitoring with "Manage in Supabase" link
- [x] Backend endpoints:
  - `GET /admin/users` - list all users with stats
  - `GET /admin/users/{id}` - user details with RAGs
  - `GET /admin/rags` - list all RAG projects

#### Phase 5: Prompt Quality & Debugging ✅ DONE
**Goal:** Monitor and improve answer quality

New tab: **Quality** (simplified - leverages Langfuse for deep analysis)

| Feature | Description |
|---------|-------------|
| Langfuse integration | Direct links to experiments, prompts, datasets |
| Golden test suite | 8 curated queries with expected answer patterns |
| Baseline experiment | `baseline-v1` run with MiniCheck evaluation |
| Experiment scripts | `setup_langfuse.py`, `run_langfuse_experiment.py` |

Components:
- [x] `QualityTab.tsx` - simplified dashboard linking to Langfuse features
- [x] `scripts/setup_langfuse.py` - creates dataset + prompts in Langfuse
- [x] `scripts/run_langfuse_experiment.py` - runs experiments with MiniCheck eval
- [x] `EVALUATION_FRAMEWORK.md` - documents dual-lane evaluation approach
- [x] Dataset `devchat-graduation-tests` with 8 golden queries
- [x] Prompts: `claim-extraction-v1`, `synthesis-v1`

**Baseline Metrics (baseline-v1):**
| Metric | Value |
|--------|-------|
| Faithfulness | 66.47% |
| Citation Recall | 98.86% |
| Citation Precision | 98.86% |
| Avg Latency | 12,193ms |

**Next Steps:**
- Improve faithfulness through prompt tuning in Langfuse
- Add user feedback tracking (👍/👎)
- Create A/B experiments for synthesis prompts

#### Phase 6: Cost Alerts & Quotas (Optional)
**Goal:** Prevent runaway costs

| Feature | Description |
|---------|-------------|
| Daily cost limit | Alert when daily spend exceeds threshold |
| Per-user quota | Limit queries/tokens per user per day |
| Email alerts | Notify admin when limits approached |
| Auto-throttle | Slow down/block when limits hit |


---

### Architecture Summary

```
Admin Panel Architecture
========================

Frontend (Next.js)
├── /admin
│   ├── Overview (Phase 3)
│   ├── Users & RAGs (Phase 4)
│   ├── Quality (Phase 5)
│   ├── Documents (existing)
│   ├── Processing (existing)
│   ├── Metadata (existing)
│   └── Settings (existing)

Backend (FastAPI)
├── /admin
│   ├── /stats/* (Phase 3)
│   ├── /users/* (Phase 4)
│   └── existing routes...

Database (Supabase)
├── usage_logs (Phase 1) - NEW
├── rag_projects
├── documents
├── processing_jobs
└── auth.users

Observability (Langfuse)
├── Traces (Phase 2)
├── Spans (per LLM call)
└── Scores (future feedback)
```

---

### Recommended Implementation Order

| Week | Phase | Deliverable |
|------|-------|-------------|
| 1 | Phase 1 | ✅ Persistent usage logging + costs |
| 1 | Phase 2 | ✅ Langfuse integration |
| 2 | Phase 3 | ✅ Admin Overview dashboard |
| 2 | Phase 4 | ✅ Users & RAGs management |
| 3 | Phase 5 | ✅ Quality monitoring + baseline (66.47% faithfulness) |
| Future | Phase 6 | Cost alerts & quotas |

**Total estimated effort:** ~22-30 hours
**Completed:** Phases 1-4 (~15 hours)

---

## 📚 Bibliography Import System (Detailed Plan)

### User Types & Workflows
| User Type | Has PDFs | Has Metadata | Ideal Route |
|-----------|----------|--------------|-------------|
| Zotero power user | In Zotero | In Zotero | Zotero sync |
| Researcher with files | Local folder | RIS/BibTeX | Upload + match |
| Systematic reviewer | Bulk PDFs | None | Auto-enrich |
| Evidence map team | Uploaded | Spreadsheet | CSV match |

### Implementation Phases

#### Phase 1: Matching Engine ✅ DONE
- [x] Matching service with multiple strategies:
  - [x] DOI matching (most reliable)
  - [x] Title fuzzy matching (>85% similarity)
  - [x] Author+Year combo
  - [x] Filename pattern (author_year.pdf)
- [x] Parse RIS/BibTeX files into structured data
- [x] Match confidence scoring (0.0-1.0)

#### Phase 2: Import UI + Manual Matching ✅ DONE
- [x] Import dialog with file upload (RIS/BibTeX/CSV)
- [x] Preview table with parsed entries
- [x] Auto-match against existing documents
- [x] Status display: ✅ Matched | ⚠️ Unmatched
- [x] Manual matching UI for unmatched items
- [ ] Options: skip, upload missing PDFs, create placeholder (future)

#### Phase 3: Zotero Integration ✅ DONE
- [x] Zotero API key connection (Settings tab UI)
- [x] Browse user's collections
- [x] Select collection to sync from
- [x] Fetch PDFs via Zotero API
- [x] Upload PDFs to R2 with metadata
- [x] Match existing docs by DOI/title

#### Phase 4: Smart Enrichment
- [ ] Extract DOI from PDF text during processing
- [ ] Auto-match imported bibliography to uploaded PDFs
- [ ] Suggest matches for review
- [ ] Ability to adapt prompts per RAG



## 📝 Recent Changes

### January 7, 2026
- **Modal Pipeline Refactoring** - Complete modular architecture:
  - Refactored monolithic `modal_mineru.py` (1700+ lines) into `modal_lib/` package (8 modules)
  - `config.py` - Modal app, image, secrets configuration
  - `extraction.py` - MinerU PDF extraction with GPU
  - `chunking.py` - Page-aware text chunking (256 words)
  - `embedding.py` - Cohere embed-v4 dense + BM25 sparse vectors
  - `indexing.py` - Qdrant upsert with hybrid vectors
  - `metadata.py` - CrossRef/OpenAlex enrichment + LLM gap-fill
  - `processing.py` - Full pipeline orchestration
  - `utils.py` - Logging, callbacks, helpers
  - Entry point `modal_mineru.py` now ~230 lines (87% reduction)
  - Successfully tested: 97/97 PDFs processed
- **Webhook Timeout Fix** - Background processing for Modal:
  - Changed `trigger_processing` from `.remote()` (blocking) to `.spawn()` (async)
  - Prevents Railway HTTP timeout (30-60s) from cancelling long jobs
  - Webhook returns immediately with `call_id` and `status: "processing"`
- **Stale Job Prevention** - Auto-cleanup mechanism:
  - Backend: Jobs running > 30 minutes auto-marked as `failed` in `list_project_jobs`
  - Frontend: `RagProcessingTab` now prefers most recent job (not just any "running" job)
  - Fixes UI getting stuck on stale "Processing X/Y" display
- **Bug Fixes:**
  - Fixed `project.qdrant_collection` → `project.get("qdrant_collection")` (dict access error)
  - Fixed Modal container import: added `.add_local_python_source("modal_lib")` to base_image
  - Added `timedelta` import to rags.py for stale job cleanup

- **Study Design Classification** - Complete implementation:
  - Created `StudyDesign` enum with 22 comprehensive types in `src/config/study_designs.py`
  - Built LLM classifier service in `src/ingestion/study_design_classifier.py`
  - Added Qdrant full-text fallback for documents without abstracts
  - Batch script `scripts/run_study_design_classification.py` with `--force` flag
  - Frontend `StudyDesignBadge.tsx` component with color-coded badges
  - Classified 96 documents: 34 RCT, 10 DiD, 7 qualitative, 6 theory, etc. (15 unknown)
  - Integrated into ingestion pipeline for auto-classification on new documents

### January 6, 2026 (Late Evening)
- **PDF Citation Highlighting** - Complete implementation:
  - PyMuPDF endpoint: `/rags/{id}/documents/{doc_id}/pdf-highlighted`
  - Inline PDF viewer replaces Evidence panel (toggle button to switch)
  - Full Qdrant chunk text (1500 chars) used for highlighting
  - Overlapping 6-word groups for better PDF text matching
  - Evidence snippet card with page number and copy button
  - Document lookup by study_id pattern (not just UUID)
  - Public RAG support without authentication
- **Chat History Caching Fix** - Citations now robustly cached:
  - `responseData` (citations, studies, evidenceHealth) saved to Supabase
  - Auto re-runs search if cache missing (ensures blue citation bubbles)
  - Delete endpoint fixed with logging

### January 6, 2026 (Evening)
- **Prompt Customization Testing** - Multiple bugs fixed during end-to-end testing:
  - **Bug 1:** Wrong import path in `api/routes/api.py` (`src.database.supabase_client` → `src.auth`)
  - **Bug 2:** Frontend sending wrong payload structure (nested `custom_prompts` → flat `extraction`/`synthesis`)
  - **Bug 3:** Frontend using `ragId` slug instead of `project.id` UUID for API calls
  - **Bug 4:** Default prompts in API didn't match actual prompts in `claim_ledger.py`
- **Prompt History Feature** - Added version history with restore:
  - Backend: `PromptHistoryEntry` model, history stored in JSONB (max 10 versions)
  - Frontend: Expandable history list with timestamps and restore button
  - API returns `history` array in `PromptConfigResponse`
- **Placeholder Documentation** - API now returns placeholder docs for prompts:
  - `EXTRACTION_PLACEHOLDERS`: `{chunk_text}`, `{metadata}`
  - `SYNTHESIS_PLACEHOLDERS`: `{query}`, `{claims}`, `{metadata_context}`, `{context_prompt}`
- **Verified Working:**
  - ✅ Prompts save to Supabase correctly
  - ✅ Prompts load at query time (logs: `Using project prompt config: custom=True`)
  - ✅ Prompt history saves and displays correctly
  - ⏳ Synthesis output not tested (query returned no relevant docs due to threshold)

### January 6, 2026 (Morning)
- **Context Prompts & Prompt Customization** - Code Complete
  - SQL migration `003_prompt_config.sql` ready (columns already exist in Supabase)
  - Backend: 5 new endpoints for prompt config (GET/PATCH/DELETE)
  - ClaimLedgerSynthesizer: accepts `prompt_config` with context/custom prompts
  - Frontend: Prompt Customization card in Settings tab
  - Safety: `acknowledge_risk` checkbox required for custom prompts
- **Per-RAG Model Selection** - Previously complete ⚠️ *UNTESTED*
- **TypeScript fixes** - Fixed type errors in RagSettingsTab.tsx
- **Backend tests passing** - All 43 pytest tests pass

### 🧪 TEST STATUS

#### Prompt Customization
| Test | Status | Notes |
|------|--------|-------|
| Settings UI shows prompts | ✅ Pass | Extraction & synthesis prompts display |
| Save prompts to Supabase | ✅ Pass | PATCH endpoint works |
| Load prompts at query time | ✅ Pass | Logs show `custom=True` |
| Prompt history saves | ✅ Pass | Max 10 versions stored |
| Prompt history restore | ✅ Pass | UI shows restore button |
| Custom prompt affects output | ⏳ Pending | Need query with relevant docs |
| Reset to defaults | ⏳ Pending | Not yet tested |

#### Per-RAG Model Selection
| Test | Status | Notes |
|------|--------|-------|
| Settings tab dropdowns | ⏳ Pending | Not tested |
| Save model config | ⏳ Pending | Not tested |
| Query uses selected model | ⏳ Pending | Not tested |

### January 5, 2026
- **Admin Panel Phase 4 Complete** - Users & RAGs tab working
  - Backend: `/admin/users` endpoint with Supabase auth integration
  - Fixed datetime serialization (Pydantic validation)
  - Added "Manage in Supabase" link for user management
  - Quick Links section with Langfuse, Railway, Modal
- **Zotero Sync Bug Fix** - Fixed early pagination termination
  - **Problem:** Sync would stop after batch 1 when all items in batch were already synced (skipped)
  - **Root Cause:** Backend wasn't returning `items_skipped` count, so frontend early-exit condition triggered incorrectly
  - **Fix:** Added `items_skipped` field to `ZoteroSyncResponse` (backend) and updated sync loop condition (frontend)
  - **Commits:** `184e50c` (items_skipped fix), plus manual insertion of 22 missing items
  - **Result:** Collection now has 188 documents (was stuck at 166)
- **Project Cleanup** - Organized scripts and documentation

### January 3, 2026
- **Bibliography Import System** - Phase 1 (backend) + Phase 2 (UI) complete
  - RIS/BibTeX/CSV parser with auto-format detection
  - Multi-strategy matching (DOI, title, author+year, filename)
  - Import dialog with drag-drop, preview table, manual matching
- Added sparse vector support to Modal indexing
- Fixed Qdrant collection name mismatch bug
- Added "Mark as reviewed" checkbox in metadata editor
- Made metadata panel compact when narrow
- Organized repository (archive old files)

### January 2, 2026
- Fixed metadata hallucination (0.8 similarity threshold)
- Backend pagination for large document lists
- Fixed flexbox scroll issues in metadata panel

### December 28, 2025
- Citation quality reached target (Faithfulness 0.699)
- Hybrid BM25+Dense search deployed
- Contextual retrieval with document prefixes

See `CHANGELOG.md` for complete history.

---

## 🔗 Links

- **Production:** https://dev-chat-frontend.vercel.app/
- **API Health:** https://3iechat.up.railway.app/health
- **Repository:** https://github.com/lsempe77/dev_chat
- **Modal App:** https://modal.com/apps/3ieimpact/main/deployed/devchat-mineru
- **Roadmap:** [FURTHER_IMPROVEMENTS.md](FURTHER_IMPROVEMENTS.md) - RAG techniques audit & competitive analysis
