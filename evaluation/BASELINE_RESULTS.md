# Extraction Baseline Results

**Date:** January 9, 2025  
**Model:** Claude 3.5 Sonnet (anthropic/claude-3.5-sonnet via OpenRouter)  
**Test Set:** 43 poverty graduation studies with ground truth  

---

## Executive Summary

| Extraction Type | Metric | Result | Status |
|-----------------|--------|--------|--------|
| **Metadata** | Overall Accuracy | 82.5% | ✓ Good |
| **Metadata** | Study Design | 97.7% | ✓ Excellent |
| **Metadata** | Components (avg) | 72.6% | ⚠ Needs work |
| **Outcomes** | Category Recall | 93.8% | ✓ Good |
| **Outcomes** | Effect Size Extracted | 68.2% | ⚠ Missing 32% |
| **Outcomes** | Effect Size Accurate (<0.1) | **40.0%** | 🔴 **TERRIBLE** |
| **Outcomes** | Effect Size Usable (<0.5) | 72.0% | ⚠ Borderline |
| **Outcomes** | Sample Size Extracted | 64.7% | ⚠ OK |
| **Outcomes** | Outcome Count | 201/442 | 🔴 45% coverage |

### Critical Finding: Effect Sizes Are Wrong
- **Mean absolute error: 30.1** (should be <0.1 for Cohen's d)
- **Max error: 1663** 
- LLM extracts raw percentages/coefficients instead of standardized effect sizes
- Example: `extracted=14.4` vs `ground_truth=0.102`

---

## 1. Metadata Extraction Baseline

### 1.1 Test Configuration
- **Source:** R2 JSON documents (MineRU processed)
- **Ground Truth:** 8WR QEX Combined.xlsx + master_UPG.csv
- **Matched Studies:** 43 (100% of ground truth)
- **Prompt Type:** Zero-shot extraction with field definitions

### 1.2 Per-Field Accuracy

| Field | Accuracy | Errors | Notes |
|-------|----------|--------|-------|
| study_design | **97.7%** | 1 | Only 1 error (42/43) |
| country | **90.7%** | 4 | Spelling, multi-country |
| skills_comp | **90.7%** | 4 | Strong |
| targeting_women | 74.4% | 11 | Moderate |
| coaching_comp | 72.1% | 12 | Moderate |
| health_comp | 69.8% | 13 | Needs improvement |
| savings_comp | 69.8% | 13 | Needs improvement |
| social_comp | **65.1%** | 15 | Lowest - needs improvement |

### 1.3 Error Analysis

#### Study Design Errors (1 error)
| Study | Author | Extracted | Ground Truth | Issue |
|-------|--------|-----------|--------------|-------|
| 121498842 | Mahecha et al. | RCT | Quasi-Experimental | Misclassification |

#### Country Errors (4 errors)
| Study | Author | Extracted | Ground Truth | Issue |
|-------|--------|-----------|--------------|-------|
| 121058373 | Banerjee et al. | None | Ghana | Failed extraction |
| 121354848 | Bouguen and Dillon | Niger | Burkina | Wrong country |
| 122182713 | IPA | Philippines | Phillipines | GT spelling error (LLM correct!) |
| 122182715 | Beam et al. | Multiple | Uganda | Multi-site study |

### 1.4 Intervention Component Error Patterns

**Common Error: False Positives (GT=0, Extracted=1)**
- **health_comp:** 10 of 13 errors are false positives
- **savings_comp:** 11 of 13 errors are false positives  
- **coaching_comp:** 10 of 12 errors are false positives
- **social_comp:** 11 of 15 errors are false positives
- **targeting_women:** 9 of 11 errors are false positives

**Root Cause Analysis:**
1. **Implicit components** - LLM infers components from context
2. **Terminology variation** - "coaching" vs "mentoring" vs "case management"
3. **Bundled interventions** - Hard to distinguish individual components
4. **Conservative GT coding** - Ground truth may only code explicit components

### 1.5 Problematic Studies

Study **121354848** (Bouguen and Dillon, Burkina) had 6 errors:
- Wrong country (Niger vs Burkina)
- Wrong health_comp, skills_comp, savings_comp
- Missing coaching_comp, social_comp, targeting_women

---

## 2. Outcome Extraction Baseline

### 2.1 Test Configuration
- **Source:** R2 JSON documents (full content, up to 80k chars)
- **Ground Truth:** 442 outcomes across 43 studies
- **Prompt Type:** Zero-shot with outcome category guidance
- **Timeout:** 180 seconds per study

### 2.2 Summary Metrics

| Metric | Value | Notes |
|--------|-------|-------|
| Studies Processed | 43 | 100% |
| Ground Truth Outcomes | 442 | From 8WR Excel |
| Extracted Outcomes | 201 | Aggregated |
| Avg Outcomes/Study (GT) | 10.3 | Many granular outcomes |
| Avg Outcomes/Study (Ext) | 4.7 | Main outcomes only |
| **Category Recall** | **93.8%** | Found right categories |

### 2.3 Category Recall Distribution

| Category Recall | Count | Percentage |
|-----------------|-------|------------|
| 100% | 35 | **81.4%** |
| 75-99% | 4 | 9.3% |
| 50-74% | 4 | 9.3% |
| <50% | 0 | 0% |

### 2.4 Low Category Recall Studies (4 studies)

| Study | Author | Country | Recall | Missing Categories |
|-------|--------|---------|--------|-------------------|
| 121058372 | Bandiera et al. | Bangladesh | 67% | Savings |
| 121294841 | Premand et al. | Niger | 50% | Savings, Expenditure |
| 121297660 | Leight et al. | Somalia | 67% | Income |
| 121475071 | Macours et al. | Nicaragua | 50% | Assets |

### 2.5 Outcome Count Analysis

**Under-Extraction (GT has many, LLM finds few):**
| Study | Extracted/GT | Ratio | Notes |
|-------|-------------|-------|-------|
| 121058356 | 6/44 | 14% | Niger - many time points in GT |
| 121058373 | 5/36 | 14% | Ghana - granular outcomes |
| 121295229 | 5/36 | 14% | India - multiple outcomes |

**Over-Extraction (LLM finds more categories than GT):**
| Study | Extracted/GT | Ratio | Notes |
|-------|-------------|-------|-------|
| 121294873 | 5/1 | 500% | Vietnam - GT only has Poverty |
| 121336027 | 4/1 | 400% | Bangladesh - GT only has Poverty |
| 121378494 | 4/1 | 400% | Somalia - GT only has Assets |

### 2.6 Category Coverage Analysis

| Category | Studies Extracted | GT Studies | Coverage |
|----------|------------------|------------|----------|
| Income | 37 | 31 | 119% |
| Assets | 33 | 31 | 106% |
| Expenditure | 33 | 28 | 118% |
| Poverty | 26 | 8 | 325% |
| Savings | 25 | 22 | 114% |

**Interpretation:** LLM tends to over-extract categories. Particularly for Poverty (finds 26 when GT only has 8), likely because LLM includes any poverty-related outcome.

---

## 3. Effect Size Accuracy Analysis (THE REAL PROBLEM)

### 3.1 Effect Size Extraction Rate

| Metric | Extracted | Ground Truth | Notes |
|--------|-----------|--------------|-------|
| Has effect_size_d | 137/201 (68.2%) | 442/442 (100%) | Missing 32% |
| Has standard_error | 95/201 (47.3%) | 442/442 (100%) | Missing 53% |
| Has n_treatment | 130/201 (64.7%) | 146/442 (33%) | Better than GT! |
| Has n_control | 129/201 (64.2%) | - | - |

### 3.2 Effect Size Accuracy (When Extracted)

| Error Threshold | Count | Percentage | Status |
|-----------------|-------|------------|--------|
| < 0.1 (accurate) | 40 | **40.0%** | 🔴 TERRIBLE |
| < 0.5 (usable) | 72 | 72.0% | ⚠ Borderline |
| ≥ 0.5 (wrong) | 28 | 28.0% | 🔴 BAD |

**Statistics:**
- Mean absolute error: **30.116** (should be ~0)
- Median error: 0.166
- Max error: **1663.190**

### 3.3 Root Cause: Format Mismatch

The LLM extracts **raw values** instead of **standardized Cohen's d**:

| Study | Category | Extracted | GT (Cohen's d) | Issue |
|-------|----------|-----------|----------------|-------|
| 121295428 | Income | 14.400 | 0.102 | Raw coefficient |
| 121294984 | Expenditure | 8.385 | 0.103 | Percentage? |
| 121295428 | Assets | 7.560 | 0.546 | SD units? |
| 121058368 | Savings | 2.000 | 0.178 | 200% change |
| 121058368 | Income | 0.910 | 0.227 | 91% change |

**The LLM doesn't understand that GT uses standardized effect sizes (Cohen's d = mean_diff / pooled_SD)**

### 3.4 Example Extractions

```
121058356: Income - Off-farm business profits monthly
  d=None, SE=None, n_t=None, n_c=None
  evidence: "Monthly revenues increase by $36-$62..."

121058364: Income - Monthly per capita income  
  d=0.12, SE=6.03, n_t=719, n_c=286
  evidence: "4.79 USD PPP increase..."
  
121058368: Income - Non-farm income
  d=0.91, SE=None, n_t=666, n_c=1940  
  evidence: "91 percent increase in non-farm income"
  ^^^ WRONG: 0.91 is the percentage, not Cohen's d!
```

---

## 4. Key Insights

### 3.1 Metadata Strengths
- ✅ Study design nearly perfect (97.7%)
- ✅ Country extraction strong (90.7%)
- ✅ Skills component well-identified (90.7%)

### 3.2 Metadata Weaknesses
- ⚠ Binary components prone to false positives
- ⚠ Social component worst (65.1%)
- ⚠ Need explicit component definitions

### 3.3 Outcome Strengths
- ✅ Category recall excellent (93.8%)
- ✅ 81.4% perfect category match
- ✅ Finds outcomes across all categories

### 3.4 Outcome Weaknesses
- ⚠ Over-extracts categories (esp. Poverty)
- ⚠ Misses some granular outcomes
- ⚠ Effect sizes often null (needs table parsing)

---

## 4. Improvement Targets

### 4.1 Metadata Extraction
| Field | Current | Target | Gap |
|-------|---------|--------|-----|
| study_design | 97.7% | 99% | +1.3% |
| country | 90.7% | 98% | +7.3% |
| skills_comp | 90.7% | 95% | +4.3% |
| targeting_women | 74.4% | 90% | **+15.6%** |
| coaching_comp | 72.1% | 90% | **+17.9%** |
| health_comp | 69.8% | 90% | **+20.2%** |
| savings_comp | 69.8% | 90% | **+20.2%** |
| social_comp | 65.1% | 90% | **+24.9%** |

### 4.2 Outcome Extraction
| Metric | Current | Target | Gap |
|--------|---------|--------|-----|
| Category Recall | 93.8% | 98% | +4.2% |
| Perfect Category Match | 81.4% | 95% | +13.6% |
| Effect Size Extraction | ~10% | 80% | **+70%** |

---

## 5. Recommended Improvements

### Priority 1: Component Definitions
Add explicit definitions to reduce false positives:
```
health_comp: "Explicit healthcare access, health insurance, or health education 
              mentioned as part of the intervention"
skills_comp: "Vocational training, business skills, or financial literacy 
              explicitly provided"
```

### Priority 2: Self-Verification
Add evidence quotes for each extraction to enable human review:
```json
{
  "coaching_comp": 0,
  "coaching_evidence": "No mention of regular mentoring or case management visits"
}
```

### Priority 3: Table Parsing for Effect Sizes
- Parse MineRU structured tables
- Extract effect sizes from results tables
- Match to outcome categories

### Priority 4: Category Strictness
- Add stricter category definitions
- Reduce Poverty over-extraction
- Match GT category coding conventions

---

## 6. Files Generated

| File | Description |
|------|-------------|
| [baseline_extraction_results.json](baseline_extraction_results.json) | Full metadata extraction results |
| [outcome_extraction_results.json](outcome_extraction_results.json) | Full outcome extraction results |
| [baseline_error_analysis.json](baseline_error_analysis.json) | Detailed error analysis |
| [matched_studies_r2.json](matched_studies_r2.json) | Study-to-R2-file mapping |
| [extraction_test_dataset.json](extraction_test_dataset.json) | Ground truth export |

---

## 7. Reproducibility

### Run Metadata Baseline
```bash
python evaluation/run_baseline_extraction.py
```

### Run Outcome Baseline
```bash
python evaluation/outcome_extraction.py
```

### Run Error Analysis
```bash
python evaluation/analyze_baselines.py
```

### Requirements
- OpenRouter API key (OPENROUTER_API_KEY)
- Cloudflare R2 credentials
- Python 3.10+, httpx, boto3

---

*Generated: January 9, 2025*
