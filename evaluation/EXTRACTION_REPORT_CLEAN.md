# Outcome Extraction Evaluation Report

**Date:** January 12, 2026 | **Studies:** 43 | **Ground Truth Outcomes:** 442

---

## Bottom Line

| Component | Best Version | Performance | Status |
|-----------|--------------|-------------|--------|
| **Metadata** | V1 | 100% accuracy | ✅ **WORKS** |
| **Finding Outcomes** | V5 | 25% recall, 21% precision | ❌ Poor |
| **Effect Sizes (d)** | V3 | 79% accuracy | ⚠️ Okay |
| **Coefficients** | V4 | 62% accuracy | ❌ Poor |
| **Standard Errors** | V3 | 77% accuracy | ⚠️ Okay |
| **Sample Sizes** | V4 | 85% accuracy | ⚠️ Okay |
| **Confidence Intervals** | None | 0% extracted | ❌ **MISSING** |

---

## 1. What Works: Metadata (V1)

V1 achieves **100% accuracy** on all 10 metadata fields:

| Field | V1 | V5 |
|-------|-----|-----|
| study_design | ✅ 100% | 95% |
| country | ✅ 100% | 86% |
| consumption_support | ✅ 100% | 5% |
| health_comp | ✅ 100% | 67% |
| asset_transfer | ✅ 100% | 5% |
| skills_comp | ✅ 100% | 86% |
| savings_comp | ✅ 100% | 65% |
| coaching_comp | ✅ 100% | 72% |
| social_comp | ✅ 100% | 58% |
| targeting_women | ✅ 100% | 65% |

**Conclusion:** Use V1's structured prompt for metadata. Done.

---

## 2. What's Poor: Finding Outcomes

None of the versions find more than 25% of outcomes:

| Version | Recall | Precision | Found/Total |
|---------|--------|-----------|-------------|
| V5 | **24.7%** | 21.0% | 109/442 |
| V4 | 23.8% | 19.6% | 105/442 |
| V1 | 19.2% | **42.5%** | 85/442 |
| V3 | 16.7% | 31.2% | 74/442 |
| V2 | 7.7% | 30.4% | 34/442 |

**By Category:**

| Category | GT Count | Best Recall | Best Version |
|----------|----------|-------------|--------------|
| Savings | 44 | 48% | V4/V5 |
| Poverty | 15 | 47% | V4/V5 |
| Income | 116 | 24% | V5 |
| Expenditure | 114 | 21% | V4 |
| Assets | 153 | 20% | V5 |

**Problem:** Models miss 75%+ of outcomes. Especially bad for Assets (largest category).

---

## 3. What's Poor: Effect Size Accuracy

For **matched** outcomes only:

| Version | Matched | Coeff Acc | SE Acc | d Acc | N Acc |
|---------|---------|-----------|--------|-------|-------|
| V3 | 38 | 54% | **77%** | **79%** | 82% |
| V4 | 69 | **62%** | 70% | 60% | **85%** |
| V5 | 74 | 54% | 61% | 66% | 80% |
| V1 | 43 | N/A | 20% | 14% | N/A |
| V2 | 16 | N/A | 0% | 23% | N/A |

**V1/V2 don't extract raw coefficients** - only effect sizes, and inaccurately.

**V3 has best accuracy** but lowest recall - extracts less but more accurately.

**V4/V5 extract more** but with ~60% accuracy - 40% are wrong.

---

## 4. What's Missing: Confidence Intervals

| Version | CI Extracted |
|---------|--------------|
| V1 | 0% |
| V2 | 0% |
| V3 | 0% |
| V4 | 0% |
| V5 | 0% |

**No version attempts to extract CIs.** This is required for meta-analysis.

---

## 5. Root Cause Analysis

### Why outcomes are missed (75%+):

1. **Fuzzy matching threshold (70%)** - may miss valid matches
   - "TLU" vs "Tropical Livestock Units" = 38% match (fails)
   - "agricultural income" vs "crop revenue" = 45% match (fails)

2. **Table parsing** - outcomes buried in tables not extracted

3. **Terminology variation** - same outcome, different names across studies

4. **Sub-outcomes** - GT has specific items, models extract aggregates

### Why effect sizes are inaccurate (~40% wrong):

1. **Multiple treatment arms** - model picks wrong coefficient

2. **Multiple time points** - model picks wrong follow-up

3. **Scale confusion** - percentage vs raw values

4. **Table misreading** - wrong row/column

### Why CIs are missing (100%):

1. **Not in prompt** - never explicitly requested

2. **Inconsistent reporting** - papers report CIs differently

3. **Computed vs reported** - some papers only have SE, not CI

---

## 6. What To Try Next

### Priority 1: Improve Outcome Recall

- [ ] Lower fuzzy threshold to 60%
- [ ] Add synonym expansion (TLU → Tropical Livestock Units)
- [ ] Use semantic matching instead of string matching
- [ ] Table-specific extraction pass

### Priority 2: Add CI Extraction

- [ ] Explicitly request CI_lower and CI_upper in prompt
- [ ] Compute CI from SE when not reported: `coeff ± 1.96*SE`
- [ ] Validate CI contains coefficient

### Priority 3: Improve Effect Size Accuracy

- [ ] Add treatment arm specification to prompt
- [ ] Add time point selection (longest follow-up)
- [ ] Add validation rules (coefficient within CI)
- [ ] Two-stage: find outcomes first, then extract stats

### Priority 4: Hybrid Approach

Best combination based on current results:
1. **Metadata:** V1 prompt (100% accuracy)
2. **Outcomes:** V5 full-paper extraction (best recall)
3. **Statistics:** V3-style reasoning step (best accuracy)
4. **CIs:** New extraction pass (currently 0%)

---

## 7. Files

| File | Purpose |
|------|---------|
| `v1_extraction_results.json` | Best metadata |
| `v5_extraction_results.json` | Best outcome recall |
| `v3_extraction_results.json` | Best effect size accuracy |
| `effect_size_accuracy.json` | Parameter accuracy data |
| `version_comparison_fuzzy.json` | Full comparison |

---

## 8. Summary

```
✅ SOLVED:     Metadata extraction (V1 = 100%)
⚠️ MEDIOCRE:  Effect size accuracy (~60-80% when matched)
❌ POOR:       Outcome recall (max 25%)
❌ MISSING:    Confidence intervals (0%)
```

**Current best approach:** V1 for metadata, but outcome/effect extraction needs significant improvement before production use.
