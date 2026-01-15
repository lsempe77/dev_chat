# Extraction V3 Research Document

**Date:** January 10, 2025

**Goal:** Improve extraction accuracy following `EXTRACTION_VALIDATION_FRAMEWORK.md` guidelines

---

## 1. Current State Analysis

### 1.1 Metadata Extraction Baseline (V1)

**Overall:** 43 studies tested against ground truth

| Variable | Accuracy | Target | Gap |
|----------|----------|--------|-----|
| study_design | **97.7%** | 95% | ✅ Exceeded |
| country | **90.7%** | 95% | ⚠️ -4.3% |
| skills_comp | **90.7%** | 85% | ✅ Exceeded |
| targeting_women | 74.4% | 85% | 🔴 -10.6% |
| coaching_comp | 72.1% | 85% | 🔴 -12.9% |
| health_comp | 69.8% | 85% | 🔴 -15.2% |
| savings_comp | 69.8% | 85% | 🔴 -15.2% |
| social_comp | 65.1% | 85% | 🔴 -19.9% |

**Metadata Diagnosis:**
- Tier 1 (study_design, country): Good (90%+)
- Tier 2 components: Mediocre (65-90%), especially `social_comp`, `health_comp`, `savings_comp`
- Missing fields: `consumption_support`, `asset_transfer` (required by framework)

### 1.2 Outcome Extraction Comparison

| Metric | V1 Baseline | V2 (3-pass) | Target | Status |
|--------|-------------|-------------|--------|--------|
| Category Recall | 93.8% | 53.3% | 90%+ | 🔴 V2 regressed |
| Effect Size Mean Error | 30.116 | 0.233 | <0.1 | 🟡 Improved but not there |
| Accurate (<0.1 error) | 40.0% | 41.7% | 75%+ | 🔴 Far from target |
| Very Wrong (>=1.0 error) | 16.0% | 2.8% | 0% | 🟡 Better |

**Outcome Diagnosis:**
- V2 over-filtered outcomes (53.3% recall vs 93.8%)
- V2 fixed catastrophic errors (30.1 → 0.233 mean error)
- V2 self-verification too aggressive, discarding valid outcomes
- Still only 41.7% accurate within 0.1 threshold

---

## 2. Root Cause Analysis

### 2.1 Why Metadata Components Miss

**Problem Studies:** 121354848 missed 7/8 fields - needs investigation

Looking at patterns:
- `social_comp`: Most missed (28/43 correct = 65.1%)
- `health_comp`: Tied for second worst (30/43 = 69.8%)

**Hypothesis 1:** Component definitions may be ambiguous
- What exactly qualifies as "social integration" vs "coaching"?
- Framework says "Mentoring/coaching" vs "Social integration" - subtle difference

**Hypothesis 2:** LLM may be extracting from different parts of document
- Abstract mentions one thing, full text reveals different components

**Hypothesis 3:** Missing evidence_quote requirement
- Current V1 doesn't ask for quotes
- STAGE 2 of framework requires: "Quote the exact text supporting this"

### 2.2 Why Effect Size Extraction is Hard

**Ground Truth Distribution:**
- 72.9% of effect sizes are small (|d| < 0.2)
- Mean: 0.151, Median: 0.106
- Range: -1.08 to 1.38
- All 442 values ARE Cohen's d (already standardized)

**Problem 1: Studies report raw values, not Cohen's d**
User correctly pointed out:
> "not all studies use Cohen's d - they can use raw results, currency, percentages"

But ground truth column `d` shows ALL values are already Cohen's d. This means:
- Human coders manually computed d from whatever the study reported
- We need to replicate that computation, not just extract d directly

**Problem 2: V1 extracted wrong values**
- V1 errors: max error was 1663 (extracted raw value like "$603")
- V1 was grabbing percentage changes or dollar amounts, not effect sizes

