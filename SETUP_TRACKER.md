# DevChat v2.0 SOTA - Setup & Progress Tracker

**Created:** December 17, 2025  
**Last Updated:** December 28, 2025  
**Status:** ✅ Production Deployed | ✅ Metadata Pipeline Working | ✅ Side-by-Side Editor | ✅ 256-word Chunks | ✅ Performance Optimized

---

## 📊 Quick Status Dashboard

| Component | Status | URL/Notes |
|-----------|--------|-----------|
| **Frontend (Vercel)** | ✅ Live | https://dev-chat-frontend.vercel.app/ |
| **Backend (Railway)** | ✅ Live | https://3iechat.up.railway.app |
| **PDF Processing (Modal)** | ✅ Working | `devchat-mineru` app with T4 GPU (manual trigger only) |
| **Vector DB (Qdrant)** | ✅ Connected | `devchat_v2` collection |
| **Metadata Pipeline** | ✅ Working | CrossRef → OpenAlex → LLM enrichment (with item_type, volume, issue, pages) |
| **Admin Metadata UI** | ✅ Working | Side-by-side editing with PDF viewer |
| **Settings Wiring** | ✅ Done | Frontend settings sent to backend |
| **LLM Suggestions** | ✅ Done | Context-aware follow-up queries |
| **Unified CLI** | ✅ Done | `devchat` command with all operations |
| **Modular Routes** | ✅ Done | `api/routes/` split by domain |
| **Chunking** | ✅ Optimized | 256 words/chunk for better RAG precision |
| **Connection Pooling** | ✅ Done | PostgreSQL pool (5 connections, 10 overflow) |
| **Query Caching** | ✅ Done | LRU cache with 1hr TTL for identical queries |
| **Parallel Query Processing** | ✅ Done | Classify+expand+filters run concurrently |
| **Proportional Context** | ✅ Done | SOTA per-study allocation (all studies cited) |

---

## 🚀 What's Deployed & Working

### Production Stack

| Service | Provider | Details |
|---------|----------|----------|
| **Frontend** | Vercel | Next.js 15, auto-deploy from GitHub |
| **Backend** | Railway | FastAPI, slim Docker image |
| **PDF Parser** | Modal | MinerU 2.6.8 on T4 GPU |
| **Storage** | Cloudflare R2 | Bucket: `devchat-pdfs` |
| **Vector DB** | Qdrant Cloud | Collection: `devchat_v2` (413K+ vectors) |
| **Metadata DB** | Railway PostgreSQL | 94 documents, instant queries (~5ms) |
| **Embeddings** | Cohere | embed-v4.0 (1536 dims) |
| **LLM (Fast)** | OpenRouter | GPT-4o-mini |
| **LLM (Reasoning)** | OpenRouter | GPT-4o |
| **Reranking** | Cohere | rerank-v3.5 |
| **Observability** | Langfuse | Full tracing |

### GitHub Repository
```
https://github.com/lsempe77/dev_chat
Branch: main
```

---

##  TODO List (Priority Order)

### P0 - Critical (This Week)

| Task | Description | Status |
|------|-------------|--------|
| **Smart Metadata Pipeline** | CrossRef/OpenAlex lookup + LLM gap fill | ✅ Done |
| **Wire Settings to Backend** | Pass `relevanceThreshold`, `maxStudies`, `answerStyle`, `useReranking` | ✅ Done |
| **LLM-Based Suggestions** | Generate contextual "Try next" queries using LLM | ✅ Done |
| **Admin Metadata UI** | Review, edit, verify document metadata | ✅ Done |
| **Side-by-Side Metadata Editor** | Edit form as panel, view PDF alongside | ✅ Done |
| **Modal Hourly Schedule Disabled** | Processing now manual-only from Admin UI | ✅ Done |
| **Duplicate Processing Prevention** | R2 lock mechanism prevents parallel processing | ✅ Done |
| **256-word Chunks** | Smaller chunks for better RAG precision | ✅ Done |
| **item_type Extraction** | Extract volume, issue, pages from CrossRef/OpenAlex | ✅ Done |

### P1 - Important (This Month)

