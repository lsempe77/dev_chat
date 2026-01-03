# DevChat v2.0 - Setup & Progress Tracker

**Created:** December 17, 2025  
**Last Updated:** January 3, 2026  
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
- [ ] **Bibliography Import System** (see detailed plan below)
- [ ] General 3ie admin panel (costs, metrics, users/rags, prompts quality, observability)

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


## 📝 Recent Changes

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
