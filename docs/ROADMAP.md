# DevChat v2 - Roadmap

**Last Updated:** January 27, 2026

> This document tracks **future features** and priorities.  
> For current implementation status, see [SETUP_TRACKER.md](../SETUP_TRACKER.md).

---

## 🎯 Upcoming Features

### Immediate

1. **Study Design Filter in Evidence Panel** - 4h
   - Add dropdown to filter evidence by study design (RCT, DiD, etc.)
   - Files: `frontend/src/components/EvidencePanel.tsx`

2. **Metadata & Quantitative Field Extraction** - 8h
   - Extract structured fields: effect sizes, sample sizes, outcomes, geography
   - Validate V2 SOTA pipeline against ground truth
   - Files: `extraction_pipeline/pipeline_v2_sota.py`

3. **"I Don't Know" Explicit Refusal** - 2h
   - When retrieval confidence is below threshold, explicitly refuse to answer
   - Instead of generating with poor context, return: "I don't have enough information to answer that confidently. Could you rephrase or specify which document to check?"
   - Prevents hallucination when no good sources found
   - Files: `src/agents/devchat_agent.py`, `src/generation/claim_ledger.py`

4. **Source Date Conflict Detection** - 2h
   - Warn when retrieved chunks span multiple years (e.g., 2019 vs 2024 policies)
   - Add warning to response: "[Note: Some sources are older. The most recent is from {year}]"
   - Prevents mixing outdated information with current
   - Files: `src/agents/devchat_agent.py`, response formatting

### Short-Term

1. **Embedding Model Comparison: Cohere vs Voyage 4** - 6h
   - Benchmark Voyage AI 4 (launched Jan 15, 2026) against current Cohere embed-v4
   - Metrics: retrieval accuracy, speed, cost per 1M tokens
   - Test on DevChat's academic literature domain
   - Files: `evaluation/benchmark_embeddings.py`

2. **Improve Faithfulness** - 8h
   - Current: 66.47%, Target: 70%+
   - Prompt tuning in Langfuse experiments
   - A/B test synthesis prompts

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

### Medium-Term

1. **Agentic RAG** - 20h
   - Multi-step: Search → Review → Refine → Gather → Answer
   - Agent decides when to iterate on search

2. **Multimodal Support** - 24h
   - Extract tables/figures during PDF parsing
   - Vision LLM for captions, store in Qdrant

3. **Document Enrichment Pipeline** - 40h
   - Geography, intervention type, effect sizes extraction
   - Enables quantitative queries across studies

### Long-Term

1. **Systematic Review Workflow** - 40h
   - Protocol → Screening → Extraction → PRISMA flow

2. **Research Report Generation** - 30h
   - Auto-generate structured reports from evidence

3. **Embeddable Widget** - 16h
   - Embed DevChat on external sites (e.g., 3ie portal)

4. **Security Hardening** - 8h
   - Rate limiting, input validation, audit logs


## Issues

1.  more detail on study design extraction. check better OM tool (3ie)

2.  tables not picking notes for statistical significance (*** corresponds to p<.005)



---

## 🟡 RAG Pipeline Optimizations (Medium Priority)

> These require more effort but provide meaningful improvements.

### 1. Step-Back Prompting - 4h
- For specific questions, first ask a more general question
- "What's the effect size in Bossuroy 2024?" → First: "What outcomes does Bossuroy 2024 measure?"
- Files: `src/retrieval/query_processor.py`

### 2. Self-Consistency - 8h
- Generate 3 answers with temperature > 0, select most consistent
- Improves accuracy on complex synthesis questions
- Files: `src/generation/claim_ledger.py`

### 3. Additional Payload Indexes - 2h
- Index `year`, `sector`, `study_type` in Qdrant for faster filtering
- Files: `infrastructure/modal_lib/embedding.py`

### 4. Scalar Quantization Option - 2h
- Add scalar quantization (int8) as alternative to binary
- Better precision/speed tradeoff for some use cases
- Files: `infrastructure/modal_lib/embedding.py`

---

## 📚 References

- [PaperQA2](https://github.com/future-house/paper-qa) - Agentic RAG benchmark
- [Anthropic Contextual Retrieval](https://www.anthropic.com/news/contextual-retrieval) - 49% improvement technique
- [RAG-Fusion](https://arxiv.org/abs/2402.03367) - Multi-query retrieval
- [Lost in the Middle](https://arxiv.org/abs/2307.03172) - LLM context position bias
- [Binary Quantization](https://qdrant.tech/documentation/guides/quantization/) - Qdrant guide
- [Elicit](https://elicit.com/) - Systematic review automation
- [Scite](https://scite.ai/) - Smart Citations

