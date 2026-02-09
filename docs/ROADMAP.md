# DevChat v2 - Roadmap

**Last Updated:** February 9, 2026

> This document tracks **future features** and priorities.  
> For current implementation status, see [SETUP_TRACKER.md](../SETUP_TRACKER.md).  
> For extraction pipeline details, see [extraction_pipeline/README.md](../extraction_pipeline/README.md).

---

## Upcoming Features

### 🚨 Critical Gaps (Must Fix Before Any Other Improvement)

These are foundational problems. Without solving them, every other "improvement" is unmeasurable guesswork.

1. **Golden Ground Truth Database** - 16h ⬅️ **#1 BLOCKER**
   - ❌ **No human-coded gold standard exists.** The "88% accuracy" is self-measured, not validated.
   - Need: Hand-extract effect sizes (coefficient, SE, p-value, sample size, outcome, treatment arm) for 10-15 representative studies (~150-300 rows)
   - Must cover: clean tables, messy OCR, multi-language, transposed formats, prose-only
   - Compare pipeline output row-by-row against human ground truth
   - Calculate real precision, recall, and F1 per field (coefficient, SE, outcome, etc.)
   - `data/master_UPG.csv` exists but is NOT a complete ground truth — it's a partial reference
   - **Output:** `data/ground_truth/` with verified CSVs per study + evaluation script
   - Files: New `evaluation/ground_truth_eval.py`

2. **Prompt Engineering Methodology** - 12h ⬅️ **#2 BLOCKER**
   - ❌ **All 9 prompts were written once and iterated by feel.** No systematic testing.
   - Need: Test prompt variants side-by-side on ground truth data
   - Ablation studies: Do few-shot examples help? How many? Which ones?
   - Temperature experiments: Does temp=0.0 vs 0.3 change accuracy?
   - Model comparison: Haiku vs Sonnet vs GPT-4o on same tables (cost-accuracy tradeoff)
   - Structured JSON mode vs free-text parsing comparison
   - **Output:** `evaluation/prompt_experiments/` with results per variant
   - Files: New `evaluation/prompt_ablation.py`

3. **Regression Testing Suite** - 8h
   - ❌ **No regression tests.** A prompt change can silently break 10 previously-working tables.
   - Need: Fixed test set of ~30 tables with expected outputs
   - Run after every prompt/parser change, fail if accuracy drops
   - Track: classification accuracy, coefficient match rate, SE match rate
   - **Output:** `tests/extraction/` with pytest fixtures from ground truth
   - Files: New `tests/extraction/test_regression.py`

4. **Coverage Measurement (Precision & Recall)** - 6h
   - ❌ **No idea what % of effect sizes the pipeline finds vs misses.**
   - Need: For ground truth studies, count how many real effects exist (from human coding)
   - Compare: pipeline-found vs human-coded → precision (% correct), recall (% found)
   - Break down by: table format, language, extraction method (table vs prose vs figure)
   - **Output:** Coverage report per study + aggregate metrics
   - Files: New `evaluation/coverage_analysis.py`

5. **Confidence Scores on Extractions** - 6h
   - ❌ **All outputs are point values with zero uncertainty.** Clean table extraction and blurry OCR guesses look identical.
   - Need: Score each extracted row on extraction confidence (0-1)
   - Factors: OCR quality, cell parsing ambiguity, LLM uncertainty, source type (table vs prose)
   - Flag low-confidence rows for human review priority
   - **Output:** `extraction_confidence` column in output CSVs
   - Files: `extraction_pipeline/pipeline.py`, all extractors

6. **Contradiction Resolution** - 4h
   - ❌ **When prose says "effect = 0.15" and table parser extracts 0.051, no logic flags this.**
   - Need: Cross-check table extraction vs prose extraction for same outcomes
   - Flag contradictions, prefer table values (more structured) but log disagreements
   - **Output:** `contradictions` column or separate log
   - Files: `extraction_pipeline/pipeline.py`

