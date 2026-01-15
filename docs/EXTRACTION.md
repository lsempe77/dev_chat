# Data Extraction & Validation Framework for DevChat

**Purpose:** Design a robust framework for extracting structured data from UPG studies and validating extraction accuracy against human ground truth.

**Date:** January 8, 2026

---

## 1. Data Overview

### Ground Truth Sources

| Source | File | Records | Unique Studies | Purpose |
|--------|------|---------|----------------|---------|
| **8WR QEX Combined** | `8WR QEX Combined.xlsx` | 443 rows | 43 studies | Effect sizes, outcomes, intervention components |
| **Master UPG** | `master_UPG.csv` | 118 rows | 118 studies | Study metadata, program names, study design |

### Coverage in RAG

| Metric | Count |
|--------|-------|
| Total PDFs in Qdrant | 97 |
| Study IDs extractable from PDFs | 55 |
| Studies matching 8WR Excel | **41** |
| Studies matching Master UPG | **54** |

**→ We have 41 studies with full ground truth for validation testing**

---

## 2. Variables to Extract

### Tier 1: High Priority (Already in current metadata or easy to extract)

| Variable | Type | Source | Validation | Current Status |
|----------|------|--------|------------|----------------|
| `study_design` | Enum: RCT, Quasi, Other | Full text | Schema constraint | ⚠️ Partial |
| `country` | String (ISO list) | Metadata + text | Schema + plausibility | ⚠️ Partial |
| `year` | Integer | Metadata + text | Cross-validate | ✅ Done |
| `author` | String | Metadata | Cross-validate | ✅ Done |

### Tier 2: Intervention Components (Binary classification)

| Variable | Type | Description | Example Values |
|----------|------|-------------|----------------|
| `consumption_support` | Binary | Cash/in-kind support | 0, 1 |
| `health_comp` | Binary | Health component | 0, 1 |
| `asset_transfer` | Binary | Livestock/tools/seed capital | 0, 1 |
| `skills_comp` | Binary | Skills training | 0, 1 |
| `savings_comp` | Binary | Savings component | 0, 1 |
| `coaching_comp` | Binary | Mentoring/coaching | 0, 1 |
| `social_comp` | Binary | Social integration | 0, 1 |

### Tier 3: Outcome Variables (Complex extraction)

| Variable | Type | Description | Example Values |
|----------|------|-------------|----------------|
| `outcome_category` | Enum | Primary outcome type | Income, Assets, Savings, Expenditure, Poverty |
| `outcome_name` | String | Specific outcome measure | "Harvest value (yearly, USD)" |
| `sample_size_treatment` | Integer | N in treatment arm | 500, 1200, etc. |
| `sample_size_control` | Integer | N in control arm | 500, 1200, etc. |
| `effect_size_d` | Float | Cohen's d | -0.5 to 1.5 |
| `standard_error` | Float | SE of effect | 0.01 to 0.5 |
| `follow_up_months` | Integer | Months after intervention | 6, 12, 24, 36 |

### Tier 4: Program Metadata

| Variable | Type | Description |
|----------|------|-------------|
| `program_name` | String | Name of intervention program |
| `program_id` | String | Unique program identifier |
| `targeting_women` | Binary | Women-focused targeting |

---

## 3. Extraction Validation Architecture

Based on SOTA research (VALID Framework, Self-Verification, Multi-Agent Consensus):