| Task | Description | Status |
|------|-------------|--------|
| **PostgreSQL Metadata Store** | Dedicated database for document metadata (instant queries vs Qdrant scroll) | ✅ Done |
| **PDF Viewer in Metadata Tab** | Open PDF side-by-side while editing metadata | ✅ Done |
| **Clickable Citations → PDF** | Click citation → opens PDF at page, with highlight text | ✅ Done |
| **Citation Coverage Validator** | Ensures all retrieved sources are cited in answer | ✅ Done |
| **Page-Aware Chunking** | Store page numbers in Qdrant for PDF navigation | ✅ Done |
| **Unified CLI** | Single `devchat` command for all operations | ✅ Done |
| **Modular Routes** | Split routes.py into domain files | ✅ Done |
| **Bibliography Import** | RIS/BibTeX/CSV parser with fuzzy matching | ✅ Done |
| **Export Citations** | BibTeX/RIS format export | ✅ Done |
| **Usage Analytics** | Track queries, latency, user engagement | ⬜ TODO |
| **Zotero Integration** | Allow user to add Zotero API for integrating library -> then triggers **Bibliography Import**| ⬜ TODO |
| **Multi-tenant architecture** | Frontend and backend | ⬜ TODO |
| **Teams architecture** | Role-based team access; Frontend and backend | ⬜ TODO |


### P2 - Future (Citation Quality Improvements)

| Task | Description |
|------|-------------|
| **Source-to-Claim Ledger** | Two-step LLM: first create claim→source map, then write answer. Dramatically improves citation recall. |
| **Structured Answer Sections** | Force sections like "Consensus", "Disagreements", "Methods caveats" - gives LLM places to cite more sources |
| **Diversity Boosting Retrieval** | Cluster/dedup + rank by "novel contribution" not just similarity. Fewer, more distinct items → higher usage |
| **PDF Text Highlighting** | Currently uses browser's #search= (Chrome/Edge only). Could implement custom PDF viewer with highlight overlay |
| **Config-driven Branding** | Logo, colors, name via env vars |
| **Collection Isolation** | Per-team Qdrant collections |


### 🐛 Known Test Failures (For Review)

| Test | File | Issue | Priority |
|------|------|-------|----------|
| `test_large_context_routes_to_reasoning` | `tests/test_generation.py:51` | Model router returns `FAST` tier instead of `REASONING` for large context. The 50KB threshold logic may need adjustment or the test expectation is wrong. | Low |
| `test_to_qdrant_filter_sector` | `tests/test_retrieval.py:72` | `ExtractedFilters.to_qdrant_filter()` returns `None` when sector filter is set. The sector field mapping to Qdrant may be missing or the filter construction logic is incomplete. | Medium |

**Last Test Run:** December 24, 2025 — 35 passed, 2 failed, 2 skipped (end-to-end tests require live services)

---

## 📚 Metadata Resolution Pipeline

Smart metadata extraction from multiple authoritative sources:

```
┌────────────────────────────────────────────────────────────────────┐
│                    METADATA RESOLUTION PIPELINE                    │
├────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  PDF Upload                                                        │
│      ▼                                                             │
│  STEP 1: Extract DOI from PDF (regex + PDF metadata)               │
│      │                                                             │
│      ├─── DOI Found ──▶ CrossRef/OpenAlex Lookup                  │
│      │                                                             │
│      └─── No DOI ────▶ LLM Extract title/authors                  │
│                              ▼                                     │
│                        OpenAlex Fuzzy Search                       │
│                              │                                     │
│      ◀───────────────────────┘                                     │
│      ▼                                                             │
│  STEP 2: Merge & Validate (title, authors, year, DOI, abstract)   │
│      ▼                                                             │
│  STEP 3: LLM Gap Fill (country, sector, study_type, intervention) │
│      ▼                                                             │
│  STEP 4: User Review (if confidence < threshold)                   │
│                                                                     │
│  ALTERNATIVE INPUTS:                                               │
│  • RIS/BibTeX Import → Skip to Step 2                              │
│  • CSV with DOIs → Batch lookup                                    │
│  • Zotero Sync (Future)                                            │
└────────────────────────────────────────────────────────────────────┘
```

### Data Sources

