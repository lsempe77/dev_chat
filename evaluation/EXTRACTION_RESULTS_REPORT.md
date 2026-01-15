# Outcome Extraction Evaluation Report

**Date:** January 12, 2026  
**Dataset:** 43 studies from graduation programs meta-analysis  
**Ground Truth:** 442 outcomes across 5 categories  

---

## Executive Summary

| Version | Recall | Precision | F1 Score | Outcomes Extracted | GT Matched | Metadata Acc |
|---------|--------|-----------|----------|-------------------|------------|--------------|
| **V1** | 19.2% | **42.5%** | 26.5% | 200 | 85/442 | **100.0%** |
| V2 | 7.7% | 30.4% | 12.3% | 112 | 34/442 | 96.3% |
| V3 | 16.7% | 31.2% | 21.8% | 237 | 74/442 | 62.6% |
| V4 | 23.8% | 19.6% | 21.5% | 535 | 105/442 | 34.0% |
| **V5** | **24.7%** | 21.0% | 22.7% | 518 | 109/442 | 60.5% |

**Best Overall:** V1 (highest precision + perfect metadata)  
**Best Recall:** V5 (24.7%)  
**Best Precision:** V1 (42.5%)  
**Best Metadata:** V1 (100%)  

### Effect Size Accuracy (New Analysis)

| Version | Matched | Coefficient Acc | SE Acc | Cohen's d Acc | N Total Acc |
|---------|---------|-----------------|--------|---------------|-------------|
| V1 | 43 | N/A | 20.0% | 13.5% | N/A |
| V2 | 16 | N/A | 0.0% | 23.1% | N/A |
| **V3** | 38 | 54.1% | **76.5%** | **78.9%** | **82.1%** |
| V4 | 69 | **62.3%** | 70.0% | 59.6% | 84.6% |
| V5 | 74 | 54.1% | 60.7% | 66.1% | 80.0% |

