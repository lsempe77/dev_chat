# DevChat v2 - Roadmap

**Last Updated:** January 15, 2026

---

## 📊 Status Dashboard

### Core Features

| Feature | Status | Notes |
|---------|--------|-------|
| **RAG Chat Interface** | ✅ Done | Query documents with grounded citations |
| **PDF Ingestion** | ✅ Done | MineRU on Modal, 97 PDFs processed |
| **Hybrid Search** | ✅ Done | Cohere embeddings + BM25 sparse |
| **Reranking** | ✅ Done | Cohere rerank-v3.5 |
| **Claim Ledger Synthesis** | ✅ Done | Two-pass extraction with citations |
| **MiniCheck Verification** | ✅ Done | Post-hoc NLI grounding |
| **PDF Citation Highlighting** | ✅ Done | PyMuPDF with page numbers |
| **Study Design Classification** | ✅ Done | 22 types, 96 docs classified |
| **Contextual Retrieval** | ✅ Done | 49% fewer retrieval failures |
| **Parent-Child Chunking** | ✅ Done | Small chunks search, parent context |

### RAG Improvements

| Technique | Status | Gap vs SOTA |
|-----------|--------|-------------|
| Hybrid Search | ✅ Done | None |
| Reranking | ✅ Done | None |
| Contextual Retrieval | ✅ Done | None |
| Parent-Child Chunking | ✅ Done | None |
| Contextual Summarization (RCS) | ❌ Not started | 8h |
| Agentic RAG | ❌ Not started | 20h |
| Multimodal (tables/figures) | ❌ Not started | 24h |

### Outcome Extraction

| Pipeline | Status | Performance |
|----------|--------|-------------|
| V2 SOTA (single paper) | ✅ Done | 100% Table 1 match (Bossuroy) |
| V11 (bulk extraction) | ✅ Done | 71.3% recall, 43 studies |

### Infrastructure

| Component | Status | Notes |
|-----------|--------|-------|
| Modal Pipeline | ✅ Done | Refactored to 8 modules |
| Qdrant Cloud | ✅ Done | 6,769 chunks indexed |
| Supabase Auth | ✅ Done | Multi-tenant ready |
| Railway API | ✅ Done | Production deployed |
| Vercel Frontend | ✅ Done | Next.js 15 |

---

## 🎯 Next Steps (Prioritized)

### Immediate (This Week)

1. **Study Design Filter in Evidence Panel** - 4h
   - Add dropdown to filter evidence by study design (RCT, DiD, etc.)
   - Files: `frontend/src/components/EvidencePanel.tsx`

2. **Auto-classify on Ingest** - 2h
   - Call study design classifier when new PDF is processed
   - Files: `infrastructure/modal_lib/processing.py`

### Short-Term (Next 2 Weeks)

3. **Contextual Summarization (RCS)** - 8h
   - Before synthesis, LLM summarizes each chunk's relevance to query
   - Filters low-relevance chunks before passing to Claim Ledger
   - Files: `src/rag/retrieval.py`, `src/generation/claim_ledger.py`

4. **Smart Citations** - 12h
   - Classify citations as supporting/contrasting using OpenAlex data
   - Display: "38 Supporting | 3 Contrasting" badges
   - Files: New `src/enrichment/citation_classifier.py`

5. **Consensus Meter** - 16h
   - Visual: "Strong Support: 85%, 17/20 studies"
   - Extend ClaimLedger to track support/contradict per citation
   - Files: `src/generation/claim_ledger.py`, frontend component

### Medium-Term (Month 2)

6. **Agentic RAG** - 20h
   - Multi-step: Search → Review → Refine → Gather → Answer
   - Agent decides when to iterate on search

7. **Multimodal Support** - 24h
   - Extract tables/figures during PDF parsing
   - Vision LLM for captions, store in Qdrant

8. **Document Enrichment Pipeline** - 40h
   - Geography, intervention type, effect sizes extraction
   - Enables quantitative queries across studies

### Long-Term (Month 3+)

9. **Systematic Review Workflow** - 40h
   - Protocol → Screening → Extraction → PRISMA flow

10. **Research Report Generation** - 30h
    - Auto-generate structured reports from evidence

11. **Embeddable Widget** - 16h
    - Embed DevChat on external sites (e.g., 3ie portal)

---

## 📁 Key File Locations

| Component | Location |
|-----------|----------|
| RAG Agent | `src/agents/devchat_agent.py` |
| Claim Ledger | `src/generation/claim_ledger.py` |
| Chunking | `src/ingestion/chunking.py` |
| Modal Pipeline | `infrastructure/modal_lib/` |
| Study Design Config | `src/config/study_designs.py` |
| Extraction Pipeline | `extraction_pipeline/pipeline_v2_sota.py` |
| API Server | `api/server.py` |
| Frontend | `frontend/src/` |

---

## 📈 Metrics

### Current Performance
- **Documents indexed:** 97 PDFs, 6,769 chunks
- **Study designs classified:** 96 documents
- **Contextual prefixes:** 100% coverage
- **V2 SOTA extraction:** 100% table match (Bossuroy)
- **V11 bulk extraction:** 71.3% recall

### Remaining Work
| Phase | Hours | Features |
|-------|-------|----------|
| Immediate | 6h | Filters + auto-classify |
| Short-Term | 36h | RCS, Smart Citations, Consensus |
| Medium-Term | 84h | Agentic RAG, Multimodal, Enrichment |
| Long-Term | 86h | SR Workflow, Reports, Widget |
| **Total** | **212h** | |

---

## 📚 References

- [PaperQA2](https://github.com/future-house/paper-qa) - Agentic RAG benchmark
- [Anthropic Contextual Retrieval](https://www.anthropic.com/news/contextual-retrieval) - 49% improvement technique
- [Elicit](https://elicit.com/) - Systematic review automation
- [Scite](https://scite.ai/) - Smart Citations

---

*Updated: January 15, 2026*