| Source | Coverage | Quality | Cost | Rate |
|--------|----------|---------|------|------|
| CrossRef | 140M+ DOIs | Excellent | Free | 50/sec |
| OpenAlex | 250M+ works | Excellent | Free | 100K/day |
| LLM | Any PDF | Variable | $$$ | N/A |

### Implementation Files

```
src/ingestion/metadata/
```

---

## 🗄️ PostgreSQL Dual-Store Architecture (December 2025)

Production-grade metadata storage with instant queries:

### Why PostgreSQL?

| Operation | Qdrant (Before) | PostgreSQL (After) |
|-----------|-----------------|--------------------|
| List 94 documents | ~2-3 seconds (scroll 413K vectors) | **~5ms** |
| Count documents | ~1 second (full scan) | **<1ms** |
| Filter by needs_review | ~2 seconds | **<5ms** |
| Aggregate stats | Not possible | **Instant** |

### Dual-Store Pattern

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        DUAL-STORE ARCHITECTURE                          │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   ┌─────────────────────┐              ┌─────────────────────┐          │
│   │     PostgreSQL      │              │       Qdrant        │          │
│   │   (Metadata Store)  │              │   (Vector Store)    │          │
│   ├─────────────────────┤              ├─────────────────────┤          │
│   │ • Document metadata │              │ • 413K+ embeddings  │          │
│   │ • 94 documents      │              │ • Semantic search   │          │
│   │ • CRUD operations   │              │ • Hybrid retrieval  │          │
│   │ • Instant queries   │              │ • Chunk payloads    │          │
│   │ • Full SQL support  │              │                     │          │
│   └──────────┬──────────┘              └──────────┬──────────┘          │
│              │                                     │                     │
│              └─────────────┬───────────────────────┘                     │
│                            │                                             │
│                            ▼                                             │
│              ┌─────────────────────────┐                                │
│              │      Admin Routes       │                                │
│              │ /admin/documents        │                                │
│              │ /admin/documents/sync   │  ← Modal calls this           │
│              │ /admin/metadata         │                                │
│              │ /admin/db-status        │                                │
│              └─────────────────────────┘                                │
│                                                                          │
│   SYNC STRATEGY:                                                        │
│   • Initial: scripts/sync_qdrant_to_postgres.py (one-time migration)   │
│   • Ongoing: Modal calls /admin/documents/sync after Qdrant indexing   │
│   • Fallback: If Postgres unavailable, routes fall back to Qdrant      │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### Database Schema

```sql
CREATE TABLE documents (
    id VARCHAR(255) PRIMARY KEY,
    title TEXT NOT NULL,
    filename VARCHAR(500) NOT NULL,
    authors TEXT[],
    year INTEGER,
    doi VARCHAR(255),
    journal VARCHAR(500),
    publisher VARCHAR(500),
    abstract TEXT,
    cited_by_count INTEGER,
    is_open_access BOOLEAN,
    countries TEXT[],
    sectors TEXT[],
    study_type VARCHAR(255),
    intervention_type VARCHAR(500),
    sdgs TEXT[],
    keywords TEXT[],
    chunk_count INTEGER DEFAULT 0,
    page_count INTEGER DEFAULT 0,
    metadata_source VARCHAR(50),
    metadata_confidence FLOAT DEFAULT 0.0,
    needs_review BOOLEAN DEFAULT TRUE,
    status VARCHAR(50) DEFAULT 'indexed',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    extra JSONB
);
```

### Implementation Files

```
src/database/
├── __init__.py           # Package exports
├── models.py             # SQLAlchemy Document model
├── connection.py         # Async PostgreSQL connection
└── repository.py         # CRUD operations

scripts/
└── sync_qdrant_to_postgres.py   # Migration utility

api/routes/
└── admin.py              # Uses Postgres when available
```

### Environment Variables

```bash
# Railway internal (backend → Postgres)
DATABASE_URL=postgresql://postgres:***@postgres.railway.internal:5432/railway

# Public (for local scripts)
DATABASE_URL=postgresql://postgres:***@crossover.proxy.rlwy.net:24886/railway
```

### Debug Endpoint