**Problem 3: V2 was too rigid**
- V2 forced Cohen's d calculation even when unnecessary
- V2 self-verification discarded too many valid outcomes
- Result: 53.3% recall = lost half the outcomes

### 2.3 The Core Challenge

Studies report results in many formats:
1. **Cohen's d directly** (rare)
2. **Regression coefficients + SE** → need to calculate d
3. **Means + SDs by group** → need to calculate d
4. **Percentage changes** → need baseline + SD to calculate d
5. **Binary outcomes (odds ratios)** → different conversion

**The ground truth has:**
- Column `Coeff reg` - regression coefficient
- Column `SE reg` - standard error
- Column `N treatment`, `N control` - sample sizes
- Column `Formula Used` - how they calculated d
- Column `d` - the computed Cohen's d

We need to replicate this computation, not just extract.

---

## 3. V3 Strategy

### 3.1 What the Framework Requires (MUST follow)

```
STAGE 1: PRIMARY EXTRACTION
- Extract {value, confidence: 0-1, evidence_quote}
- Structured output (JSON schema)

STAGE 2: SELF-VERIFICATION (Provenance Check)
- "Quote the exact text supporting this"
- If quote not found → confidence *= 0.5

STAGE 3: SCHEMA VALIDATION
- study_design ∈ {RCT, Quasi-Experimental, Observational}
- country ∈ ISO_COUNTRY_LIST
- sample_size > 0 AND sample_size < 1,000,000
- effect_size ∈ [-5, 5]

STAGE 4: CROSS-SOURCE VALIDATION
- Compare with OpenAlex/Crossref if DOI available

STAGE 5: UNCERTAINTY FLAGGING
- If confidence < 0.7 → needs_review = true
```

### 3.2 Key V3 Changes

**Change 1: Unified extraction schema with confidence/evidence**
Currently: `{field: value}`
Should be: `{field: {value, confidence, evidence_quote, needs_review}}`

**Change 2: Extract raw statistical values, compute d separately**
Instead of asking LLM to calculate Cohen's d:
1. Extract: `coeff`, `se`, `n_treatment`, `n_control`, `means`, `sds`
2. Compute d programmatically using known formulas
3. Flag if insufficient data for computation

**Change 3: Less aggressive filtering**
- V2 discarded outcomes if self-verification failed
- V3: Keep but flag `needs_review = true, confidence = 0.3`

**Change 4: Add intervention component definitions to prompt**
Include explicit definitions from ground truth:
- `consumption_support`: "Cash or in-kind support to stabilize food security"
- `health_comp`: "Health services or health education component"
- `asset_transfer`: "Livestock, tools, or seed capital transfer"
- `skills_comp`: "Skills or vocational training"
- `savings_comp`: "Savings group or savings account component"
- `coaching_comp`: "Mentoring, coaching, or case management"
- `social_comp`: "Social integration, community activities, or social support"

### 3.3 Effect Size Computation Strategy

**Option A: Formula-based (Like ground truth)**
```python
# From regression coefficient
d = coeff / pooled_sd

# From t-statistic
d = t * sqrt(1/n1 + 1/n2)

# From means and SDs
d = (mean1 - mean2) / pooled_sd
pooled_sd = sqrt(((n1-1)*sd1^2 + (n2-1)*sd2^2) / (n1+n2-2))
```

**Option B: LLM-assisted with formulas**
- Show LLM the formulas
- Ask to identify which applies
- Extract required values
- Compute outside LLM

**Recommendation:** Option B - let LLM identify what's available, compute externally

---

## 4. V3 Implementation Plan

### Phase 1: Improve Metadata Extraction (4 hours)

1. **Add explicit component definitions to prompt**
2. **Require evidence quotes for each field**
3. **Add confidence scores (0-1)**
4. **Add missing fields:** `consumption_support`, `asset_transfer`

Expected improvement:
- `social_comp`: 65% → 80%
- `health_comp`: 70% → 85%
- Other components: 5-10% improvement

