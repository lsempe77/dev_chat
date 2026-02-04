# Extraction Pipeline

The `extraction_pipeline/` package extracts **full quantitative results** from academic papers, including coefficients, standard errors, sample sizes, and treatment effect data.

## Overview

The extraction pipeline is now **fully integrated with production**:

1. **Batch Processing** → Extracts data from PDFs stored in R2
2. **Supabase Storage** → Stores results in `extracted_estimates` table  
3. **REST API** → Serves data via `/extraction/*` endpoints
4. **Chatbot Integration** → Provides quantitative context for RAG synthesis

## Data Model

Every extracted estimate includes the **complete quantitative record**:

### Core Fields

| Field | Type | Description |
|-------|------|-------------|
| `study_id` | string | Document/study identifier |
| `table_number` | string | Source table (e.g., "Table2") |
| `table_caption` | string | Full table caption |
| `page_number` | int | Page in PDF |

### Treatment Effect Data

| Field | Type | Description |
|-------|------|-------------|
| `treatment_arm` | string | Treatment group name (e.g., "Cash + Training") |
| `outcome_name` | string | Outcome variable name |
| `outcome_category` | string | Standardized category (Income, Assets, Health, etc.) |

### Quantitative Results

| Field | Type | Description |
|-------|------|-------------|
| `coefficient` | float | Point estimate (regression coefficient) |
| `standard_error` | float | Standard error of the coefficient |
| `p_value` | float | Statistical significance |
| `ci_lower` | float | 95% CI lower bound |
| `ci_upper` | float | 95% CI upper bound |

### Sample Size Data

| Field | Type | Description |
|-------|------|-------------|
| `sample_size` | int | Total N |
| `n_treatment` | int | Treatment group N |
| `n_control` | int | Control group N |

### Control Group Statistics

| Field | Type | Description |
|-------|------|-------------|
| `control_mean` | float | Control group mean |
| `control_sd` | float | Control group standard deviation |

### Standardized Effect Sizes

| Field | Type | Description |
|-------|------|-------------|
| `cohens_d` | float | Cohen's d effect size |
| `hedges_g` | float | Hedges' g (bias-corrected) |
| `effect_size_assumption` | string | How effect size was calculated |

### Effect Classification

| Field | Type | Description |
|-------|------|-------------|
| `is_main_effect` | bool | Primary analysis (vs. robustness check) |
| `is_subgroup` | bool | Subgroup/heterogeneity analysis |
| `subgroup_variable` | string | Subgroup variable (e.g., "Gender") |

### Study Metadata

| Field | Type | Description |
|-------|------|-------------|
| `authors` | string | Study authors |
| `year` | int | Publication year |
| `country` | string | Study country |
| `study_design` | string | Design (RCT, DiD, RDD, etc.) |

## API Endpoints

### Get Study Effects

```http
GET /extraction/studies/{study_id}/effects
```

Returns all extracted estimates for a study, including full quantitative data.

**Response:**
```json
[
  {
    "id": "uuid",
    "study_id": "121058356",
    "treatment_arm": "Cash + Training",
    "outcome_name": "Monthly income",
    "coefficient": 42.5,
    "standard_error": 12.3,
    "p_value": 0.001,
    "n_treatment": 1250,
    "n_control": 1248,
    "cohens_d": 0.34,
    "is_main_effect": true,
    "authors": "Bandiera et al.",
    "year": 2017,
    "country": "Bangladesh"
  }
]
```

### Query Effects

```http
GET /extraction/effects?outcome_categories=Income,Assets&countries=Bangladesh&main_effects_only=true
```

Filter effects across studies with query parameters.

### Get Outcome Summaries

```http
GET /extraction/outcomes/summary
```

Cross-study aggregation by outcome category for meta-analysis context.

**Response:**
```json
[
  {
    "outcome_category": "Income",
    "n_studies": 45,
    "n_estimates": 312,
    "pooled_cohens_d": 0.28,
    "sd_cohens_d": 0.15,
    "median_cohens_d": 0.25
  }
]
```

### Evidence Panel Data

```http
GET /extraction/evidence-panel
```

Returns complete data for frontend Evidence Panel component.

### Chatbot Context

```http
GET /extraction/chatbot-context?outcome_keywords=income,assets
```

Returns compact quantitative context for injection into RAG prompts.