```bash
# Check PostgreSQL status
curl https://3iechat.up.railway.app/admin/db-status

# Response:
{
  "postgres_available": true,
  "database_url": "postgresql://postgres:***@postgres.railway.internal:5432/railway",
  "document_count": 94,
  "connection": "success"
}
```

---

## ⚡ Performance Optimizations (December 2025)

### Overview

| Optimization | Before | After | Improvement |
|--------------|--------|-------|-------------|
| **PostgreSQL Connection Pooling** | ~4.3s per request | ~0.3s | **14x faster** |
| **Query Processing** | 7.2s (sequential) | ~2.5s (parallel) | **3x faster** |
| **Response Caching** | 17s (always compute) | <5ms (cache hit) | **3000x faster** |
| **Total Chat Time** | ~22s | ~15s (first) / <5ms (cached) | **Significantly faster** |

### 1. PostgreSQL Connection Pooling

**Problem:** Every admin request created a new TCP connection to PostgreSQL (NullPool).

**Solution:** Enabled persistent connection pool.

```python
# src/database/connection.py
engine = create_async_engine(
    database_url,
    pool_size=5,           # 5 persistent connections
    max_overflow=10,       # Up to 15 total under load
    pool_timeout=30,
    pool_recycle=1800,     # Recycle after 30 min
    pool_pre_ping=True,    # Validate connections
)
```

**Impact:** Documents/Metadata tabs load 14x faster.

### 2. Parallel Query Processing

**Problem:** Query processor ran 3 LLM calls sequentially (classify → expand → extract_filters).

**Solution:** Run all 3 in parallel with `asyncio.gather`.

```python
# src/retrieval/query_processor.py
query_type, expanded_query, filters = await asyncio.gather(
    self._classify_query(query),
    self._expand_query(query),
    self._extract_filters(query),
)
```

**Impact:** Query processing ~3x faster (limited by slowest LLM call).

### 3. Response Caching

**Problem:** Identical queries recomputed full pipeline every time.

**Solution:** LRU cache with settings-aware keys.

```python
# src/agents/devchat_agent.py
cache = get_response_cache()

# Cache key includes query + settings
settings_dict = {
    "relevance_threshold": user_settings.relevance_threshold,
    "max_studies": user_settings.max_studies,
    "answer_style": user_settings.answer_style,
    "use_reranking": user_settings.use_reranking,
    "use_structured_citations": user_settings.use_structured_citations,
}

cached_response = await cache.get(query, settings_dict=settings_dict)
if cached_response:
    return cached_response  # <5ms
```

**Configuration:**
- TTL: 1 hour (`response_cache_ttl_seconds: 3600`)
- Max entries: 100 (LRU eviction)
- Enabled by default (`enable_response_cache: true`)

**Impact:** Repeat queries return in <5ms instead of 15-20s.

### Cache Monitoring

```bash
# Check cache stats
curl https://3iechat.up.railway.app/health/production

# Response includes:
{
  "cache": {
    "enabled": true,
    "size": 42,
    "max_size": 100,
    "ttl_seconds": 3600,
    "hits": 128,
    "misses": 57,
    "hit_rate": 0.692
  }
}
```

### 4. Proportional Context Allocation (SOTA)

**Problem:** When retrieving many studies, earlier studies consumed all context budget, causing later studies to be completely dropped from both context and citations.

**Solution:** Each study gets a proportional share of the context budget.

```python
# src/retrieval/context_builder.py
num_studies = len(by_study)
overhead_per_study = 200  # Headers, separators
available_for_content = max_context_length - (overhead_per_study * num_studies)
chars_per_study = max(500, available_for_content // num_studies)

# Each study's content is truncated at sentence boundaries
combined_text = self._truncate_study_content(combined_text, chars_per_study)
```

**Configuration:**
- `max_context_length`: 16,000 chars (increased from 8,000)
- Minimum 500 chars per study
- Intelligent truncation at sentence boundaries

**Impact:** All retrieved studies are represented and cited, even with `max_studies=20`.

**Example:**
- With 10 studies: each gets ~1,400 chars
- With 20 studies: each gets ~700 chars
- Studies are never completely dropped

---

## 🖥️ Unified CLI (December 2025)

