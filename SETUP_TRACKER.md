# DevChat v2.0 - Setup & Progress Tracker

**Created:** December 17, 2025  
**Last Updated:** January 5, 2026  
**Status:** ✅ Production | ✅ Multi-Tenant | ✅ Hybrid Search | ✅ Sparse Vectors

---

## 📊 Quick Status Dashboard

| Component | Status | Details |
|-----------|--------|---------|
| **Frontend (Vercel)** | ✅ Live | https://dev-chat-frontend.vercel.app/ |
| **Backend (Railway)** | ✅ Live | https://3iechat.up.railway.app |
| **PDF Processing (Modal)** | ✅ Working | MinerU + dense/sparse indexing |
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
- [x] Compare modal (side-by-side study comparison)
- [x] View PDF in citations (correct R2 paths)

### Backend
- [x] Processing jobs tracking with progress
- [x] Admin authentication (API key + session)

---

## 📈 Citation Quality Metrics

| Metric | Score | Target | Status |
|--------|-------|--------|--------|
| **Faithfulness** | 0.699 | 0.70+ | ✅ At Target |
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
- [ ] **3ie Admin Panel** (see detailed plan below) 🚀 NEXT

### Waiting on External
- [ ] Enable Supabase Realtime when beta access granted (run SQL: `ALTER PUBLICATION supabase_realtime ADD TABLE processing_jobs, documents;`)

### Medium Priority
- [ ] Advanced search filters in chat
- [x] Export citations (CSV, JSON, BibTeX) ✅ Done

### Future Exploration
- [ ] RAPTOR hierarchical summarization
- [ ] GraphRAG for complex relationships
- [ ] ColBERTv2 for better retrieval

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
| Metrics tracking | ⚠️ Partial | In-memory only, lost on restart |
| Cost tracking | ❌ Missing | No $$ calculation |
| Langfuse integration | ❌ Missing | Config exists, not wired up |
| User management | ❌ Missing | No UI to view users/RAGs |
| Overview dashboard | ❌ Missing | No aggregate stats view |

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

#### Phase 2: Langfuse Observability Integration
**Goal:** Full tracing of LLM calls, prompt debugging, quality monitoring

- [ ] Install Langfuse SDK: `pip install langfuse`
- [ ] Initialize Langfuse client in `src/config/settings.py`
- [ ] Add `@observe` decorator to key functions:
  - `query_with_claim_ledger()` - main synthesis
  - `embed_texts()` - embedding calls
  - `rerank()` - reranking calls
  - `enrich_metadata()` - metadata LLM calls
- [ ] Pass trace IDs through the call stack
- [ ] Add Langfuse dashboard link to admin UI

**Effort:** ~3 hours

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

**Effort:** ~4 hours

#### Phase 4: User & RAG Management
**Goal:** View all users, their RAGs, usage, and take action

New tab: **Users & RAGs**

| Feature | Description |
|---------|-------------|
| User list | Email, created, last active, query count, cost |
| RAG list per user | Name, docs, chunks, status, last query |
| Usage details | Click user → see their usage history |
| Actions | Disable user, delete RAG (soft), export data |

Components:
- [ ] `AdminUsers.tsx` - user list with expandable rows
- [ ] `UserDetail.tsx` - modal with user details + RAGs
- [ ] Backend endpoints:
  - `GET /admin/users` - list all users with stats
  - `GET /admin/users/{id}/rags` - user's RAG projects
  - `GET /admin/users/{id}/usage` - user's usage logs
  - `POST /admin/users/{id}/disable` - disable user

**Effort:** ~5 hours

#### Phase 5: Prompt Quality & Debugging
**Goal:** Monitor and improve answer quality

New tab: **Quality** (or integrate with Langfuse)

| Feature | Description |
|---------|-------------|
| Recent queries | Question, answer, sources, latency |
| Feedback tracking | User 👍/👎 on answers (future) |
| Langfuse link | Direct link to trace for each query |
| Prompt templates | View/edit system prompts |
| A/B testing | Compare prompt versions (future) |

Initial scope:
- [ ] Link to Langfuse dashboard for detailed traces
- [ ] Show recent queries with expandable details
- [ ] Display query → answer → sources chain
- [ ] Add prompt template viewer (read-only for now)

**Effort:** ~4 hours (basic), ~8 hours (full)

#### Phase 6: Cost Alerts & Quotas (Optional)
**Goal:** Prevent runaway costs

| Feature | Description |
|---------|-------------|
| Daily cost limit | Alert when daily spend exceeds threshold |
| Per-user quota | Limit queries/tokens per user per day |
| Email alerts | Notify admin when limits approached |
| Auto-throttle | Slow down/block when limits hit |

**Effort:** ~6 hours

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
| 1 | Phase 1 | Persistent usage logging + costs |
| 1 | Phase 2 | Langfuse integration |
| 2 | Phase 3 | Admin Overview dashboard |
| 2 | Phase 4 | Users & RAGs management |
| 3 | Phase 5 | Quality monitoring |
| Future | Phase 6 | Cost alerts & quotas |

**Total estimated effort:** ~22-30 hours

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

### January 5, 2026
- **Zotero Sync Bug Fix** - Fixed early pagination termination
  - **Problem:** Sync would stop after batch 1 when all items in batch were already synced (skipped)
  - **Root Cause:** Backend wasn't returning `items_skipped` count, so frontend early-exit condition triggered incorrectly
  - **Fix:** Added `items_skipped` field to `ZoteroSyncResponse` (backend) and updated sync loop condition (frontend)
  - **Commits:** `184e50c` (items_skipped fix), plus manual insertion of 22 missing items
  - **Result:** Collection now has 188 documents (was stuck at 166)

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
- **Modal App:** https://modal.com/apps/lsempe77/main/deployed/devchat-mineru