```
┌──────────────────────────────────────────────────────────────────────┐
│                    EXTRACTION PIPELINE v1.0                          │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  STAGE 1: PRIMARY EXTRACTION                                         │
│  ─────────────────────────────────────────────────────────────────   │
│  • GPT-4o extracts each variable                                     │
│  • Returns: {value, confidence: 0-1, evidence_quote}                 │
│  • Structured output (JSON schema enforcement)                       │
│                                                                      │
│  STAGE 2: SELF-VERIFICATION (Provenance Check)                       │
│  ─────────────────────────────────────────────────────────────────   │
│  • For each extraction: "Quote the exact text supporting this"       │
│  • If quote not found → confidence *= 0.5                            │
│  • Enables human audit of uncertain extractions                      │
│                                                                      │
│  STAGE 3: SCHEMA VALIDATION                                          │
│  ─────────────────────────────────────────────────────────────────   │
│  • study_design ∈ {RCT, Quasi-Experimental, Observational}           │
│  • country ∈ ISO_COUNTRY_LIST                                        │
│  • sample_size > 0 AND sample_size < 1,000,000                       │
│  • effect_size ∈ [-5, 5] (reasonable range)                          │
│  • year ∈ [1990, 2026]                                               │
│                                                                      │
│  STAGE 4: CROSS-SOURCE VALIDATION                                    │
│  ─────────────────────────────────────────────────────────────────   │
│  • If DOI available: Compare with OpenAlex/Crossref                  │
│  • Compare title/year/authors with metadata                          │
│  • Flag mismatches for review                                        │
│                                                                      │
│  STAGE 5: UNCERTAINTY FLAGGING                                       │
│  ─────────────────────────────────────────────────────────────────   │
│  • If confidence < 0.7 → needs_review = true                         │
│  • If schema validation fails → needs_review = true                  │
│  • Store in Qdrant payload for human review                          │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 4. Accuracy Testing Framework

### 4.1 Dataset Preparation

```python
# Merge ground truth with Qdrant documents
matched_studies = {
    "121058356": "Bossuroy (2021) - Niger CTP",
    "121058367": "Alderman (2021) - Ethiopia SPIR",
    "121294795": "...",
    # ... 41 matched studies total
}
```

### 4.2 Evaluation Metrics

| Metric | Formula | Use Case |
|--------|---------|----------|
| **Exact Match** | `extracted == ground_truth` | Categorical variables |
| **Fuzzy Match** | `fuzz.ratio(extracted, gt) > 0.9` | Text fields (program name) |
| **Numeric Tolerance** | `abs(extracted - gt) < tolerance` | Effect sizes, sample sizes |
| **Precision** | `TP / (TP + FP)` | Binary components |
| **Recall** | `TP / (TP + FN)` | Binary components |
| **F1 Score** | `2 * (P * R) / (P + R)` | Overall performance |

### 4.3 Per-Variable Accuracy Targets

| Variable Type | Target Accuracy | Rationale |
|---------------|-----------------|-----------|
| Study Design (RCT/Quasi) | 95%+ | Critical for filtering |
| Country | 95%+ | Schema constrained |
| Intervention Components (binary) | 85%+ | Complex reasoning |
| Sample Size | 80%+ | Numeric extraction hard |
| Effect Size | 75%+ | Requires table parsing |
| Program Name | 90%+ | Usually in title/abstract |

---

## 5. Testing Procedure

### Phase 1: Baseline Test (Before improvements)

1. Take 10 random studies from the 41 matched
2. Run current extraction on their PDFs
3. Compare against ground truth
4. Document baseline accuracy per variable

### Phase 2: After Validation Layer

1. Implement self-verification
2. Implement schema validation
3. Re-run on same 10 studies
4. Measure improvement

### Phase 3: Full Evaluation

1. Run on all 41 matched studies
2. Calculate final metrics
3. Analyze failure modes
4. Iterate on prompts/schemas

---

## 6. Implementation Plan

| Phase | Task | Effort | Priority |
|-------|------|--------|----------|
| **P0** | Create test harness (match PDFs to ground truth) | 4h | 🔴 Critical |
| **P1** | Implement self-verification prompts | 4h | 🔴 Critical |
| **P2** | Add schema validation for all variables | 4h | 🔴 Critical |
| **P3** | Build evaluation script (metrics calculation) | 4h | 🔴 Critical |
| **P4** | Run baseline evaluation | 2h | 🟡 High |
| **P5** | Tune extraction prompts based on errors | 8h | 🟡 High |
| **P6** | Multi-LLM consensus (optional) | 8h | 🟢 Medium |

**Total Estimated Time: ~34 hours**

---

## 7. Technical Design

### 7.1 Extraction Schema (Pydantic)

```python
from pydantic import BaseModel, Field
from typing import Optional, Literal
from enum import Enum