Single `devchat` command for all operations:

```bash
# Install CLI
pip install -e .

# Available commands
devchat --help
```

### Commands

| Command | Description |
|---------|-------------|
| `devchat serve` | Start API server (`--port`, `--reload`) |
| `devchat ingest` | Ingest documents (`--source`, `--recreate`) |
| `devchat process-pdfs` | Process PDFs with MinerU (`--pdf-dir`) |
| `devchat evaluate` | Run RAGAS evaluation (`--test-file`) |
| `devchat citations` | Evaluate citation quality (`--batch`) |
| `devchat ragas` | Run RAGAS evaluator (`--query`) |
| `devchat check-metadata` | Debug Qdrant metadata (`--list`, `--doc-id`) |
| `devchat health` | Check service health (`--detailed`) |
| `devchat version` | Show version info |

### Example Usage

```bash
# Development server with hot reload
devchat serve --port 8000 --reload

# Ingest markdown documents
devchat ingest --source ./data/markdown --recreate

# Check all indexed documents
devchat check-metadata --list

# Verify services are healthy
devchat health --detailed
```

---

## 📁 Modular Routes Architecture (December 2025)

Split the monolithic `routes.py` (1936 lines) into domain-specific modules:

```
api/routes/
├── __init__.py          # Exports all routers for backwards compatibility
├── dependencies.py      # Shared singletons: get_agent(), get_indexer(), caches
├── health.py            # /health/* endpoints (~100 lines)
├── chat.py              # /chat/* endpoints (~110 lines)
├── api.py               # /api/* frontend endpoints (~280 lines)
└── admin.py             # /admin/* dashboard endpoints (~1100 lines)
```

### Benefits

| Before | After |
|--------|-------|
| 1936 lines in one file | 5 focused domain files |
| Hard to navigate | Each file ~100-300 lines |
| Merge conflicts | Isolated changes per domain |
| Tight coupling | Shared dependencies extracted |

### Server Import (unchanged)

```python
# api/server.py - still works exactly the same
from api.routes import admin_router, api_router, chat_router, health_router, router
```

---

## 🔧 Configuration Reference

### Environment Variables (.env)

```env
# Required
OPENROUTER_API_KEY=sk-or-v1-...
COHERE_API_KEY=...
QDRANT_URL=https://xxx.eu-west-1.aws.cloud.qdrant.io
QDRANT_API_KEY=...

# R2 Storage
R2_ACCOUNT_ID=...
R2_ACCESS_KEY_ID=...
R2_SECRET_ACCESS_KEY=...
R2_BUCKET_NAME=devchat-pdfs

# Optional
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=https://cloud.langfuse.com
```

### Modal Secrets (in Modal dashboard)

| Secret Name | Keys | Purpose |
|-------------|------|---------|
| `r2-credentials` | R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET_NAME | PDF storage |
| `qdrant-credentials` | QDRANT_URL, QDRANT_API_KEY | Vector database |
| `cohere-credentials` | COHERE_API_KEY | Embeddings |
| `openrouter-credentials` | OPENROUTER_API_KEY | LLM metadata enrichment |

### Qdrant Configuration

```
Collection: devchat_v2
Vector: dense (named vector, 1536 dims)
Payload Index: pdf_name (keyword)
Distance: Cosine
```

---

## 🚀 Quick Start Commands

### Run Backend
```powershell
cd devchat_v2_sota
.\.venv\Scripts\Activate.ps1
uvicorn api.server:app --reload --port 8000
```

### Run Frontend
```powershell
cd devchat_v2_sota/frontend
npm run dev
# Access: http://localhost:3000
```

### Process PDFs (Modal)
```powershell
# Process all new PDFs in R2
modal run infrastructure/modal_mineru.py::orchestrate

# Force reprocess everything
modal run infrastructure/modal_mineru.py::orchestrate --force-reprocess

# Check what's indexed
modal run infrastructure/modal_mineru.py::check_qdrant
```