7. **Validation Against Published Meta-Analyses** - 8h
   - ❌ **Several programs (BRAC, GiveDirectly) have existing systematic reviews we could validate against.**
   - Need: Find published meta-analyses for overlapping studies
   - Compare our extracted effect sizes to published ones
   - Calculate: mean absolute error, correlation, systematic bias direction
   - **Output:** `evaluation/meta_analysis_comparison.py`

8. **User Feedback Loop** - 8h
   - ❌ **Researchers can't flag extraction errors in the frontend.** No corrections feed back.
   - Need: "Flag error" button on extracted estimates in Evidence Panel
   - Store corrections in Supabase `extraction_corrections` table
   - Use corrections to update ground truth and retrain/re-evaluate
   - Files: Frontend component + `api/routes/extraction.py` + migration

---

### Immediate (Next Sprint)

1. **Full Extraction Dataset + Human Validation** - 6h (reduced from 8h)
   - ✅ **V3-V6 COMPLETE:** 54 studies, 4 table orientations, multi-language, prose + figure fallbacks
   - ✅ **Step 1 COMPLETE:** Full corpus extraction → 92 studies (86 with data, 6 empty), 12,366 rows
   - **Step 2:** Human review of extracted data (spot-check ~10% of rows) ⬅️ **IN PROGRESS**
   - **Step 3:** Document FP/FN, calculate precision/recall
   - **Output:** `extraction_pipeline/outputs/full_corpus_for_validation.csv` (current: 12,366 rows)
   - Files: `extraction_pipeline/cli_v2.py`, `extraction_pipeline/combine_outputs.py`

2. **Domain-Specific Intervention Components** - 6h
   - Build LLM-based component extractor per `DOMAIN_CONFIGS` in `schemas.py`
   - Add CLI arg `--domain graduation|education|health`
   - Test on 3 domains
   - Files: `extraction_pipeline/pipeline.py`, `src/extraction/schemas.py`

3. **Study Design Filter in Evidence Panel** - 4h
   - Add dropdown to filter evidence by study design (RCT, DiD, etc.)
   - Files: `frontend/src/components/EvidencePanel.tsx`

4. **"I Don't Know" Explicit Refusal** - 2h
   - When retrieval confidence is below threshold, explicitly refuse to answer
   - Prevents hallucination when no good sources found
   - Files: `src/agents/devchat_agent.py`, `src/generation/claim_ledger.py`

### Short-Term

1. **~~Extraction Pipeline → Production Integration~~** - 12h ✅ **COMPLETE**
   - ✅ Supabase `extracted_estimates` table with 28 columns
   - ✅ API endpoints: `/extraction/studies/{id}/effects`, `/extraction/chatbot-context`, etc.
   - ✅ Supabase loader: `python -m extraction_pipeline.adapters.supabase_loader --all`
   - ✅ Chatbot integration models: `QuantitativeContext`, `ChatbotEffectContext`
   - Files: `api/routes/extraction.py`, `extraction_pipeline/adapters/supabase_loader.py`
   - **Next:** Run migration, upload data, build Evidence Panel component

2. **Embedding Model Comparison: Cohere vs Voyage 4** - 6h
   - Benchmark Voyage AI 4 (launched Jan 15, 2026) against current Cohere embed-v4
   - Metrics: retrieval accuracy, speed, cost per 1M tokens
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

6. **Self-Consistency** - 8h
   - Generate 3 answers with temperature > 0, select most consistent
   - Improves accuracy on complex synthesis questions
   - Files: `src/generation/claim_ledger.py`

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

5. **TruLens Evaluation** - 4h
   - Alternative RAG evaluation framework
   - Reference: https://www.trulens.org/

