# Outcome Extraction Pipeline - Technical Documentation

## 1. The Problem

**Goal**: Extract structured data from impact evaluation PDFs:
- Outcome names (e.g., "Gross consumption (daily, USD/adult eq.)")
- Treatment effect coefficients (e.g., 0.15)
- Standard errors (e.g., 0.05)  
- Cohen's d effect sizes (e.g., 0.0904)

**Why it's hard**: Academic tables are complex:
```
| Outcome                 | Treatment 6mo | Treatment 18mo | Control Mean |
|-------------------------|---------------|----------------|--------------|
| Gross consumption (USD) | 0.15***       | 0.22***        | 2.45         |
|                         | (0.05)        | (0.06)         | (1.10)       |
```
- Multi-row headers with merged cells
- Multiple time points (6mo, 18mo, 3yr)
- Multiple treatment arms (Full, Capital Only, etc.)
- SEs in parentheses below coefficients
- Footnotes with significance stars

---

## 2. Data Flow

```
PDF (R2 Storage)
     │
     ▼
MineRU (PDF → JSON with markdown + HTML tables)
     │
     ▼
┌────────────────────────────────────────────────────┐
│  STAGE 1: Find outcome names in tables             │
│  Input: Tables as markdown                         │
│  Output: List of outcome names + which table       │
│  Result: 100% recall (found all 71 GT outcomes)    │
└────────────────────────────────────────────────────┘
     │
     ▼
┌────────────────────────────────────────────────────┐
│  STAGE 2: Extract numbers for each outcome         │
│  Input: Outcome name + its table                   │
│  Output: coefficient, SE, sample_size              │
│  Result: 76% have coefficient, 55% have SE         │
└────────────────────────────────────────────────────┘
     │
     ▼
┌────────────────────────────────────────────────────┐
│  STAGE 3: Compute Cohen's d                        │
│  Formula: d = 2 * (coef/SE) / sqrt(N)              │
│  Result: 61% have Cohen's d, 80% accuracy          │
└────────────────────────────────────────────────────┘
```

---

## 3. Ground Truth

**Source**: `evaluation/matched_studies_r2.json`

**5 Test Studies** (used for development):
| Study | Author | GT Outcomes |
|-------|--------|-------------|
| 121058356 | Bossuroy et al. | 44 |
| 121058359 | Misha et al. | 3 |
| 121058364 | Maldonado et al. | 2 |
| 121058367 | Alderman et al. | 16 |
| 121058368 | Banerjee et al. | 6 |
| **Total** | | **71** |

**Full dataset**: 43 studies, 442 outcomes

**GT Structure**:
```json
{
  "name": "Gross consumption (daily, USD/adult eq.)",
  "effect_size_d": 0.0904,
  "se": 0.0299
}
```

**Critical**: GT computes Cohen's d using **t-statistic formula**:
```
d = 2 * t / sqrt(N)    where t = coefficient / SE
```

---

## 4. Version History

| Version | Recall | What Changed |
|---------|--------|--------------|
| V10 | 42% | Baseline |
| V11 | 71% | Added ensemble (Claude + GPT-4o) |
| V12 | 62% | Tried aggressive deduplication - hurt recall |
| V13 | 72% | Lowered thresholds, greedy matching |
| V16 | 100% | Switched to GPT-4o, focused on 5 studies |
| V17d | 100% | Removed slow LLM matching, pure embeddings |

**Key lesson**: Lower matching thresholds = higher recall. V17d uses 0.25 embedding similarity threshold.

---

## 5. Current Results

### Stage 1: Outcome Identification
- **Recall: 100%** (71/71 GT outcomes found)
- Precision: 19% (382 extracted, 71 in GT)
- Over-extraction is acceptable - we match to GT

### Stage 2: Parameter Extraction
- **Coefficient extraction: 76%** (262/343)
- **SE extraction: 55%** (188/343)
- Gap: Some outcomes don't have clear coefficient rows

