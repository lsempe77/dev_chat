# DevChat v2.0 - Setup & Status Tracker

**Last Updated:** January 27, 2025

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

> **Active:** `extraction_pipeline/pipeline_v2_sota.py` ONLY  
> **Archived:** All v1-v17 and extractor.py variants in `archive/extraction_pipeline_old/`

| Pipeline | Status | Performance | Notes |
| -------- | ------ | ----------- | ----- |
| **V2 SOTA** (production) | ✅ Active | 100% accuracy on Bossuroy Table 1 (18/18 rows) | BeautifulSoup HTML parsing, 4-stage process |
| V11 (bulk, archived) | ⚠️ Deprecated | 71.3% recall, 43 studies | Superseded by V2 SOTA |




### Quality Metrics (Baseline)

| Metric | Score | Target |
| ------ | ----- | ------ |
| Faithfulness | 66.47% | 70%+ |
| Citation Recall | 98.86% | 70%+ ✅ |
| Citation Precision | 98.86% | 70%+ ✅ |
| Avg Latency | 12,193ms | - |

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
│   └── config/             # Study designs, costs
├── frontend/               # Next.js app
│   └── src/components/     # React components
├── infrastructure/         
│   ├── modal_mineru.py     # Entry point (~230 lines)
│   └── modal_lib/          # 8 modules (chunking, embedding, etc.)
├── extraction_pipeline/    # ✅ ACTIVE: Treatment effect extraction
│   ├── pipeline_v2_sota.py # Production script (ONLY version to use)
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

