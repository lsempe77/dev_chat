# V3 Extraction Evaluation - Final Report (with Robust JSON Parsing)

## Executive Summary

V3 extraction with robust JSON parsing was run on all 43 matched studies. **The JSON parsing fix eliminated all metadata failures.**

### Metadata Accuracy - V3 vs V1 Baseline

| Field | V1 Baseline | V3 Result | Change |
|-------|-------------|-----------|--------|
| study_design | 97.7% | **100.0%** | **+2.3%** ✓ |
| country | 90.7% | **90.7%** | 0% |
| skills_comp | 90.7% | **90.7%** | 0% |
| savings_comp | 69.8% | **72.1%** | **+2.3%** ✓ |
| health_comp | 69.8% | **69.8%** | 0% |
| social_comp | 65.1% | **69.8%** | **+4.7%** ✓ |
| coaching_comp | 72.1% | 69.8% | -2.3% |
| targeting_women | 74.4% | 65.1% | -9.3% |

**Metadata failures: 0/43** (previously 5/43 with malformed JSON)

---

## ⚠️ CRITICAL ISSUE: Outcome Discovery

**V3 only finds 53.6% of outcomes** - nearly half of all outcomes in the ground truth are missed.

| Metric | Value | Assessment |
|--------|-------|------------|
| Ground Truth Outcomes | 442 | - |
| Extracted Outcomes | 237 | **46.4% missed** |
| **Overall Recall** | **53.6%** | ❌ Needs improvement |

### Category-Level Recall Analysis

| Category | GT Count | Extracted | **Missed** | Recall |
|----------|----------|-----------|------------|--------|
| Income | 116 | 66 | **50** | 56.9% |
| Assets | 153 | 41 | **112** | 26.8% ❌ |
| Savings | 44 | 34 | **10** | 77.3% ✓ |
| Expenditure | 114 | 45 | **69** | 39.5% |
| Poverty | 15 | 51 | *-36* | 340%* |

*Poverty is over-extracted due to misclassification from other categories.

### Why Outcomes Are Missed

1. **Single-pass extraction**: One LLM call may not find all outcomes scattered across the document
2. **Table complexity**: Outcomes buried in complex multi-panel tables
3. **Duplicate detection**: Some outcomes may be extracted but not matched to GT
4. **Category confusion**: Outcomes extracted but assigned wrong category

### Impact on Meta-Analysis

Missing 46% of outcomes means:
- Incomplete effect size distribution
- Potential bias if missed outcomes differ systematically
- Reduced statistical power for synthesis

---

### Key Improvements from JSON Fix

| Metric | Before Fix | After Fix | Improvement |
|--------|------------|-----------|-------------|
| study_design | 88.4% | 100.0% | +11.6% |
| country | 79.1% | 90.7% | +11.6% |
| skills_comp | 79.1% | 90.7% | +11.6% |
| coaching_comp | 55.8% | 69.8% | +14.0% |
| Metadata failures | 5/43 | 0/43 | **Eliminated** |

### Outcomes Extraction

| Metric | V3 Result |
|--------|-----------|
| Ground Truth Outcomes | 442 |
| Extracted Outcomes | 237 |
| Recall | 53.6% |
| Cohen's d Computed | 88 (37.1% of extracted) |
| Mean |d| Error | 0.1015 |
| Median |d| Error | 0.0513 |

### Cohen's d Error Distribution

| Error Threshold | Count | Cumulative % |
|-----------------|-------|--------------|
| ≤ 0.01 | 16 | 25.0% |
| ≤ 0.05 | 31 | 48.4% |
| ≤ 0.1 | 40 | 62.5% |
| ≤ 0.2 | 52 | 81.2% |
| ≤ 0.5 | 63 | 98.4% |
| ≤ 1.0 | 64 | 100% |

**Key Finding**: 81% of computed Cohen's d values have error < 0.2

### Cohen's d by Computation Method

| Method | Count | Mean Error | Median Error |
|--------|-------|------------|--------------|
| formula_6_n_total | 51 | 0.092 | 0.056 |
| formula_5_exact | 12 | 0.131 | 0.010 |
| means_and_sds | 1 | 0.251 | 0.251 |

### Category Recall

| Category | GT Count | V3 Extracted | Recall |
|----------|----------|--------------|--------|
| Savings | 44 | 34 | 77.3% |
| Income | 116 | 66 | 56.9% |
| Expenditure | 114 | 45 | 39.5% |
| Assets | 153 | 41 | 26.8% |
| Poverty | 15 | 51 | 340.0%* |

*Over-extraction in Poverty category - classification issue.

### D Computation Analysis

| Computation Method | Count | % of Extracted |
|--------------------|-------|----------------|
| insufficient_data | 149 | 62.9% |
| formula_6_n_total | 63 | 26.6% |
| formula_5_exact | 21 | 8.9% |
| means_and_sds | 4 | 1.7% |

**Root Cause**: 62.9% of outcomes lack standard errors for d computation.

## What V3 Achieves

1. **100% study_design accuracy** - Exceeds V1 baseline
2. **Evidence quotes** for provenance tracking
3. **Confidence scores** for each extracted field
4. **Zero metadata failures** with robust JSON parsing
5. **Programmatic Cohen's d** using verified formula
6. **81% of d values** within 0.2 of ground truth

## Remaining Challenges for V4 (Priority Order)

1. **🔴 Outcome discovery**: Only 53.6% recall - **46% of outcomes missed**
   - Assets category worst at 26.8% recall (112 outcomes missed)
   - Need multi-pass extraction or table-focused approach
   
2. **🟠 SE extraction**: 62.9% of found outcomes missing standard errors
   - Can't compute Cohen's d without SE
   - Need targeted table parsing
   
3. **🟡 Category misclassification**: Poverty 340% over-extracted
   - Outcomes being assigned wrong category
   
4. **🟡 targeting_women**: -9.3% vs baseline (needs prompt tuning)

## Technical Details

### Files Generated
- `v3_extraction_results.json`: Full extraction data with comparison
- `v3_extraction_report.md`: Per-study breakdown
- `v3_extraction_results_partial.json`: Incremental saves

### Formula Used
```python
d = (coef / se) * np.sqrt(1/n1 + 1/n2)
```

## Conclusion

With robust JSON parsing, V3 now **matches or exceeds V1 baseline** on most metadata fields while adding:
- Evidence quotes for every extraction
- Confidence scores
- Programmatic Cohen's d computation

The verified formula works accurately when data is available - **81% of d values within 0.2 of GT**. 

**However, the critical bottleneck is outcome discovery** - only 53.6% of outcomes are found. Even perfect d computation is useless if we miss half the outcomes.

## Next Steps (V4) - Priority Order

1. **🔴 Multi-pass outcome extraction**: Run multiple extraction passes to find more outcomes
   - Target: >80% recall (currently 53.6%)
   - Focus on Assets category (26.8% recall)
   
2. **🔴 Table-focused parsing**: Extract and parse tables separately
   - Tables contain most quantitative outcomes
   - Current approach misses table structure
   
3. **🟠 Targeted SE extraction**: Separate prompt for standard errors
   - Currently 62.9% of found outcomes missing SE
   
4. **🟡 Category normalization**: Fix Poverty over-classification (340%)

5. **🟡 targeting_women prompt tuning**: Currently -9.3% vs baseline
