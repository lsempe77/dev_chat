# DevChat v2 - Roadmap

**Last Updated:** January 27, 2026

> This document tracks **future features** and priorities.  
> For current implementation status, see [SETUP_TRACKER.md](../SETUP_TRACKER.md).

---

## Sphinx Documentation - PENDING

Sphinx autodoc setup is complete in `docs/sphinx/`. 

### To Enable GitHub Pages (requires GitHub Pro for private repos):

1. **Upgrade to GitHub Pro** (private repo requirement)
   - Go to: https://github.com/settings/billing/plans

2. **Enable GitHub Pages**
   - Go to: Settings → Pages
   - Source: Select "GitHub Actions"
   - The workflow `.github/workflows/docs.yml` will auto-deploy on push

3. **Access docs at:** `https://lsempe77.github.io/dev_chat/`

### Build Locally:
```bash
cd docs/sphinx
sphinx-build -b html source build/html
# Open build/html/index.html
```

### What's Documented:
- `src/` - Core library (agents, generation, retrieval, ingestion)
- `api/` - FastAPI routes and schemas
- `extraction_pipeline/` - Table extraction
- `infrastructure/` - Modal deployment
- `evaluation/` - Test and validation scripts
- `scripts/` - Utility scripts

---

## Upcoming Features

### Immediate

1. **Study Design Filter in Evidence Panel** - 4h
   - Add dropdown to filter evidence by study design (RCT, DiD, etc.)
   - Files: `frontend/src/components/EvidencePanel.tsx`

2. **Metadata & Quantitative Field Extraction** - 8h
   - Extract structured fields: effect sizes, sample sizes, outcomes, geography
   - Validate V2 SOTA pipeline against ground truth
   - Files: `extraction_pipeline/pipeline.py`

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
   - Multi-step: Search -> Review -> Refine -> Gather -> Answer
   - Agent decides when to iterate on search

2. **Multimodal Support** - 24h
   - Extract tables/figures during PDF parsing
   - Vision LLM for captions, store in Qdrant

3. **Document Enrichment Pipeline** - 40h
   - Geography, intervention type, effect sizes extraction
   - Enables quantitative queries across studies

### Long-Term

1. **Systematic Review Workflow** - 40h
   - Protocol -> Screening -> Extraction -> PRISMA flow

2. **Research Report Generation** - 30h
   - Auto-generate structured reports from evidence

3. **Embeddable Widget** - 16h
   - Embed DevChat on external sites (e.g., 3ie portal)

4. **Security Hardening** - 8h
   - Rate limiting, input validation, audit logs

5. https://www.trulens.org/?


## Issues

1. More detail on study design extraction. Check better OM tool (3ie)

2. Tables not picking notes for statistical significance (*** corresponds to p<.005)

---

## Tables Extraction Ground Truth Dataset - 16h

**Goal:** Create gold-standard human-annotated dataset to measure extraction accuracy, train models, and improve recall.

### Current State
- **Latest Test:** Study 121058356 "Pathways out of Extreme Poverty" (763 rows extracted)
  - Output: `extraction_pipeline/outputs/121058356/extracted_data.csv`
- **Legacy GT:** `8WR QEX Combined.xlsx` (443 rows, 43 studies)
- **Test Script:** `evaluation/validate_extraction.py`

### Fields Being Extracted
| Field | Description | In Latest Test |
|-------|-------------|----------------|
| `coefficient` | Regression coefficient | Yes |
| `standard_error` | SE of coefficient | Yes |
| `significance` | Star notation (*, **, ***) | Yes |
| `sample_size` | N for estimate | Yes |
| `control_mean` | Control group mean | Yes |
| `control_sd` | Control group SD | Yes |
| `literal_cell_text` | Raw cell text (e.g., "0.15*** (0.05)") | Yes |
| `outcome_name` | Outcome variable | Yes |
| `outcome_definition` | Description of outcome | Yes |
| `table_number` | Which table (Table 1, A1, etc.) | Yes |
| `treatment_arm` | Intervention arm name | Yes |

### Tasks
1. **Create human-verified ground truth for Study 121058356** - 4h
   - Manually verify all 763 rows against PDF
   - Flag extraction errors, missing rows
   - Create `ground_truth_121058356.csv`

2. **Add significance star mapping** - 2h (Fixes Issue #2)
   - Map *** to p<.001, ** to p<.01, * to p<.05
   - Extract from table footnotes when available

3. **Expand to 5-10 diverse studies** - 8h
   - Select studies with different table formats
   - Complex tables: multi-panel, subgroups, footnotes

4. **Validation tooling** - 2h
   - Script to compare extraction vs GT
   - Metrics: precision, recall, F1 by field type

5. **Check Outcomes mapping 3ie tool** - 2h
   - Define additional fields to be extracted
   - Metrics: precision, recall, F1 by field type


### Success Metrics
- **Accuracy Target:** 90%+ on numeric fields (coefficient, SE)
- **Recall Target:** 85%+ outcomes found per study
- **Significance Parsing:** 95%+ star notation correctly interpreted

---

## RAG Pipeline Optimizations (Medium Priority)

> These require more effort but provide meaningful improvements.

### 1. Self-Consistency - 8h
- Generate 3 answers with temperature > 0, select most consistent
- Improves accuracy on complex synthesis questions
- Files: `src/generation/claim_ledger.py`

---

## References

- [PaperQA2](https://github.com/future-house/paper-qa) - Agentic RAG benchmark
- [Anthropic Contextual Retrieval](https://www.anthropic.com/news/contextual-retrieval) - 49% improvement technique
- [RAG-Fusion](https://arxiv.org/abs/2402.03367) - Multi-query retrieval
- [Lost in the Middle](https://arxiv.org/abs/2307.03172) - LLM context position bias
- [Binary Quantization](https://qdrant.tech/documentation/guides/quantization/) - Qdrant guide
- [Elicit](https://elicit.com/) - Systematic review automation
- [Scite](https://scite.ai/) - Smart Citations

