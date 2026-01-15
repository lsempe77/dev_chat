# DevChat v2.0 - Setup & Progress Tracker

**Last Updated:** January 15, 2026

---

## 📊 Status Dashboard

### Infrastructure

| Component | Status | Details |
|-----------|--------|---------|
| Frontend (Vercel) | ✅ Live | https://dev-chat-frontend.vercel.app/ |
| Backend (Railway) | ✅ Live | https://3iechat.up.railway.app |
| PDF Processing (Modal) | ✅ Working | MineRU + modal_lib + Contextual Retrieval |
| Vector DB (Qdrant) | ✅ Connected | 6,769 chunks, hybrid search |
| Auth (Supabase) | ✅ Working | JWT auth, RLS policies |
| Storage (R2) | ✅ Working | Cloudflare R2 for PDFs |
| Observability (Langfuse) | ✅ Working | Full tracing |

### Core Features

| Feature | Status | Notes |
|---------|--------|-------|
| Multi-tenant RAG | ✅ Done | Users create/manage own projects |
| Document Upload | ✅ Done | Drag-drop, batch, deduplication |
| Hybrid Search | ✅ Done | Cohere embed-v4 + BM25 sparse |
| Reranking | ✅ Done | Cohere rerank-v3.5 |
| Claim Ledger Synthesis | ✅ Done | Two-pass extraction with citations |
| MiniCheck Verification | ✅ Done | Post-hoc NLI grounding |
| PDF Citation Highlighting | ✅ Done | PyMuPDF with page numbers |
| Contextual Retrieval | ✅ Done | 49% fewer retrieval failures |
| Parent-Child Chunking | ✅ Done | Small chunks search, parent context |
| Study Design Classification | ✅ Done | 22 types, 96 docs classified |
| Chat History | ✅ Done | Persistent with response caching |
| Zotero Integration | ✅ Done | Sync collections, import PDFs |
| Bibliography Import | ✅ Done | RIS/BibTeX/CSV with matching |

### Admin Panel

| Tab | Status | Features |
|-----|--------|----------|
| Overview | ✅ Done | Stats, costs, projections |
| Users & RAGs | ✅ Done | User list, RAG projects |
| Quality | ✅ Done | Langfuse integration, baseline metrics |
| Documents | ✅ Done | Upload, list, delete |
| Processing | ✅ Done | Job status, trigger processing |
| Metadata | ✅ Done | Edit metadata with PDF viewer |

### Per-RAG Settings

| Feature | Status | Notes |
|---------|--------|-------|
| Model Selection | ✅ Code ready | ⚠️ Needs SQL migration + testing |
| Context Prompts | ✅ Done | Domain instructions per RAG |
| Custom Prompts | ✅ Done | Override extraction/synthesis |
| Prompt History | ✅ Done | Max 10 versions with restore |

### Extraction Pipeline

| Pipeline | Status | Performance |
|----------|--------|-------------|
| V2 SOTA (single paper) | ✅ Done | 100% Table 1 match (Bossuroy) |
| V11 (bulk extraction) | ✅ Done | 71.3% recall, 43 studies |

### Quality Metrics (Baseline)

| Metric | Score | Target |
|--------|-------|--------|
| Faithfulness | 66.47% | 70%+ |
| Citation Recall | 98.86% | 70%+ ✅ |
| Citation Precision | 98.86% | 70%+ ✅ |
| Avg Latency | 12,193ms | - |

---

## 🎯 Next Steps (Prioritized)

### Immediate (This Week)

1. **Study Design Filter** - 4h
   - Add dropdown to filter evidence by study design
   - Files: `frontend/src/components/EvidencePanel.tsx`

2. **Auto-classify on Ingest** - 2h
   - Call study design classifier in Modal pipeline
   - Files: `infrastructure/modal_lib/processing.py`

3. **Test Per-RAG Model Selection** - 2h
   - Run SQL migration `002_model_config.sql`
   - Verify model switching works end-to-end

### Short-Term (Next 2 Weeks)

4. **Improve Faithfulness** - 8h
   - Current: 66.47%, Target: 70%+
   - Prompt tuning in Langfuse experiments
   - A/B test synthesis prompts

5. **Smart Citations** - 12h
   - Classify as supporting/contrasting using OpenAlex
   - Display: "38 Supporting | 3 Contrasting"

6. **Consensus Meter** - 16h
   - Visual: "Strong Support: 85%, 17/20 studies"
   - Extend ClaimLedger to track per citation

### Medium-Term (Month 2)

7. **Document Enrichment Pipeline** - 40h
   - Geography, intervention, effect sizes extraction
   - Enables quantitative queries across studies

8. **Agentic RAG** - 20h
   - Multi-step: Search → Review → Refine → Answer

9. **Multimodal Support** - 24h
   - Extract tables/figures, vision LLM captions

### Long-Term (Month 3+)

10. **Systematic Review Workflow** - 40h
11. **Research Report Generation** - 30h
12. **Embeddable Widget** - 16h
13. **Security Hardening** - 8h

---

## 📁 Repository Structure

```
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
├── extraction_pipeline/    # Treatment effect extraction
│   ├── pipeline_v2_sota.py # Production script
│   └── outputs/            # Extracted data per study
├── evaluation/             # RAGAS, MiniCheck, test cases
├── scripts/                # Utility scripts
├── docs/                   # ROADMAP.md, EVALUATION.md
└── archive/                # Old scripts, historical docs
```

---

## 🔧 Key Configurations

### Environment Variables
```
SUPABASE_URL, SUPABASE_SERVICE_KEY
QDRANT_URL, QDRANT_API_KEY
OPENROUTER_API_KEY
COHERE_API_KEY
CLOUDFLARE_R2_* (access key, secret, bucket, URL)
LANGFUSE_* (host, public/secret key)
```

### SQL Migrations
| Migration | Status | Purpose |
|-----------|--------|---------|
| 001_usage_logs.sql | ✅ Applied | Usage tracking |
| 002_model_config.sql | ⚠️ Pending | Per-RAG model selection |
| 002_evaluation_runs.sql | ✅ Applied | Langfuse evaluation tracking |
| 003_prompt_config.sql | ✅ Applied | Custom prompts |

---

## 📚 Documentation

| Document | Purpose |
|----------|---------|
| [docs/ROADMAP.md](docs/ROADMAP.md) | Feature status + next steps |
| [docs/EVALUATION.md](docs/EVALUATION.md) | Evaluation framework |
| [docs/EXTRACTION.md](docs/EXTRACTION.md) | Data extraction validation |
| [extraction_pipeline/README.md](extraction_pipeline/README.md) | Table extraction pipeline |
| [infrastructure/README.md](infrastructure/README.md) | Infrastructure setup guide |
| CHANGELOG.md | Version history |

---

## 🔗 Links

| Resource | URL |
|----------|-----|
| Production | https://dev-chat-frontend.vercel.app/ |
| API Health | https://3iechat.up.railway.app/health |
| Modal App | https://modal.com/apps/3ieimpact/main/deployed/devchat-mineru |
| Langfuse | https://cloud.langfuse.com/ |
| Supabase | https://supabase.com/dashboard |

---

*Updated: January 15, 2026*