**Best Effect Size Accuracy:** V3 (78.9% for Cohen's d)  
**Best Coefficient Extraction:** V4 (62.3% accurate)  
**CI Coverage:** 0% across all versions (major gap)  

---

## 1. Version Descriptions

### V1: Structured Few-Shot Extraction
- **File:** `evaluation/extraction_v1.py`
- **Approach:** Single-pass structured extraction with detailed few-shot examples
- **Context:** First 50,000 characters of paper
- **Model:** `anthropic/claude-3.5-sonnet`
- **Key Features:**
  - Explicit JSON schema with examples
  - Detailed field-by-field instructions
  - Category-specific outcome examples
  - Boolean metadata fields with clear definitions

### V2: Minimal Prompt Extraction
- **File:** `evaluation/extraction_v2.py`
- **Approach:** Simplified prompt with less guidance
- **Context:** First 50,000 characters
- **Model:** `anthropic/claude-3.5-sonnet`
- **Key Features:**
  - Shorter, less detailed prompts
  - Fewer examples
  - Aimed to test if simpler is better

### V3: Chain-of-Thought Extraction
- **File:** `evaluation/extraction_v3.py`
- **Approach:** Two-pass with reasoning step
- **Context:** First 50,000 characters
- **Model:** `anthropic/claude-3.5-sonnet`
- **Key Features:**
  - First pass: Identify all outcomes with reasoning
  - Second pass: Structure into JSON
  - More deliberate extraction process

### V4: Multi-Pass Full Paper (Fixed)
- **File:** `evaluation/extraction_v4_fixed.py`
- **Approach:** Simplified 2-pass (metadata + outcomes)
- **Context:** Full paper for outcomes, first 30K for metadata
- **Model:** `anthropic/claude-3.5-sonnet`
- **Key Features:**
  - Separate metadata and outcome passes
  - Full paper access for outcomes
  - Deduplication by name similarity + coefficient
  - Cohen's d computation

### V5: Full Paper Single-Pass
- **File:** `evaluation/extraction_v5_fullpaper.py`
- **Approach:** Single comprehensive pass with full paper
- **Context:** Full paper content
- **Model:** `anthropic/claude-3.5-sonnet`
- **Key Features:**
  - Full paper access (no truncation)
  - Detailed extraction prompt
  - Direct JSON output

---

## 2. Outcome Extraction Results

### 2.1 Overall Performance

| Version | Recall | Precision | F1 Score | Extracted | Matched |
|---------|--------|-----------|----------|-----------|---------|
| V1 | 19.2% | 42.5% | 26.5% | 200 | 85 |
| V2 | 7.7% | 30.4% | 12.3% | 112 | 34 |
| V3 | 16.7% | 31.2% | 21.8% | 237 | 74 |
| V4 | 23.8% | 19.6% | 21.5% | 535 | 105 |
| V5 | 24.7% | 21.0% | 22.7% | 518 | 109 |

**Observations:**
- V5 achieves highest recall (24.7%) but at cost of precision
- V1 achieves highest precision (42.5%) with good balance
- V4/V5 extract 2.5x more outcomes than V1, but many are false positives
- V2 significantly underperforms (likely too minimal guidance)

### 2.2 By Category: INCOME (116 GT outcomes)

| Version | Recall | Precision | Matched | Extracted |
|---------|--------|-----------|---------|-----------|
| V1 | 20.7% | 41.4% | 24 | 58 |
| V2 | 9.5% | 30.6% | 11 | 36 |
| V3 | 18.1% | 31.8% | 21 | 66 |
| V4 | 23.3% | 16.3% | 27 | 166 |
| V5 | 24.1% | 17.5% | 28 | 160 |

**Observations:**
- V5 finds most income outcomes (28/116)
- V4/V5 over-extract by 3x (160+ vs 58 for V1)
- V1 maintains best precision (41.4%)

### 2.3 By Category: ASSETS (153 GT outcomes)

| Version | Recall | Precision | Matched | Extracted |
|---------|--------|-----------|---------|-----------|
| V1 | 13.1% | 45.5% | 20 | 44 |
| V2 | 6.5% | 27.8% | 10 | 36 |
| V3 | 9.2% | 34.1% | 14 | 41 |
| V4 | 17.0% | 21.1% | 26 | 123 |
| V5 | 19.6% | 21.7% | 30 | 138 |

**Observations:**
- Assets is hardest category (largest GT, lowest recalls)
- V5 achieves best recall (19.6%)
- V1 achieves best precision (45.5%)
- V4/V5 extract 3x more but with more false positives

### 2.4 By Category: SAVINGS (44 GT outcomes)

| Version | Recall | Precision | Matched | Extracted |
|---------|--------|-----------|---------|-----------|
| V1 | 40.9% | 69.2% | 18 | 26 |
| V2 | 9.1% | 80.0% | 4 | 5 |
| V3 | 40.9% | 52.9% | 18 | 34 |
| V4 | 47.7% | 39.6% | 21 | 53 |
| V5 | 47.7% | 33.9% | 21 | 62 |

**Observations:**
- Best performing category across all versions
- V4/V5 achieve highest recall (47.7%)
- V1 achieves best precision (69.2%)
- V2 has highest precision (80%) but very low recall

### 2.5 By Category: EXPENDITURE (114 GT outcomes)

| Version | Recall | Precision | Matched | Extracted |
|---------|--------|-----------|---------|-----------|
| V1 | 15.8% | 45.0% | 18 | 40 |
| V2 | 6.1% | 31.8% | 7 | 22 |
| V3 | 14.9% | 37.8% | 17 | 45 |
| V4 | 21.1% | 22.6% | 24 | 106 |
| V5 | 20.2% | 27.4% | 23 | 84 |

**Observations:**
- V4 achieves best recall (21.1%)
- V1 achieves best precision (45.0%)
- V4/V5 extract 2-2.5x more outcomes

### 2.6 By Category: POVERTY (15 GT outcomes)

| Version | Recall | Precision | Matched | Extracted |
|---------|--------|-----------|---------|-----------|
| V1 | 33.3% | 15.6% | 5 | 32 |
| V2 | 13.3% | 15.4% | 2 | 13 |
| V3 | 26.7% | 7.8% | 4 | 51 |
| V4 | 46.7% | 8.0% | 7 | 87 |
| V5 | 46.7% | 9.5% | 7 | 74 |

**Observations:**
- Smallest GT category (15 outcomes)
- V4/V5 achieve best recall (46.7%)
- All versions over-extract poverty outcomes
- Low precision across all versions indicates category confusion

---

## 3. Metadata Extraction Results

### 3.1 Overall Accuracy by Version

| Version | Average Accuracy | Perfect Fields |
|---------|-----------------|----------------|
| **V1** | **100.0%** | 10/10 |
| V2 | 96.3% | 8/10 |
| V3 | 62.6% | 2/10 |
| V4 | 34.0% | 2/10 |
| V5 | 60.5% | 0/10 |

### 3.2 Field-by-Field Accuracy

| Field | V1 | V2 | V3 | V4 | V5 |
|-------|-----|-----|-----|-----|-----|
| study_design | 100% | 95.3% | 100% | 74.4% | 95.3% |
| country | 100% | 95.3% | 90.7% | 65.1% | 86.0% |
| consumption_support | 100% | 100% | 0% | 100% | 4.7% |
| health_comp | 100% | 95.3% | 69.8% | 0% | 67.4% |
| asset_transfer | 100% | 100% | 0% | 100% | 4.7% |
| skills_comp | 100% | 95.3% | 90.7% | 0% | 86.0% |
| savings_comp | 100% | 95.3% | 72.1% | 0% | 65.1% |
| coaching_comp | 100% | 95.3% | 69.8% | 0% | 72.1% |
| social_comp | 100% | 95.3% | 69.8% | 0% | 58.1% |
| targeting_women | 100% | 95.3% | 62.8% | 0% | 65.1% |

### 3.3 Metadata Analysis

**V1 Strengths:**
- Perfect extraction of all metadata fields
- Clear boolean field definitions in prompt
- Explicit examples for each field

**V4 Issues:**
- Most component fields at 0% (health_comp, skills_comp, savings_comp, coaching_comp, social_comp, targeting_women)
- Metadata prompt may be too simplified
- Uses shorter context (30K vs 50K)

**V5 Issues:**
- consumption_support and asset_transfer at 4.7%
- May be interpreting these fields differently
- Full paper context may dilute abstract/intro focus

---

## 4. Detailed Category Analysis

### 4.1 What Each Category Measures

| Category | Description | GT Count | Examples |
|----------|-------------|----------|----------|
| Income | Earnings, wages, revenue | 116 | total income, wage income, non-farm income |
| Assets | Possessions, wealth stocks | 153 | livestock, land, productive assets |
| Savings | Financial reserves | 44 | total savings, formal savings, emergency fund |
| Expenditure | Spending, consumption | 114 | food expenditure, total consumption, non-food |
| Poverty | Poverty measures | 15 | poverty rate, poverty gap, below poverty line |

### 4.2 Category-Specific Insights

**Income (Hardest to match):**
- Many income outcome names vary across studies
- "Total income" vs "household income" vs "annual income"
- Fuzzy matching at 70% threshold may miss subtle variations

**Assets (Largest category):**
- Most granular outcomes (specific asset types)
- "Livestock value" vs "value of livestock" vs "TLU"
- Different studies use different asset taxonomies

**Savings (Best performance):**
- More standardized terminology
- Clearer definitions across studies
- Smaller category = easier to extract

**Expenditure (Medium difficulty):**
- Food vs non-food distinction common
- "Consumption" vs "expenditure" terminology
- Per-capita vs household level variations

**Poverty (Over-extraction problem):**
- Only 15 GT outcomes but all versions extract 30-90
- Models may be categorizing income/expenditure as poverty
- Poverty measures often defined indirectly

---

## 5. Effect Size & Parameter Accuracy

This section compares extracted statistical values against ground truth for matched outcomes.

### 5.1 Parameter Accuracy Summary (within 10% tolerance)

| Version | Matched | Coefficient | SE | Cohen's d | N Total |
|---------|---------|-------------|-----|-----------|---------|
| V1 | 43 | N/A | 20.0% | 13.5% | N/A |
| V2 | 16 | N/A | 0.0% | 23.1% | N/A |
| **V3** | 38 | 54.1% | **76.5%** | **78.9%** | **82.1%** |
| **V4** | 69 | **62.3%** | 70.0% | 59.6% | **84.6%** |
| **V5** | 74 | 54.1% | 60.7% | 66.1% | 80.0% |

**Key Findings:**
- **V3 has best parameter accuracy** despite lower recall
- **V4 extracts most coefficients correctly** (62.3%)
- **V1/V2 don't extract raw coefficients** (only effect sizes)
- **No version extracts confidence intervals**

### 5.2 Parameter Extraction Completeness

| Version | Has Coefficient | Has SE | Has Cohen's d | Has N Total | Has CI |
|---------|-----------------|--------|---------------|-------------|--------|
| V1 | 0.0% (0) | 46.5% (20) | 86.0% (37) | 0.0% (0) | 0.0% (0) |
| V2 | 0.0% (0) | 68.8% (11) | 81.2% (13) | 0.0% (0) | 0.0% (0) |
| V3 | 97.4% (37) | 44.7% (17) | 50.0% (19) | 73.7% (28) | 0.0% (0) |
| **V4** | **100%** (69) | 72.5% (50) | 75.4% (52) | **94.2%** (65) | 0.0% (0) |
| **V5** | **100%** (74) | **82.4%** (61) | 79.7% (59) | 87.8% (65) | 0.0% (0) |

**Observations:**
- **V4/V5 extract coefficients for all matched outcomes**
- **V5 best at extracting standard errors** (82.4%)
- **V1/V2 focus on effect sizes, not raw coefficients**
- **No version extracts confidence intervals** (major gap)

### 5.3 Detailed Accuracy by Version

#### V1 (43 matched outcomes)
- Coefficient: Not extracted
- Standard Error: 20.0% accurate (4/20), median error 56.2%
- Cohen's d: 13.5% accurate (5/37), **median error 180%** (scale issue)
- N Total: Not extracted
- N Treatment: 66.7% accurate (6/9)
- N Control: 55.6% accurate (5/9)

#### V3 (38 matched outcomes) - Best Accuracy
- Coefficient: 54.1% accurate (20/37), median error 3.0%
- Standard Error: **76.5% accurate** (13/17)
- Cohen's d: **78.9% accurate** (15/19), median error 1.6%
- N Total: **82.1% accurate** (23/28)
- N Treatment: 100% accurate (3/3)
- N Control: 100% accurate (3/3)

#### V4 (69 matched outcomes) - Most Complete
- Coefficient: **62.3% accurate** (43/69)
- Standard Error: 70.0% accurate (35/50)
- Cohen's d: 59.6% accurate (31/52)
- N Total: **84.6% accurate** (55/65)
- N Treatment: 85.7% accurate (6/7)
- N Control: 71.4% accurate (5/7)

#### V5 (74 matched outcomes) - Best Completeness
- Coefficient: 54.1% accurate (40/74)
- Standard Error: 60.7% accurate (37/61)
- Cohen's d: 66.1% accurate (39/59)
- N Total: 80.0% accurate (52/65)
- N Treatment: 58.3% accurate (7/12)
- N Control: 75.0% accurate (9/12)

### 5.4 CI Coverage Gap

**Critical Finding:** No version extracts confidence intervals.

| Version | Has CI Lower | Has CI Upper |
|---------|--------------|--------------|
| V1 | 0% | 0% |
| V2 | 0% | 0% |
| V3 | 0% | 0% |
| V4 | 0% | 0% |
| V5 | 0% | 0% |

This is a **major improvement opportunity** - the GT has CI data for many outcomes.

---

## 6. Processing Statistics

### 6.1 Extraction Time

| Version | Total Time | Per Study | API Calls/Study |
|---------|-----------|-----------|-----------------|
| V1 | ~25 min | ~35 sec | 1 |
| V2 | ~20 min | ~28 sec | 1 |
| V3 | ~45 min | ~63 sec | 2 |
| V4 | ~50 min | ~70 sec | 2 |
| V5 | ~30 min | ~42 sec | 1 |

### 6.2 Token Usage (Estimated)

| Version | Input Tokens/Study | Output Tokens/Study |
|---------|-------------------|---------------------|
| V1 | ~12,000 | ~2,000 |
| V2 | ~12,000 | ~1,500 |
| V3 | ~15,000 | ~3,000 |
| V4 | ~25,000 | ~4,000 |
| V5 | ~30,000 | ~3,500 |

### 6.3 Failure Rates

| Version | Studies Failed | Failure Rate | Common Cause |
|---------|---------------|--------------|--------------|
| V1 | 0/43 | 0% | - |
| V2 | 0/43 | 0% | - |
| V3 | 0/43 | 0% | - |
| V4 | 1/43 | 2.3% | Content too large (596K chars) |
| V5 | 0/43 | 0% | - |

---

## 7. Fuzzy Matching Configuration

### 7.1 Matching Parameters

- **Algorithm:** Levenshtein-based fuzzy matching (fuzzywuzzy)
- **Threshold:** 70% similarity
- **Comparison:** Extracted outcome name vs GT outcome name
- **Matching:** One-to-one (each GT can match at most one extracted)

### 7.2 Matching Examples

**High-confidence matches (>90%):**
- "total income" ↔ "Total Income" (100%)
- "livestock value" ↔ "Livestock Value" (100%)
- "food expenditure" ↔ "Food Expenditure" (100%)

**Medium-confidence matches (70-90%):**
- "household income" ↔ "total household income" (82%)
- "savings" ↔ "total savings" (75%)
- "consumption expenditure" ↔ "total consumption" (73%)

**Failed matches (<70%):**
- "agricultural income" ↔ "crop revenue" (45%)
- "TLU" ↔ "tropical livestock units" (38%)
- "poverty rate" ↔ "below poverty line" (52%)

---

## 8. Error Analysis

### 8.1 False Positives (Extracted but not in GT)

**Common patterns:**
1. **Sub-components of GT outcomes**
   - GT: "total income" → Extracted: "wage income", "self-employment income", "farm income"
   
2. **Intermediate variables**
   - Extracted: "labor supply", "hours worked", "crop yield"
   - These are mechanisms, not final outcomes
   
3. **Category misclassification**
   - Income outcomes classified as Poverty
   - Expenditure outcomes classified as Income

### 8.2 False Negatives (In GT but not extracted)

**Common patterns:**
1. **Non-standard naming**
   - GT: "TLU" (Tropical Livestock Units)
   - Not recognized as asset outcome
   
2. **Buried in tables**
   - Outcomes only in table headers, not in text
   
3. **Composite measures**
   - GT: "asset index" - may be extracted as individual assets

### 8.3 Metadata Errors

**V3-V5 common issues:**
- Binary fields interpreted as descriptions
- "consumption_support" extracted as "yes" instead of true
- Country extraction including multiple countries

---

## 9. Recommendations

### 9.1 For Production Use

**Recommended: Hybrid Approach**
Based on analysis, no single version excels at everything:

| Need | Best Version | Alternative |
|------|--------------|-------------|
| Metadata accuracy | **V1** (100%) | V2 (96.3%) |
| Outcome recall | **V5** (24.7%) | V4 (23.8%) |
| Outcome precision | **V1** (42.5%) | V3 (31.2%) |
| Effect size accuracy | **V3** (78.9% d) | V5 (66.1% d) |
| Coefficient extraction | **V4** (62.3%) | V5 (54.1%) |
| Complete statistics | **V4/V5** (100% coeff) | V3 (97.4%) |

**Suggested Hybrid:**
1. Use **V1's metadata prompt** (100% accuracy)
2. Use **V5's full-paper outcome extraction** (best recall)
3. Add **V3's reasoning step** for effect sizes (best accuracy)

### 9.2 Critical Improvement Opportunities

1. **Confidence Intervals (0% coverage)**
   - No version extracts CI
   - Add explicit CI extraction to prompts
   - Priority: HIGH (required for meta-analysis)

2. **Effect Size Computation**
   - V1 has 180% median error on Cohen's d
   - V3 achieves 78.9% accuracy
   - Use V3's extraction approach for effect sizes

3. **Coefficient Accuracy**
   - V4 best at 62.3%
   - Large outlier errors (mean >> median)
   - Add validation rules for coefficient ranges

4. **Category Precision**
   - Poverty over-extracted by all versions (7-9% precision)
   - Add clearer category definitions
   - Post-processing validation

### 9.3 Improvement Opportunities

1. **Hybrid approach:**
   - V1's structured prompt + V5's full paper access
   - Separate metadata and outcome extraction
   - Keep V1's explicit boolean definitions

2. **Category-specific prompts:**
   - Different prompts for each outcome category
   - Reduce poverty over-extraction
   - Improve asset recognition

3. **Post-processing:**
   - Deduplication by semantic similarity
   - Category validation rules
   - Sample size sanity checks

4. **Matching improvements:**
   - Semantic matching instead of fuzzy string
   - Synonym expansion for outcome names
   - Abbreviation handling (TLU, HH, etc.)

5. **CI Extraction:**
   - Explicitly request CI_lower and CI_upper
   - Validate CI contains coefficient
   - Extract from tables more carefully

---

## 10. Files Reference

### 10.1 Extraction Scripts

| File | Description |
|------|-------------|
| `evaluation/extraction_v1.py` | V1: Structured few-shot |
| `evaluation/extraction_v2.py` | V2: Minimal prompt |
| `evaluation/extraction_v3.py` | V3: Chain-of-thought |
| `evaluation/extraction_v4_fixed.py` | V4: Multi-pass full paper |
| `evaluation/extraction_v5_fullpaper.py` | V5: Single-pass full paper |

### 10.2 Results Files

| File | Description |
|------|-------------|
| `evaluation/v1_extraction_results.json` | V1 raw results |
| `evaluation/v2_extraction_results.json` | V2 raw results |
| `evaluation/v3_extraction_results.json` | V3 raw results |
| `evaluation/v4_extraction_results.json` | V4 raw results |
| `evaluation/v5_extraction_results.json` | V5 raw results |
| `evaluation/version_comparison_fuzzy.json` | Comparison data |

### 10.3 Ground Truth

| File | Description |
|------|-------------|
| `evaluation/ground_truth_outcomes.json` | 443 labeled outcomes |
| `data/metadata.csv` | Study metadata |
| `data/pdf_metadata_mapping.json` | PDF to study ID mapping |

---

## Appendix A: Version Configuration Details

### V1 Configuration
```python
model = "anthropic/claude-3.5-sonnet"
max_tokens = 4096
temperature = 0
context_limit = 50000  # chars
```

### V5 Configuration
```python
model = "anthropic/claude-3.5-sonnet"
max_tokens = 8192
temperature = 0
context_limit = None  # full paper
```

---

## Appendix B: Category Recall Heatmap

```
              V1      V2      V3      V4      V5
Income      ███░░   █░░░░   ██░░░   ███░░   ███░░   (20-24%)
Assets      █░░░░   █░░░░   █░░░░   ██░░░   ██░░░   (7-20%)
Savings     ████░   █░░░░   ████░   █████   █████   (9-48%)
Expenditure ██░░░   █░░░░   █░░░░   ███░░   ██░░░   (6-21%)
Poverty     ███░░   █░░░░   ███░░   █████   █████   (13-47%)
```

---

## Appendix C: Study-Level Results Summary

**Studies with most outcomes extracted (V5):**
1. Study 121058364: 31 outcomes
2. Study 122182715: 28 outcomes  
3. Study 122182714: 25 outcomes
4. Study 121058370: 22 outcomes
5. Study 121058374: 21 outcomes

**Studies with fewest outcomes (V5):**
1. Study 121058367: 0 outcomes (too large for API)
2. Study 122182729: 4 outcomes
3. Study 121058356: 6 outcomes
4. Study 121058382: 7 outcomes

---

*Report generated: January 12, 2026*