### Test Semantic Search
```python
# Quick test script
from qdrant_client import QdrantClient
import cohere
import os

qdrant = QdrantClient(url=os.getenv("QDRANT_URL"), api_key=os.getenv("QDRANT_API_KEY"))
co = cohere.Client(os.getenv("COHERE_API_KEY"))

query = "What is ALCE benchmark?"
embedding = co.embed(texts=[query], model="embed-v4.0", input_type="search_query").embeddings[0]

results = qdrant.query_points(
    collection_name="devchat_v2",
    query=embedding,
    using="dense",
    limit=5
)
for r in results.points:
    print(f"Score: {r.score:.3f} | {r.payload['text'][:100]}...")
```

---

## 📋 Phase Completion Status

### Phase 1-5: Core RAG ✅

| Phase | Status | Key Achievement |
|-------|--------|-----------------|
| 1. Environment | ✅ | Python 3.12, all deps installed |
| 2. Vector DB | ✅ | Qdrant Cloud connected |
| 3. Ingestion | ✅ | Document loader + chunking |
| 4. Retrieval | ✅ | Hybrid search + reranking |
| 5. Generation | ✅ | GPT-4o-mini via OpenRouter |

### Phase 6: Research Workbench UI ✅

| Component | Status |
|-----------|--------|
| Split Layout | ✅ |
| Answer Panel + Citations | ✅ |
| Evidence Panel | ✅ |
| Study Cards | ✅ |
| Filter Chips/Drawer | ✅ |
| Settings Drawer | ✅ |
| Compare Modal | ✅ |
| Admin UI | ✅ |

### Phase 7: Integration ✅

- [x] Frontend ↔ Backend connected
- [x] Citations clickable and validated
- [x] Full query → answer flow working

### Phase 8: Production PDF Pipeline ✅

| Task | Status |
|------|--------|
| Modal app deployed | ✅ `devchat-mineru` |
| R2 bucket configured | ✅ `devchat-pdfs` |
| MinerU GPU processing | ✅ T4, ~2 min/24 pages |
| Cohere embeddings | ✅ 1536 dims |
| Qdrant indexing | ✅ Named vector `dense` |
| Smart deduplication | ✅ Checks R2 + Qdrant |

---

## 🐛 Bugs Fixed

| Date | Issue | Resolution |
|------|-------|------------|
| Dec 17 | Embedding dim mismatch (1024 vs 1536) | Updated to Cohere's actual 1536 dims |
| Dec 17 | Qdrant API deprecation | Changed `search()` to `query_points()` |
| Dec 17 | Sparse search returned 0 results | Fixed hash randomization with MD5 |
| Dec 17 | Filter extraction too aggressive | Rewrote conservative prompt |
| Dec 17 | Reranker API error | Removed deprecated `return_documents` param |
| Dec 18 | Citations showing "Unknown Author" | Fixed metadata extraction pipeline |
| Dec 18 | Qdrant named vector error | Updated to `vectors={"dense": ...}` |
| Dec 18 | Payload index missing | Created index on `pdf_name` field |

---

## 🔮 Roadmap

### Completed (December 2025)

| Task | Status |
|------|--------|
| Deploy Backend (Railway) | ✅ Done |
| Deploy Frontend (Vercel) | ✅ Done |
| Frontend ↔ Backend wiring | ✅ Done |
| Wire Settings to backend | ✅ Done |
| LLM-based suggestions | ✅ Done |
| Bulk document ingestion | ✅ Done |
| Admin UI → R2 upload | ✅ Done |
| PostgreSQL metadata store | ✅ Done |
| Performance optimizations | ✅ Done |
| Proportional context allocation | ✅ Done |

### Next Up

| Priority | Task | Effort |
|----------|------|--------|
| 🟡 P1 | Run RAGAS evaluation | 1-2 days |
| 🟡 P1 | Usage Analytics (queries, latency, engagement) | 2-3 days |
| 🟡 P1 | Zotero Integration | 2-3 days |
| 🟡 P2 | Authentication (Clerk) | 2-3 days |
| 🟡 P2 | Contextual Retrieval | 3-5 days |
| 🟡 P2 | HyDE embeddings | 2-3 days |
| 🟡 P2 | Multi-tenant architecture | 3-5 days |
| 🟢 P3 | Docker containerization | 2-3 days |
| 🟢 P3 | PDF retention policy | 1 day |

### Long-Term (v3.0)

