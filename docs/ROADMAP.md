# DevChat v2 - Roadmap

**Last Updated:** January 15, 2026

> This document tracks **future features** and priorities.  
> For current implementation status, see [SETUP_TRACKER.md](../SETUP_TRACKER.md).

---

## 🎯 Upcoming Features

### Immediate (This Week)

1. **Study Design Filter in Evidence Panel** - 4h
   - Add dropdown to filter evidence by study design (RCT, DiD, etc.)
   - Files: `frontend/src/components/EvidencePanel.tsx`

2. **Metadata & Quantitative Field Extraction** - 8h
   - Extract structured fields: effect sizes, sample sizes, outcomes, geography
   - Validate V2 SOTA pipeline against ground truth
   - Files: `extraction_pipeline/pipeline_v2_sota.py`

### Short-Term (Next 2 Weeks)

1. **Improve Faithfulness** - 8h
   - Current: 66.47%, Target: 70%+
   - Prompt tuning in Langfuse experiments
   - A/B test synthesis prompts

2. **Contextual Summarization (RCS)** - 8h
   - Before synthesis, LLM summarizes each chunk's relevance to query
   - Filters low-relevance chunks before passing to Claim Ledger
   - Files: `src/rag/retrieval.py`, `src/generation/claim_ledger.py`

3. **Smart Citations** - 12h
   - Classify citations as supporting/contrasting using OpenAlex data
   - Display: "38 Supporting | 3 Contrasting" badges
   - Files: New `src/enrichment/citation_classifier.py`

4. **Consensus Meter** - 16h
   - Visual: "Strong Support: 85%, 17/20 studies"
   - Extend ClaimLedger to track support/contradict per citation
   - Files: `src/generation/claim_ledger.py`, frontend component

### Medium-Term (Month 2)

1. **Agentic RAG** - 20h
   - Multi-step: Search → Review → Refine → Gather → Answer
   - Agent decides when to iterate on search

2. **Multimodal Support** - 24h
   - Extract tables/figures during PDF parsing
   - Vision LLM for captions, store in Qdrant

3. **Document Enrichment Pipeline** - 40h
   - Geography, intervention type, effect sizes extraction
   - Enables quantitative queries across studies

### Long-Term (Month 3+)

1. **Systematic Review Workflow** - 40h
   - Protocol → Screening → Extraction → PRISMA flow

2. **Research Report Generation** - 30h
   - Auto-generate structured reports from evidence

3. **Embeddable Widget** - 16h
   - Embed DevChat on external sites (e.g., 3ie portal)

4. **Security Hardening** - 8h
   - Rate limiting, input validation, audit logs

---

## 📊 Effort Summary

| Phase | Hours | Features |
| ----- | ----- | -------- |
| Immediate | 12h | Study design filter + Metadata extraction |
| Short-Term | 44h | Faithfulness, RCS, Smart Citations, Consensus |
| Medium-Term | 84h | Agentic RAG, Multimodal, Enrichment |
| Long-Term | 94h | SR Workflow, Reports, Widget, Security |
| **Total** | **234h** | |

---

## 📚 References

- [PaperQA2](https://github.com/future-house/paper-qa) - Agentic RAG benchmark
- [Anthropic Contextual Retrieval](https://www.anthropic.com/news/contextual-retrieval) - 49% improvement technique
- [Elicit](https://elicit.com/) - Systematic review automation
- [Scite](https://scite.ai/) - Smart Citations

---

Last updated: January 15, 2026
