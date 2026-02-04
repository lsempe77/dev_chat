# Overview

DevChat is a RAG-powered research workbench designed for academic literature analysis at 3ie (International Initiative for Impact Evaluation).

## What is DevChat?

DevChat helps researchers:

1. **Upload and process** academic papers (PDFs) with AI-powered parsing
2. **Search** across their document corpus using hybrid semantic + keyword search  
3. **Get answers** with inline citations verified by NLI models
4. **Extract quantitative data** from results tables (coefficients, standard errors, sample sizes, p-values)
5. **Access full treatment effect data** via REST API for evidence synthesis

## Core Components

### Frontend (Next.js)
- React-based UI deployed on Vercel
- Chat interface with evidence panel
- Document management and upload
- Project settings and admin panel

### Backend (FastAPI)
- REST API deployed on Railway
- Authentication via Supabase JWT
- Chat endpoint with streaming responses
- **Extraction API** - Quantitative evidence endpoints
- Admin endpoints for document management

### PDF Processing (Modal)
- GPU-accelerated PDF parsing with MineRU
- Table and formula extraction
- Contextual chunking with Claude
- Vector embedding with Cohere

### Extraction Pipeline
- Automated table classification (results vs. non-results)
- Treatment effect extraction (coefficients, SEs, CIs, p-values)
- Sample size detection (n_treatment, n_control)
- Effect size calculation (Cohen's d, Hedges' g)
- **Supabase storage** - 28 columns of quantitative data
- **REST API** - 10 endpoints for querying effects

### Vector Database (Qdrant)
- Hybrid search (dense + sparse vectors)
- Binary quantization for fast search
- Multi-tenant with collection per project

### Synthesis Pipeline
- Claim Ledger: Two-pass extraction with citations
- MiniCheck: NLI verification of claims
- Study design classification
- **Quantitative context injection** for RAG synthesis

## Technology Stack

| Layer | Technology |
|-------|------------|
| Frontend | Next.js 15, TypeScript, Tailwind, shadcn/ui |
| Backend | FastAPI, Python 3.12, Pydantic v2 |
| Database | Supabase PostgreSQL with RLS |
| Vectors | Qdrant Cloud (hybrid search) |
| PDF Parsing | Modal (MineRU GPU) |
| Embeddings | Cohere embed-v4 |
| LLM | Claude (via OpenRouter) |
| Observability | Langfuse |

## Quantitative Evidence API

The `/extraction/*` endpoints provide full treatment effect data:

```http
# Get all effects for a study
GET /extraction/studies/121058356/effects

# Query with filters
GET /extraction/effects?outcome_categories=Income&countries=Bangladesh

# Cross-study aggregation
GET /extraction/outcomes/summary

# Chatbot context (for RAG prompt injection)
GET /extraction/chatbot-context?outcome_keywords=income,assets
```

**Example Response:**
```json
{
  "treatment_arm": "Cash + Training",
  "outcome_name": "Monthly income",
  "coefficient": 42.5,
  "standard_error": 12.3,
  "p_value": 0.001,
  "n_treatment": 1250,
  "n_control": 1248,
  "cohens_d": 0.34,
  "authors": "Bandiera et al.",
  "year": 2017
}
```

See {doc}`api/extraction` for complete API documentation.