### Phase 2: Restructure Outcome Extraction (8 hours)

1. **Extract raw statistics table first**
   - Find all tables with results
   - Extract: outcome name, coefficient, SE, N, means, SDs
   
2. **Match to outcome categories**
   - Income, Assets, Savings, Expenditure, Poverty
   
3. **Compute Cohen's d externally**
   - Use extracted values + known formulas
   - Flag `needs_manual_review` if insufficient data
   
4. **Less aggressive filtering**
   - Keep outcomes, add confidence flags
   - Don't discard based on self-verification

Expected improvement:
- Category recall: 53% → 85%+ (restore what V2 lost)
- Effect size accuracy: 42% → 65%+

### Phase 3: Add Cross-Validation (4 hours)

1. **Cross-check sample sizes**
   - Total N should match treatment + control
   
2. **Cross-check effect sizes**
   - d should be consistent with coefficient/SE
   
3. **Flag inconsistencies**
   - `needs_review = true` if math doesn't check out

---

## 5. Prompt Engineering Improvements

### 5.1 Intervention Components (V3)

```
You are extracting intervention components from an Ultra-Poor Graduation study.

For each component, determine if it is PRESENT (1) or ABSENT (0) based on the study's 
intervention design. Provide an evidence quote for each decision.

COMPONENT DEFINITIONS (be precise):

1. consumption_support (1/0):
   "Cash or in-kind support to stabilize food security and prevent households from 
   selling assets to survive"
   - Examples: cash transfers, food rations, consumption stipends
   
2. health_comp (1/0):
   "Health services or health education component"
   - Examples: health training, clinic referrals, health checkups
   
3. asset_transfer (1/0):
   "Livestock, tools, or seed capital to provide foundation for income-generation"
   - Examples: goats, chickens, agricultural tools, seed capital for business
   
4. skills_comp (1/0):
   "Skills or vocational training"
   - Examples: business training, technical skills, financial literacy training
   
5. savings_comp (1/0):
   "Savings group or savings account component"
   - Examples: village savings groups, savings accounts, mandatory savings
   
6. coaching_comp (1/0):
   "Mentoring, coaching, or regular home visits by case managers"
   - Examples: weekly visits, mentoring, life skills coaching
   
7. social_comp (1/0):
   "Social integration, community activities, or social support networks"
   - Examples: community sensitization, social network building, group meetings
   
For each component, output:
{
  "value": 0 or 1,
  "confidence": 0.0 to 1.0,
  "evidence_quote": "exact quote from document"
}

If unsure, set confidence < 0.7 and needs_review = true.
```

### 5.2 Outcome Extraction (V3)

```
You are extracting outcome data from an impact evaluation study.

STEP 1: Find all results tables in the document.

STEP 2: For each outcome row, extract:
- outcome_name: Specific measure (e.g., "Total assets value (USD)")
- outcome_category: One of [Income, Assets, Savings, Expenditure, Poverty]
- coefficient: Treatment effect estimate (if regression)
- standard_error: SE of treatment effect
- t_statistic: t-stat if available
- n_treatment: Sample size in treatment group
- n_control: Sample size in control group
- mean_treatment: Mean in treatment group (if available)
- mean_control: Mean in control group (if available)
- sd_treatment: Standard deviation in treatment (if available)
- sd_control: Standard deviation in control (if available)

STEP 3: Do NOT calculate Cohen's d yourself. Just extract the raw values.

Output format:
{
  "outcomes": [
    {
      "outcome_name": "...",
      "outcome_category": "...",
      "coefficient": null or float,
      "standard_error": null or float,
      "t_statistic": null or float,
      "n_treatment": null or int,
      "n_control": null or int,
      "mean_treatment": null or float,
      "mean_control": null or float,
      "sd_treatment": null or float,
      "sd_control": null or float,
      "evidence_table": "Name of table or section where found",
      "confidence": 0.0 to 1.0
    }
  ]
}
```