6. **Slack/Teams MCP Integration** - 20h
   - Let researchers query DevChat from Slack without switching apps
   - Example: `@devchat What effect sizes for cash transfers?`
   - Reference: [MCPs for Developers](https://www.oreilly.com/radar/mcps-for-developers-who-think-they-dont-need-mcps/)

7. **Context7-style Live Docs MCP** - 12h
   - Pull up-to-date methodology docs into agent context
   - Sources: 3ie methods guidance, PRISMA guidelines, Cochrane handbook
   - Reference: [Context7 MCP](https://block.github.io/goose/docs/mcp/context7-mcp)

8. **Aardvark** - 12h
   - Test security
---

## Success Metrics (Targets)

| Metric | Current | Target | Status |
|--------|---------|--------|--------|
| **Extraction: Study coverage** | 86/92 (93%) | 95%+ | 🟡 Close |
| **Extraction: Rows extracted** | 12,366 | - | ✅ |
| **Extraction: Table orientations** | 5 types | - | ✅ |
| **Extraction: Languages** | EN, ES, FR, PT | - | ✅ |
| **Extraction: Fallbacks** | Prose + Figures | - | ✅ |
| **Extraction: Precision** | ❓ Unknown | 90%+ | ❌ Needs ground truth |
| **Extraction: Recall** | ❓ Unknown | 80%+ | ❌ Needs ground truth |
| **Extraction: Coefficient accuracy** | ❓ Unknown | ±0.01 | ❌ Needs ground truth |
| **Extraction: SE accuracy** | ❓ Unknown | ±0.005 | ❌ Needs ground truth |
| **Extraction: Classification accuracy** | ~88% (self-measured) | 95%+ | 🟡 Needs validation |
| **Extraction: Confidence scores** | None | Per-row scores | ❌ Not started |
| **Extraction: Regression tests** | None | 30+ test cases | ❌ Not started |
| **RAG: Faithfulness** | 66.47% | 70%+ | 🟡 In progress |
| **RAG: Citation Recall** | 98.86% | 70%+ | ✅ |

---

## Completed This Session (Jan 31, 2026)

| Feature | Description |
|---------|-------------|
| **Modular Refactor** | Split pipeline.py into `core/`, `adapters/`, `postprocessing/` modules |
| **Error Handling** | `ErrorAccumulator` with stage context, `LLMFailureType` enum |
| **LLM Client** | Centralized `LLMClient` with caching, `sanitize_llm_response()` |
| **Schema Adapter** | `ColumnNames` constants, `normalize_authors()`, consistent field mapping |
| **Effect Size Assumptions** | Explicit `effect_size_assumption` column tracks calculation assumptions |
| **CLI v2** | New `cli_v2.py` with `--fast`, `--minimal`, `--no-prose`, `--no-figures` flags |

## Completed (Jan 29, 2026)

| Feature | Description |
|---------|-------------|
| **V4: SE-split parser** | Handles tables where SE is in separate rows below coefficients |
| **V4: European format** | Converts comma decimals (0,15) to dots (0.15) |
| **V4: Treatments-in-cols** | Extracts tables with treatment groups as column headers |
| **V5: Multi-language** | Spanish, French, Portuguese keywords for treatment detection |
| **V6: Figure extraction** | LLM extracts effects from figure captions when tables unavailable |
| **V6: Prose extraction** | LLM extracts effects from narrative text as fallback |
| **Regression check** | Verified V4 changes don't break previously working papers |

---

## References

- [PaperQA2](https://github.com/future-house/paper-qa) - Agentic RAG benchmark
- [Anthropic Contextual Retrieval](https://www.anthropic.com/news/contextual-retrieval) - 49% improvement technique
- [RAG-Fusion](https://arxiv.org/abs/2402.03367) - Multi-query retrieval
- [Lost in the Middle](https://arxiv.org/abs/2307.03172) - LLM context position bias
- [Binary Quantization](https://qdrant.tech/documentation/guides/quantization/) - Qdrant guide
- [Elicit](https://elicit.com/) - Systematic review automation
- [Scite](https://scite.ai/) - Smart Citations
- [TruLens](https://www.trulens.org/) - RAG evaluation framework


