# DevChat v2.0 SOTA - Setup & Progress Tracker

**Created:** December 17, 2025  
**Last Updated:** December 19, 2025  
**Status:** ✅ Core RAG Pipeline Complete | ⚠️ Needs Real Document Corpus

---

## 📊 Quick Status Dashboard

| Component | Status | Notes |
|-----------|--------|-------|
| **RAG Pipeline** | ✅ Complete | Retrieval → Rerank → Generate working |
| **Frontend UI** | ✅ Complete | Next.js Research Workbench |
| **PDF Processing** | ✅ Complete | Modal + MinerU + R2 + Qdrant |
| **Document Corpus** | ⚠️ **1 test PDF only** | Need SharePoint integration |
| **SharePoint Sync** | ❌ Not Started | Critical blocker |
| **Authentication** | ❌ Not Started | Future: Clerk/Auth0 |
| **Evaluation** | ❌ Not Run | RAGAS metrics ready |

---

## 🚨 What's Missing (Critical)

### 1. 🚀 DEPLOYMENT (Backend + Frontend)
**Current State:** Running locally only (localhost:8000 + localhost:3000)  
**Required:** Deploy to cloud for external access  
**Options:**
| Service | Backend | Frontend | Cost |
|---------|---------|----------|------|
| **Railway** | FastAPI | Next.js | ~$5/mo |
| **Render** | FastAPI | Static/Vercel | Free tier |
| **Vercel + Railway** | Railway | Vercel | Free-$5/mo |
| **Fly.io** | FastAPI | Next.js | ~$5/mo |

### 2. Real Document Corpus
**Current State:** Only 1 test paper (ALCE, 31 chunks) indexed  
**Required:** 100+ 3ie papers  
**Solution:** Admin UI upload (not SharePoint API)

### 3. Admin UI → R2 Upload Wiring
**Current State:** Admin UI exists but upload not connected  
**Required:** Wire drag & drop → R2 → Modal trigger  
**Flow:**
```
Admin UI (drop PDFs) → FastAPI /admin/upload → R2 bucket → Modal process
```

### 4. End-to-End Validation
- [ ] Run RAGAS evaluation on real queries
- [ ] Test with 3ie subject matter experts
- [ ] Benchmark retrieval precision/recall

---

## ✅ What's Working

### Production Stack

| Component | Technology | Status |
|-----------|------------|--------|
| **Vector DB** | Qdrant Cloud (EU) | ✅ Collection `devchat_v2`, 31 chunks |
| **Embeddings** | Cohere embed-v4.0 | ✅ 1536 dimensions |
| **LLM** | OpenRouter (GPT-4o-mini) | ✅ Fast model |
| **Reasoning** | OpenRouter (GPT-4o) | ✅ Complex queries |
| **Reranking** | Cohere rerank-v3.5 | ✅ Top 50 → 15 |
| **PDF Parser** | MinerU 2.6.8 | ✅ Modal T4 GPU |
| **Storage** | Cloudflare R2 | ✅ Bucket `devchat-pdfs` |
| **Compute** | Modal (serverless GPU) | ✅ Auto-scaling |
| **Frontend** | Next.js 16 | ✅ Research Workbench |
| **Backend** | FastAPI | ✅ Port 8000 |
| **Observability** | Langfuse Cloud | ✅ Full tracing |

### Key Files

```
src/
├── agents/devchat_agent.py      # Main orchestrator
├── retrieval/
│   ├── hybrid_retriever.py      # Dense + sparse search
│   ├── reranker.py              # Cohere rerank
│   └── query_processor.py       # Query expansion
├── generation/
│   ├── synthesizer.py           # Answer generation
│   └── citations.py             # Citation formatting
└── ingestion/
    └── pdf_processor.py         # MinerU wrapper

infrastructure/
└── modal_mineru.py              # Production PDF pipeline (840 lines)

frontend/src/
├── app/page.tsx                 # Main Research Workbench
├── app/admin/page.tsx           # Admin document management
└── components/workbench/        # UI components
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

| Secret Name | Keys |
|-------------|------|
| `r2-credentials` | R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET_NAME |
| `qdrant-credentials` | QDRANT_URL, QDRANT_API_KEY |
| `cohere-credentials` | COHERE_API_KEY |

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

### Near-Term (This Week)

| Priority | Task | Effort |
|----------|------|--------|
| 🔴 P0 | **Deploy Backend (Railway/Render)** | 1-2 hours |
| 🔴 P0 | **Deploy Frontend (Vercel)** | 30 min |
| 🔴 P0 | **Wire Admin UI → R2 upload** | 2-3 hours |
| 🔴 P0 | Bulk document ingestion via UI | 1 day |
| 🟡 P1 | Run RAGAS evaluation | 1 day |

### Medium-Term (Month 2)

| Priority | Task | Effort |
|----------|------|--------|
| 🟡 P2 | Authentication (Clerk) | 2-3 days |
| 🟡 P2 | Contextual Retrieval | 3-5 days |
| 🟡 P2 | HyDE embeddings | 2-3 days |
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
                  (T4)       (extract)   (md/json)    (512 tok)  (embed)  (index)
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
| `api/routes.py` | FastAPI endpoints | ~300 |

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

*Last verified: December 19, 2025*