### 5.3 Cohen's d Computation (Python) - VERIFIED FORMULAS

**Reverse-engineered from ground truth:**

```python
import numpy as np

def compute_cohens_d(outcome: dict) -> tuple[float | None, str]:
    """
    Compute Cohen's d from extracted values.
    Returns (d, method_used) or (None, "insufficient_data")
    
    VERIFIED: Formula 5 from ground truth is EXACT:
    d = t * sqrt(1/n1 + 1/n2) where t = coef/se
    """
    coef = outcome.get('coefficient')
    se = outcome.get('standard_error')
    n1 = outcome.get('n_treatment')
    n2 = outcome.get('n_control')
    n_total = outcome.get('n_total')
    
    # FORMULA 5: t-stat with treatment/control sample sizes (VERIFIED EXACT)
    if all(x is not None for x in [coef, se, n1, n2]) and se != 0:
        t = coef / se
        d = t * np.sqrt(1/n1 + 1/n2)
        return d, "formula_5_exact"
    
    # FORMULA 6: When only N_total available (need to assume 50/50 split)
    if all(x is not None for x in [coef, se, n_total]) and se != 0:
        # Assume 50/50 split if not specified
        n1_est = n_total / 2
        n2_est = n_total / 2
        t = coef / se
        d = t * np.sqrt(1/n1_est + 1/n2_est)
        return d, "formula_6_approx"
    
    return None, "insufficient_data"
```

**Key insight from reverse-engineering:**
- Formula 5 (32% of outcomes): Has N treatment + N control → EXACT formula
- Formula 6 (68% of outcomes): Only N total → Assumes 50/50 split
- Ground truth uses: `d = (coef/se) * sqrt(1/n1 + 1/n2)`

---

## 6. Evaluation Plan

### 6.1 Test Set

Same 43 studies from 8WR QEX Combined.xlsx + master_UPG.csv

### 6.2 Metrics to Track

**Metadata:**
| Variable | V1 Baseline | V3 Target |
|----------|-------------|-----------|
| study_design | 97.7% | 98%+ |
| country | 90.7% | 95% |
| health_comp | 69.8% | 85% |
| skills_comp | 90.7% | 92% |
| savings_comp | 69.8% | 85% |
| coaching_comp | 72.1% | 85% |
| social_comp | 65.1% | 80% |
| targeting_women | 74.4% | 85% |

**Outcomes:**
| Metric | V1 | V2 | V3 Target |
|--------|-----|-----|-----------|
| Category Recall | 93.8% | 53.3% | 90%+ |
| Effect Size <0.1 error | 40% | 42% | 70%+ |
| Mean Error | 30.1 | 0.233 | <0.15 |
| Very Wrong (>=1.0) | 16% | 2.8% | 0% |

### 6.3 Success Criteria

1. **Metadata:** All components ≥ 80% accuracy
2. **Outcomes:** Category recall ≥ 85% AND effect size accuracy ≥ 60%
3. **No regressions:** V3 should not be worse than V1/V2 on any metric

---

## 7. Next Steps

1. [ ] Implement V3 metadata extraction with evidence quotes
2. [ ] Test on 10 studies, compare to V1 baseline
3. [ ] Implement V3 outcome extraction (raw values + compute d)
4. [ ] Test on 10 studies, compare to V1/V2
5. [ ] If metrics met, run full 43-study evaluation
6. [ ] Document final results in BASELINE_RESULTS.md

---

## Appendix: Key Files

- `EXTRACTION_VALIDATION_FRAMEWORK.md` - Requirements document
- `8WR QEX Combined.xlsx` - Ground truth outcomes (443 rows, 43 studies)
- `master_UPG.csv` - Ground truth metadata (118 rows)
- `evaluation/baseline_extraction_results.json` - V1 baseline (43 studies)
- `evaluation/improved_extraction_results.json` - V2 results
- `evaluation/outcome_extraction_v2.py` - V2 implementation