### Stage 3: Cohen's d
- **Coverage: 61%** (208/342 have Cohen's d)
- **Accuracy: 80%** on exact-name GT matches
- Perfect matches: "Gross consumption" → 0.0904 (matches GT exactly)

---

## 6. The Main Problems

### Problem 1: LLM collapses multi-dimensional tables

**Critical Issue**: Tables have multiple dimensions (treatment arms × followup periods), but LLM extracts only ONE value per outcome.

Example Table 1 from Bossuroy:
```
| Outcome         | Capital 6mo | Psycho 6mo | Full 6mo | Capital 18mo | Psycho 18mo | Full 18mo |
|-----------------|-------------|------------|----------|--------------|-------------|-----------|
| Consumption     | 0.15        | 0.09       | 0.25     | 0.12         | 0.18        | 0.25      |
| Food security   | 0.52        | 0.21       | 0.66     | 0.50         | 0.47        | 0.63      |
| Food score      | 4.17        | 2.71       | 6.01     | 3.69         | 2.78        | 6.11      |
```

**LLM extracted**: 3 outcomes (one value each)
**Human extracted**: 18 rows (3 outcomes × 3 arms × 2 followups)

The LLM completely misses the **treatment arm** and **followup period** dimensions.

### Problem 2: Wrong table numbering

LLM labeled the first results table as "Table 2" when it's actually "Table 1". This causes:
- Confusion when cross-referencing
- Mismatch with paper citations

### Problem 3: Which column to extract?

Tables have multiple columns for different time points:
```
| Outcome     | 6 months | 18 months | 36 months |
|-------------|----------|-----------|-----------|
| Consumption | 0.10     | 0.15      | 0.22      |
```

**We don't know which column GT used.** Currently extracting first/main column.

### Problem 4: Which treatment arm?

Some studies have multiple treatment arms:
```
| Outcome     | Full Treatment | Capital Only | Training Only |
|-------------|----------------|--------------|---------------|
| Income      | 0.25           | 0.15         | 0.08          |
```

**We don't know which arm GT used.** Currently extracting first/ITT column.

### Problem 5: SE parsing

SEs are in parentheses below coefficients:
```
| Outcome     | Treatment |
|-------------|-----------|
| Consumption | 0.15***   |
|             | (0.05)    |  ← This is the SE
```

LLM sometimes misses this or confuses with CI. **55% extraction rate needs improvement.**

### Problem 6: Duplicate GT outcomes

Same outcome appears multiple times in GT with different effect sizes (different time points):
```json
{"name": "Income", "effect_size_d": 0.08},
{"name": "Income", "effect_size_d": 0.12},
{"name": "Income", "effect_size_d": 0.15}
```

**We match to first occurrence, may be wrong.**

### Problem 7: Missing prose extraction

**Authors highlight key findings in the paper text**, not just tables:
- Abstract: "We find a 15% increase in consumption (p<0.01)"
- Results section: "The treatment effect on income was 0.25 SD (SE=0.08)"
- Discussion: "The largest effects were on savings (d=0.32)"

**Currently we only extract from tables.** The prose often contains:
- The most policy-relevant outcomes
- Effect sizes in standardized units (SD, Cohen's d)
- Clearer interpretation of which time point/arm is "main"

This is a **TODO** for future versions.

---

## 7. Key Files

| File | Purpose |
|------|---------|
| `extractor_v17d.py` | Stage 1: Find outcomes |
| `extractor_v17d_stage2.py` | Stage 2: Extract coef/SE |
| `cohens_d_pipeline.py` | Stage 3: Compute Cohen's d |
| `v16_results.json` | Stage 1 output |
| `v17d_stage2_results.json` | Stage 2 output |
| `v17d_cohens_d_results.json` | Stage 3 output |

---

## 8. Next Steps (To Discuss)

1. **How to identify correct time point?**
   - Option A: Extract ALL columns, let user pick
   - Option B: Prefer "endline" or longest follow-up
   - Option C: Add time point to GT for matching

2. **How to identify correct treatment arm?**
   - Option A: Extract ALL arms
   - Option B: Look for "ITT" or "Full Treatment"
   - Option C: Add arm info to GT

3. **How to improve SE extraction (55% → 80%)?**
   - Better prompting for parentheses parsing
   - Regex fallback after LLM

4. **Scale to 43 studies?**
   - Current: 5 studies, 71 outcomes
   - Full: 43 studies, 442 outcomes
   - Need to validate approach works at scale

---

## 9. Cohen's d Formula

**GT uses this formula** (verified by reverse-engineering):
```
t = coefficient / SE
d = 2 * t / sqrt(N)
```

**Example**:
- Coefficient: 0.15
- SE: 0.05
- N: 4405
- t = 0.15 / 0.05 = 3.0
- d = 2 × 3.0 / √4405 = 6.0 / 66.37 = **0.0904** ✅

This matches GT exactly for "Gross consumption".