**Response:**
```json
{
  "studies": [
    {
      "study_id": "121058356",
      "authors": "Bandiera et al.",
      "year": 2017,
      "outcomes": ["Income", "Assets"],
      "avg_effect": 0.34,
      "n_estimates": 15
    }
  ],
  "pooled_effects": {
    "Income": 0.28,
    "Assets": 0.31
  },
  "n_studies": 92,
  "n_estimates": 10020
}
```

### Query-Relevant Context

```http
POST /extraction/chatbot-context/for-query
```

Get quantitative evidence relevant to a specific user query.

**Request:**
```json
{
  "query_text": "What is the impact of graduation programs on income?",
  "max_estimates": 50
}
```

## Chatbot Integration

The extraction API is designed for **future RAG chat integration**. The key integration points are:

### 1. QuantitativeContext Model

```python
class QuantitativeContext(BaseModel):
    query_relevant_estimates: List[ExtractedEstimate]
    outcome_summaries: List[OutcomeMetaAnalysis]
    evidence_narrative: str  # Pre-generated for prompt injection
```

### 2. ChatbotEffectContext Model

Compact model optimized for prompt injection:

```python
class ChatbotEffectContext(BaseModel):
    studies: List[Dict]  # Compact study data
    pooled_effects: Dict[str, float]  # By outcome category
    n_studies: int
    n_estimates: int
    
    def to_prompt_context(self) -> str:
        """Generate prompt-ready context string."""
        # Returns formatted text for synthesis prompts
```

### 3. Integration Pattern

```python
# In your synthesis agent:
from api.routes.extraction import get_chatbot_context

# During RAG synthesis
quant_context = await get_chatbot_context(
    outcome_keywords="income,assets",
    study_ids=retrieved_study_ids
)

# Inject into synthesis prompt
system_prompt = f"""
{base_prompt}

## Quantitative Evidence
{quant_context.to_prompt_context()}
"""
```

### 4. Future Wiring Options

The full quantitative data enables:

1. **Evidence Strength Statements**: "Based on 45 studies with pooled effect d=0.28..."
2. **Confidence Intervals in Responses**: "Income increased by 42.5 (SE: 12.3, p<0.001)"
3. **Meta-Analysis Summaries**: Auto-generated pooled effects by outcome
4. **Heterogeneity Detection**: Compare effects across countries/designs
5. **Forest Plot Generation**: All data needed for visual meta-analysis

## CLI Usage

### Upload to Supabase

```bash
# Dry run (validate only)
python -m extraction_pipeline.adapters.supabase_loader --all --dry-run

# Upload all extracted data
python -m extraction_pipeline.adapters.supabase_loader --all

# Upload single study
python -m extraction_pipeline.adapters.supabase_loader --study-id 121058356
```

### Run Extraction

```bash
# Extract from specific study
python -m extraction_pipeline.cli_v2 --study_id 121058356

# Fast mode (no LLM)
python -m extraction_pipeline.cli_v2 --study_id 121058356 --fast

# All studies in project
python -m extraction_pipeline.cli_v2 --all
```

## Database Schema

Migration: `supabase/migrations/20260204_extracted_estimates.sql`

```sql
CREATE TABLE extracted_estimates (
    id UUID PRIMARY KEY,
    study_id TEXT NOT NULL,
    treatment_arm TEXT NOT NULL,
    outcome_name TEXT NOT NULL,
    coefficient DOUBLE PRECISION,
    standard_error DOUBLE PRECISION,
    p_value DOUBLE PRECISION,
    n_treatment INTEGER,
    n_control INTEGER,
    cohens_d DOUBLE PRECISION,
    -- ... 28 total columns
);

-- Auto-generated summary for chatbot context
effect_summary TEXT GENERATED ALWAYS AS (
    treatment_arm || ' effect on ' || outcome_name || ': ' || coefficient || ...
) STORED;
```

## Module Reference

```{eval-rst}
.. automodule:: extraction_pipeline.pipeline
   :members:
   :undoc-members:
   :show-inheritance:
```

### Supabase Loader

```{eval-rst}
.. automodule:: extraction_pipeline.adapters.supabase_loader
   :members:
   :undoc-members:
   :show-inheritance:
```

### API Schemas

```{eval-rst}
.. automodule:: api.schemas.extraction
   :members:
   :undoc-members:
   :show-inheritance:
```

### API Routes

```{eval-rst}
.. automodule:: api.routes.extraction
   :members:
   :undoc-members:
   :show-inheritance:
```
