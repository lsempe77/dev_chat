# V3 Extraction Evaluation - Comprehensive Report

## Executive Summary

V3 extraction was run on all 43 matched studies. Here's how it compares to the V1 baseline:

### Metadata Accuracy Comparison

| Field | V1 Baseline | V3 Result | Change |
|-------|-------------|-----------|--------|
| study_design | 97.7% | 88.4% | -9.3% |
| country | 90.7% | 79.1% | -11.6% |
| skills_comp | 90.7% | 79.1% | -11.6% |
| health_comp | 69.8% | 65.1% | -4.7% |
| savings_comp | 69.8% | 69.8% | 0.0% |
| coaching_comp | 72.1% | 55.8% | -16.3% |
| social_comp | 65.1% | 62.8% | -2.3% |
| targeting_women | 74.4% | 62.8% | -11.6% |

**Overall Metadata Accuracy: 70.3%** (V1: ~78%)

### Root Cause Analysis for Metadata Regression

1. **JSON Parsing Failures**: 5 of 43 studies (11.6%) had metadata extraction failures due to JSON parsing errors in the LLM response. These studies returned empty metadata, dragging down accuracy.

2. **Evidence Quote Formatting**: The evidence quote extraction may be causing the LLM to generate malformed JSON with special characters.

3. **No consumption_support or asset_transfer in V1**: Can't compare these fields to baseline.

### Outcomes Extraction

| Metric | V3 Result |
|--------|-----------|
| Ground Truth Outcomes | 442 |
| Extracted Outcomes | 229 |
| Recall | 51.8% |
| Cohen's d Computed | 81 (35.4% of extracted) |
| Mean |d| Error | 0.1063 |
| Median |d| Error | 0.0563 |

### Cohen's d Error Distribution

| Error Threshold | Count | Cumulative % |
|-----------------|-------|--------------|
| ≤ 0.01 | 13 | 22.8% |
| ≤ 0.05 | 25 | 43.9% |
| ≤ 0.1 | 34 | 59.6% |
| ≤ 0.2 | 46 | 80.7% |
| ≤ 0.5 | 56 | 98.2% |
| ≤ 1.0 | 57 | 100% |

**Key Finding**: 80% of computed Cohen's d values have error < 0.2

### Cohen's d by Computation Method

| Method | Count | Mean Error | Median Error |
|--------|-------|------------|--------------|
| formula_6_n_total | 49 | 0.094 | 0.056 |
| formula_5_exact | 7 | 0.168 | 0.043 |
| means_and_sds | 1 | 0.251 | 0.251 |

**Notable**: `formula_6_n_total` (n_total with 50/50 split assumption) is the most commonly used method due to lack of separate n_treatment/n_control in most papers.

### Category Recall

| Category | GT Count | V3 Extracted | Recall |
|----------|----------|--------------|--------|
| Income | 116 | 64 | 55.2% |
| Assets | 153 | 41 | 26.8% |
| Savings | 44 | 30 | 68.2% |
| Expenditure | 114 | 42 | 36.8% |
| Poverty | 15 | 52 | 346.7%* |

*Over-extraction in Poverty category suggests misclassification.

### D Computation Failure Analysis

| Computation Method | Count | % of Extracted |
|--------------------|-------|----------------|
| insufficient_data | 148 | 64.6% |
| formula_6_n_total | 61 | 26.6% |
| formula_5_exact | 16 | 7.0% |
| means_and_sds | 4 | 1.7% |

**Root Cause**: 64.6% of outcomes couldn't compute Cohen's d due to missing standard errors. Sample case:
- coefficient: 0.25 ✓
- standard_error: None ✗ (critical missing)
- n_treatment: None ✗
- n_control: 1206 ✓
- n_total: 4712 ✓

The LLM extracts coefficients but often misses the standard errors from complex tables.

## Best and Worst Cases

### Perfect Matches (error = 0.0000)
- 121336027: computed=-1.0802, gt=-1.0802
- 121475071: computed=-0.0127, gt=-0.0127
- 121475071: computed=0.0899, gt=0.0899
- 121378494: computed=0.1384, gt=0.1384
- 122182716: computed=0.1280, gt=0.1280

### Largest Errors
- 121336027: computed=-0.4575, gt=-1.0802, error=0.6228
- 121330141: computed=1.3905, gt=0.9959, error=0.3946
- 121295229: computed=0.2308, gt=-0.0668, error=0.2976

## Key Findings

### What V3 Does Well

1. **Evidence Quotes**: V3 extracts evidence quotes for each field, enabling provenance tracking
2. **Confidence Scores**: Each extraction has a 0-1 confidence score
3. **Programmatic Cohen's d**: Uses verified formula instead of LLM computation
4. **Structured Output**: Clean dataclass-based extraction schema
5. **When data is available, d computation is accurate**: 80% of values within 0.2 of GT

### Areas for Improvement

1. **Standard Error Extraction**: Only 35.4% of outcomes have computable d (missing SE)
2. **JSON Parsing Robustness**: 11.6% metadata failure rate
3. **Outcome Recall**: Only 51.8% of outcomes captured
4. **Category Classification**: Poverty over-extracted, Assets under-extracted

## Recommendations for V4

1. **Targeted SE Extraction**: Separate prompt specifically for standard errors from tables
2. **JSON Mode**: Use structured output mode to prevent parsing failures
3. **Multi-Pass Outcome Extraction**: Run extraction multiple times with different prompts
4. **Table-Focused Extraction**: Extract table contents separately then parse
5. **Self-Verification**: Add validation stage comparing extracted values

## Technical Details

### Files Generated
- `v3_extraction_results.json`: Full extraction data with comparison
- `v3_extraction_report.md`: Per-study breakdown
- `v3_extraction_results_partial.json`: Incremental saves during processing

### Processing Time
- ~25 minutes for 43 studies
- ~35 seconds per study average (2 LLM calls per study)

### Formula Used
```python
d = (coef / se) * np.sqrt(1/n1 + 1/n2)
```

## Conclusion

V3 represents a step towards evidence-based extraction with confidence scores and provenance tracking. The key bottleneck is **standard error extraction** - when SE is available, the Cohen's d formula works accurately (80% within 0.2 of ground truth). 

The next iteration should focus on:
1. Better SE extraction from tables (currently 64.6% missing)
2. More robust JSON parsing (11.6% metadata failures)
3. Multi-pass outcome extraction to improve recall (currently 51.8%)