class StudyDesign(str, Enum):
    RCT = "RCT"
    QUASI = "Quasi-Experimental"
    OBSERVATIONAL = "Observational"
    UNKNOWN = "Unknown"

class OutcomeCategory(str, Enum):
    INCOME = "Income"
    ASSETS = "Assets"
    SAVINGS = "Savings"
    EXPENDITURE = "Expenditure"
    POVERTY = "Poverty"

class ExtractedVariable(BaseModel):
    value: str | int | float | bool
    confidence: float = Field(ge=0, le=1)
    evidence_quote: Optional[str] = None
    needs_review: bool = False

class StudyExtraction(BaseModel):
    # Tier 1
    study_design: ExtractedVariable
    country: ExtractedVariable
    year: ExtractedVariable
    
    # Tier 2: Intervention components
    consumption_support: ExtractedVariable
    health_comp: ExtractedVariable
    asset_transfer: ExtractedVariable
    skills_comp: ExtractedVariable
    savings_comp: ExtractedVariable
    coaching_comp: ExtractedVariable
    social_comp: ExtractedVariable
    
    # Tier 3: Outcomes (list - multiple per study)
    outcomes: list[OutcomeExtraction]
    
    # Tier 4: Program
    program_name: ExtractedVariable
    targeting_women: ExtractedVariable

class OutcomeExtraction(BaseModel):
    category: OutcomeCategory
    name: str
    sample_size_treatment: Optional[int]
    sample_size_control: Optional[int]
    effect_size: Optional[float]
    standard_error: Optional[float]
    follow_up_months: Optional[int]
```

### 7.2 Validation Functions

```python
from iso3166 import countries

def validate_country(value: str) -> bool:
    """Check if country is valid ISO country."""
    try:
        countries.get(value)
        return True
    except KeyError:
        # Try common variations
        variations = {
            "Phillipines": "Philippines",
            "Burkina": "Burkina Faso",
            # ... more mappings
        }
        return value in variations

def validate_sample_size(n: int) -> bool:
    """Check sample size is plausible."""
    return 1 <= n <= 1_000_000

def validate_effect_size(d: float) -> bool:
    """Check effect size is in reasonable range."""
    return -5 <= d <= 5

def validate_year(year: int) -> bool:
    """Check year is plausible."""
    return 1990 <= year <= 2026
```

---

## 8. Next Steps

1. **Create test harness** - Script to match PDFs ↔ ground truth
2. **Build extraction pipeline** - Structured prompts with self-verification
3. **Run baseline** - Measure current accuracy
4. **Iterate** - Improve based on error analysis

---

## Appendix A: Matched Study IDs

```
Studies in BOTH Excel Ground Truth AND Qdrant RAG (41 total):
121058356, 121058364, 121058367, 121058368, 121058369, 121058373,
121294795, 121294841, 121294873, 121294984, 121295229, 121295428,
121295641, 121295691, 121297660, ...
```

## Appendix B: Countries in Dataset

```
Niger (56), India (54), Bangladesh (43), Ethiopia (37), Burkina (30),
Yemen (29), Ghana (25), Egypt (24), Philippines (18), South Sudan (16),
Afghanistan (14), Peru (14), Chad (12), Uganda (12), Somalia (11),
Honduras (10), Paraguay (8), Zambia (8), Malawi (7), Pakistan (6),
Nicaragua (4), Rwanda (2), Burundi (1), Vietnam (1)
```

## Appendix C: Outcome Categories

```
Income, Assets, Savings, Expenditure, Poverty
```