| Feature | Description |
|---------|-------------|
| Self-RAG | LLM critiques own retrieval |
| ColBERTv2 | Late interaction retrieval |
| RAPTOR | Hierarchical summarization |
| GraphRAG | Knowledge graph retrieval |
| SaaS Platform | Multi-tenant, billing, API |

---

## 📚 Architecture Diagrams

### RAG Pipeline

```
Query → Query Processor → Hybrid Retriever → Reranker → Context Builder → Synthesizer → Answer
              ↓                   ↓              ↓
         Expansion          Dense + Sparse    Top 15
         + Classify          from Qdrant     reranked
```

### PDF Processing Pipeline

```
R2 input-pdfs/ → Modal GPU → MinerU → R2 outputs/ → Chunking → Cohere → Qdrant
                  (T4)       (extract)   (md/json)   (256 words) (embed)  (index)
```

### Frontend Architecture

```
page.tsx (Research Workbench)
├── SearchInput → POST /api/query
├── SplitLayout
│   ├── AnswerPanel (citations, evidence health, suggestions)
│   └── EvidencePanel (study cards)
├── FilterChips + FilterDrawer
├── SettingsDrawer
└── CompareModal
```

---

## 🔑 API Endpoints

### Main Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/query` | POST | Main RAG search |
| `/api/filters` | GET | Available filter options |
| `/api/compare` | POST | Compare studies |
| `/api/suggest` | POST | Query coaching |

### Admin Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/admin/status` | GET | Dashboard status |
| `/admin/upload` | POST | Upload PDF to R2 |
| `/admin/jobs` | GET | List processing jobs |
| `/admin/jobs/trigger` | POST | Start batch processing |
| `/admin/documents` | GET | List indexed documents |
| `/admin/documents/{id}` | DELETE | Delete document |

---

## 📝 Notes for Future Development

### Citation Reliability
Current system relies on LLM following `[1]`, `[2]` format. Future improvements:
- Structured output with Instructor library
- Post-hoc verification with embedding similarity
- ALCE-style attributed QA

### Multi-Tenancy (for SaaS)
Options for user isolation:
- Qdrant namespaces (logical)
- Payload filtering by tenant_id
- Separate collections (enterprise)

### Evaluation Metrics (RAGAS)
- **Faithfulness:** Answer uses only retrieved context
- **Answer Relevancy:** Answer addresses the question
- **Context Precision:** Retrieved chunks are relevant

---

## 📁 File Reference

### Core Python Files

| File | Purpose | Lines |
|------|---------|-------|
| `src/agents/devchat_agent.py` | Main RAG orchestrator | ~250 |
| `src/retrieval/hybrid_retriever.py` | Dense + sparse search | ~200 |
| `src/retrieval/reranker.py` | Cohere reranking | ~100 |
| `src/generation/synthesizer.py` | LLM answer generation | ~150 |
| `infrastructure/modal_mineru.py` | Production PDF pipeline | ~840 |
| `api/routes/` | Modular API endpoints | ~1600 |
| `cli.py` | Unified CLI | ~320 |

### Frontend Files

| File | Purpose |
|------|---------|
| `frontend/src/app/page.tsx` | Main Research Workbench |
| `frontend/src/app/admin/page.tsx` | Admin document management |
| `frontend/src/lib/api.ts` | FastAPI client functions |
| `frontend/src/components/workbench/` | All UI components |

---

## 🔗 External Resources

### Documentation
- [Qdrant Docs](https://qdrant.tech/documentation/)
- [Cohere API](https://docs.cohere.com/)
- [OpenRouter](https://openrouter.ai/docs)
- [Modal](https://modal.com/docs)
- [MinerU](https://github.com/opendatalab/MinerU)

### Research Papers
- [ALCE: Citation Generation](https://arxiv.org/abs/2305.14627)
- [RAG-Fusion](https://arxiv.org/abs/2402.03367)
- [CRAG](https://arxiv.org/abs/2401.15884)
- [Self-RAG](https://arxiv.org/abs/2310.11511)
- [Contextual Retrieval](https://www.anthropic.com/news/contextual-retrieval)

---

*Last verified: December 28, 2025*
