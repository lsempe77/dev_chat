---
output:
  pdf_document: default
  html_document: default
---
# DevChat v2.0 - SOTA RAG Architecture (2025-2026)

**DevChat** is an AI-powered **Research Workbench** for exploring academic studies from 3ie's Development Evidence Portal.

This is the **production-grade implementation** featuring state-of-the-art RAG techniques and a professional research-focused UI.

## 📊 Current Status

| Component | Status | Description |
|-----------|--------|-------------|
| **Backend (Railway)** | ✅ Live | https://3iechat.up.railway.app |
| **Frontend (Vercel)** | ✅ Live | https://frontend-amber-seven-55.vercel.app |
| **PDF Pipeline (Modal)** | ✅ Working | MinerU GPU processing |
| **Vector DB (Qdrant)** | ✅ Connected | `devchat_v2` collection (31 chunks) |
| **End-to-End RAG** | ✅ Working | Query → Retrieval → Rerank → Generate |
| **Document Corpus** | ⚠️ Limited | Only 1 test PDF indexed |
| **Settings Wiring** | ⬜ TODO | UI exists, not sent to backend |

**Live Demo:** https://frontend-amber-seven-55.vercel.app

---

## 🚀 Architecture Overview

┌─────────────────────────────────────────────────────────────────────────┐
│                              USER QUERY                                  │
└─────────────────────────────────┬───────────────────────────────────────┘
                                  │
┌─────────────────────────────────▼───────────────────────────────────────┐
│                      QUERY UNDERSTANDING LAYER                           │
│  • Classification (simple/complex/comparison)                            │
│  • Query Expansion (synonyms, acronyms, domain terms)                    │
│  • Metadata Extraction (year, sector, country filters)                   │
│  • Model: GPT-4o-mini via OpenRouter (fast)                              │
└─────────────────────────────────┬───────────────────────────────────────┘
                                  │
            ┌─────────────────────┼─────────────────────┐
            │                     │                     │
            ▼                     ▼                     ▼
   ┌────────────────┐   ┌────────────────┐   ┌────────────────┐
   │  DENSE SEARCH  │   │ SPARSE SEARCH  │   │METADATA FILTER │
   │  Cohere v4     │   │  BM25/SPLADE   │   │ Year, Sector   │
   └───────┬────────┘   └───────┬────────┘   └───────┬────────┘
            │                   │                     │
            └───────────────────┼─────────────────────┘
                                │
┌───────────────────────────────▼─────────────────────────────────────────┐
│                    FUSION + RERANKING                                    │
│  • Reciprocal Rank Fusion (RRF)                                          │
│  • Cohere Rerank v3.5 (top 50 → top 15)                                  │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │
┌───────────────────────────────▼─────────────────────────────────────────┐
│                    CONTEXT ASSEMBLY                                      │
│  • Parent chunk expansion                                                │
│  • Study grouping                                                        │
│  • Citation metadata attachment                                          │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │
┌───────────────────────────────▼─────────────────────────────────────────┐
│                    ADAPTIVE SYNTHESIS                                    │
│  Simple queries  → GPT-4o-mini (fast, cheap)                             │
│  Complex queries → GPT-4o (reasoning, nuance)                            │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │
┌───────────────────────────────▼─────────────────────────────────────────┐
│                    RESPONSE + CITATIONS                                  │
└─────────────────────────────────────────────────────────────────────────┘

---

## 🚀 Quick Start

### Production URLs

- **Frontend:** https://frontend-amber-seven-55.vercel.app
- **Backend API:** https://3iechat.up.railway.app
- **API Docs:** https://3iechat.up.railway.app/docs
- **GitHub:** https://github.com/lsempe77/dev_chat

### Local Development

#### 1. Start Backend (FastAPI)

```bash
# Terminal 1 - Backend API
cd devchat_v2_sota
pip install -r requirements.txt
uvicorn api.server:app --reload --port 8000
```

Backend runs at: `http://localhost:8000`
API docs at: `http://localhost:8000/docs`

#### 2. Start Frontend (Next.js)

```bash
# Terminal 2 - Frontend UI
cd frontend
npm install
npm run dev
```

Frontend runs at: `http://localhost:3000`

#### 3. Environment Variables

Create `.env` file with:
```bash
# LLM Provider (OpenRouter)
OPENROUTER_API_KEY=sk-or-...

# Embeddings & Reranking (Cohere)
COHERE_API_KEY=...

# Vector Database (Qdrant Cloud)
QDRANT_URL=https://...qdrant.io
QDRANT_API_KEY=...

# Observability (Langfuse)
LANGFUSE_PUBLIC_KEY=pk-...
LANGFUSE_SECRET_KEY=sk-...
LANGFUSE_HOST=https://cloud.langfuse.com
```

---

## 📁 Project Structure

devchat_v2_sota/
├── src/
│   ├── config/
│   │   ├── __init__.py
│   │   ├── settings.py          # Environment & model configuration
│   │   └── prompts.py           # All LLM prompts
│   │
│   ├── ingestion/
│   │   ├── __init__.py
│   │   ├── document_loader.py   # Load PDFs, Markdown, etc.
│   │   ├── chunking.py          # Semantic + parent-child chunking
│   │   ├── embeddings.py        # Embedding generation
│   │   └── indexer.py           # Qdrant index management
│   │
│   ├── retrieval/
│   │   ├── __init__.py
│   │   ├── query_processor.py   # Query expansion & classification
│   │   ├── hybrid_retriever.py  # Dense + Sparse + Metadata
│   │   ├── reranker.py          # Cohere reranking
│   │   └── context_builder.py   # Assemble final context
│   │
│   ├── generation/
│   │   ├── __init__.py
│   │   ├── router.py            # Model selection logic
│   │   ├── synthesizer.py       # Answer generation
│   │   └── citations.py         # Citation formatting
│   │
│   ├── agents/
│   │   ├── __init__.py
│   │   └── devchat_agent.py     # Main conversational agent
│   │
│   └── utils/
│       ├── __init__.py
│       ├── logging.py           # Structured logging
│       └── metrics.py           # Latency & quality tracking
│
├── api/
│   ├── __init__.py
│   ├── server.py                # FastAPI application
│   ├── routes.py                # API endpoints
│   └── schemas.py               # Pydantic models
│
├── frontend/                        # Next.js Research Workbench UI ✅
│   ├── src/
│   │   ├── app/
│   │   │   ├── layout.tsx           # Root layout
│   │   │   ├── page.tsx             # Main Research Workbench
│   │   │   └── globals.css          # Tailwind styles
│   │   ├── components/
│   │   │   ├── ui/                  # shadcn/ui (16 components)
│   │   │   └── workbench/           # Custom components:
│   │   │       ├── SplitLayout.tsx      # Resizable panels
│   │   │       ├── AnswerPanel.tsx      # Answer + citations + evidence health
│   │   │       ├── EvidencePanel.tsx    # Study cards + export
│   │   │       ├── StudyCard.tsx        # Study display
│   │   │       ├── FilterChips.tsx      # Active filters
│   │   │       ├── FilterDrawer.tsx     # Add filters
│   │   │       ├── SettingsDrawer.tsx   # Search settings
│   │   │       ├── CompareModal.tsx     # Study comparison
│   │   │       └── SearchInput.tsx      # Query input
│   │   ├── lib/
│   │   │   ├── api.ts               # FastAPI client
│   │   │   └── utils.ts             # Utilities
│   │   └── types/
│   │       └── index.ts             # TypeScript interfaces
│   ├── package.json
│   └── tailwind.config.ts
│
├── evaluation/
│   ├── __init__.py
│   ├── evaluator.py             # RAGAS evaluation
│   └── test_cases.json          # Golden test set
│
├── scripts/
│   ├── ingest_documents.py      # CLI for document ingestion
│   └── run_evaluation.py        # CLI for running evals
│
├── tests/
│   ├── __init__.py
│   ├── test_retrieval.py
│   ├── test_generation.py
│   └── test_integration.py
│
├── .env.example                 # Environment template
├── requirements.txt             # Dependencies
├── pyproject.toml               # Project metadata
├── Dockerfile                   # Container build
└── README.md                    # This file


## 🛠️ Tech Stack

| Component | Technology | Why |
|-----------|------------|-----|
| **LLM Provider** | OpenRouter | Unified API for all models, single API key |
| **LLM (Fast)** | GPT-4o-mini | Query processing, simple Q&A |
| **LLM (Reasoning)** | GPT-4o | Complex synthesis, comparisons |
| **Embeddings** | Cohere embed-v4.0 | 1536 dims, SOTA retrieval |
| **Reranking** | Cohere Rerank v3.5 | 15-20% accuracy boost |
| **Vector DB** | Qdrant Cloud | Dense vectors + metadata filters |
| **PDF Processing** | MinerU on Modal | GPU extraction, T4 instance |
| **Storage** | Cloudflare R2 | S3-compatible object storage |
| **API** | FastAPI | Async, fast, typed |
| **UI** | Next.js 15 + shadcn/ui | Research Workbench |
| **Hosting** | Railway + Vercel | Backend + Frontend |
| **Observability** | Langfuse | Tracing & analytics |

### OpenRouter Integration

We use [OpenRouter](https://openrouter.ai) as the unified LLM provider:
- **Single API key** to access all major models (Anthropic, OpenAI, Google, etc.)
- **Model format**: `provider/model-name` (e.g., `openai/gpt-4o-mini`)
- **Easy model switching** without code changes
- **Usage tracking** and cost monitoring built-in

---

## 🔌 Backend API (Frontend ↔ Backend)

The frontend is fully wired to the FastAPI backend. Here's the API reference:

### API Endpoints

| Frontend Function | Endpoint | Status |
|-------------------|----------|--------|
| `queryEvidence(query, filters)` | `POST /api/query` | ✅ Working |
| `compareStudies(studyIds)` | `POST /api/compare` | ✅ Working |
| `getSuggestions(query, context)` | `POST /api/suggest` | ⚠️ Placeholder |
| `getAvailableFilters()` | `GET /api/filters` | ✅ Working |

### SearchSettings → Backend Parameters

The SettingsDrawer sends these parameters to the backend:

```typescript
interface SearchSettings {
  relevanceThreshold: number;  // 0-1 → Filter results with score < threshold
  maxStudies: number;          // 3-25 → Limit retrieval count (top_k)
  answerStyle: AnswerStyle;    // → Select prompt template in synthesizer
  minConfidence: string;       // → Qdrant filter on confidence field
  useReranking: boolean;       // → Skip/use Cohere reranker
  yearCutoff: number;          // → Qdrant filter: year >= yearCutoff
}
```

### Request/Response Schemas

**POST /api/query**
```typescript
// Request
{
  query: string,
  filters: Filter[],           // [{type: "country", value: "Kenya", label: "Kenya"}]
  settings: SearchSettings
}

// Response
{
  answer: string,              // Markdown with [1][2] citations
  studies: Study[],            // Ranked study objects
  citations: Citation[],       // {id, studyId, text, startIndex, endIndex}
  evidenceHealth: EvidenceHealth,
  suggestions: string[]
}
```

**POST /api/compare**
```typescript
// Request
{ studyIds: string[] }

// Response
{
  rows: CompareRow[]  // [{dimension, values: {studyId: value}}]
}
```

---

## 🎨 Research Workbench UI

DevChat is not just a chatbot - it's a **Research Workbench** designed for serious evidence exploration.

### Core UX Principle

Users don't just want an answer. They want to know:
- **What evidence you used**
- **Why you chose it**
- **What you might have missed**
- **How to steer the system without wrestling prompts**

### UI Layout

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Active filters: [Kenya ✕] [RCT ✕] [2018-2024 ✕]            [+ Add]    │
├─────────────────────────────────────────────────────────────────────────┤
│  🔍 What are the effects of cash transfers on food security?           │
├─────────────────────────────┬───────────────────────────────────────────┤
│                             │                                           │
│     💬 ANSWER PANEL         │     📚 EVIDENCE PANEL                     │
│                             │                                           │
│  Structured response with   │  Study cards ranked by relevance          │
│  inline [1] [2] citations   │                                           │
│                             │  ┌─────────────────────────────────────┐  │
│  Click [1] → highlights     │  │ [1] Smith et al. (2023)             │  │
│  snippet on right           │  │ Kenya | RCT | High confidence       │  │
│                             │  │ "35% increase in food security..."  │  │
│  ─────────────────────────  │  │ [Open PDF] [Compare] [Exclude]      │  │
│                             │  └─────────────────────────────────────┘  │
│  📊 Evidence Health         │                                           │
│  • 6 studies used           │  ┌─────────────────────────────────────┐  │
│  • 2018-2024 coverage       │  │ [2] Patel et al. (2022)             │  │
│  • ⚠️ No studies from Asia  │  │ India | RCT | Medium confidence     │  │
│                             │  │ "Computer-assisted learning..."     │  │
│  ─────────────────────────  │  │ [Open PDF] [Compare] [Exclude]      │  │
│                             │  └─────────────────────────────────────┘  │
│  💡 Try next:               │                                           │
│  • Narrow to Sub-Saharan    │                                           │
│    Africa?                  │                                           │
│  • Compare CCT vs UCT?      │                                           │
│                             │                                           │
└─────────────────────────────┴───────────────────────────────────────────┘
```

### Key Features

| Feature | Description |
|---------|-------------|
| **Split Screen** | Answer on left, evidence panel on right - always visible |
| **Study Cards** | Title, year, country, study type, confidence, matched snippets |
| **Citation Linking** | Click [1] in answer → highlights exact snippet in evidence |
| **Faceted Filters** | Year, country, sector, methodology as clickable chips |
| **Compare Mode** | Select 2-10 studies → table with population, intervention, effects |
| **Query Coaching** | Suggested next moves: narrow, compare, explore gaps |
| **Evidence Health** | Coverage signals: # studies, date range, gaps detected |
| **Answer Styles** | Toggle: Executive summary / Research brief / Policy implications |
| **Export** | PDF/Word with citations, Markdown, shareable research trail |

### Compare Mode

```
┌─────────────────────────────────────────────────────────────────────────┐
│  COMPARING 3 STUDIES                                    [Clear] [Export]│
├─────────────────────────────────────────────────────────────────────────┤
│              │ Smith 2023   │ Patel 2022   │ Jones 2021   │
│──────────────│──────────────│──────────────│──────────────│
│ Country      │ Kenya        │ India        │ Mexico       │
│ Design       │ RCT          │ RCT          │ Quasi-exp    │
│ Population   │ Rural HH     │ Urban slums  │ Rural HH     │
│ Intervention │ UCT $50/mo   │ CCT + health │ CCT          │
│ Outcome      │ Food security│ Nutrition    │ Food security│
│ Effect       │ +35% ↑       │ +12% ↑       │ +8% ↑        │
│ Confidence   │ High         │ Medium       │ Low          │
├─────────────────────────────────────────────────────────────────────────┤
│  ⚠️ CONFLICT DETECTED: Effect sizes vary significantly (8-35%)         │
│  [Explain why they differ]                                              │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 📊 Key Features

### Hybrid Retrieval
- **Dense vectors** (Cohere embed-v4) for semantic similarity
- **Sparse vectors** (BM25) for exact keyword matching
- **Metadata filters** for Year, Sector, Country, Confidence Level
- **Reciprocal Rank Fusion** to merge results

### Query Intelligence
- **Query Classification**: Routes to appropriate pipeline
- **Query Expansion**: "CCTs" → "conditional cash transfers, cash transfer programs"
- **Filter Extraction**: Parses implicit constraints from natural language

### Adaptive Synthesis
- **Simple queries**: Fast model, direct answers
- **Complex queries**: Reasoning model, structured synthesis
- **Comparison queries**: Multi-document analysis with conflict resolution

### Evaluation Pipeline
- **RAGAS metrics**: Faithfulness, Answer Relevancy, Context Precision
- **Golden test set**: Curated question-answer pairs
- **A/B testing**: Compare model/prompt variants

## 🔧 Configuration

Key settings in `src/config/settings.py`:

```python
# Model Selection (via OpenRouter)
LLM_FAST = "openai/gpt-4o-mini"
LLM_REASONING = "openai/gpt-4o"
EMBEDDING_MODEL = "embed-v4.0"  # Cohere
RERANK_MODEL = "rerank-v3.5"    # Cohere

# Retrieval Parameters
HYBRID_ENABLED = False  # Dense only (collection has no sparse vectors)
RETRIEVAL_TOP_K = 50
RERANK_TOP_N = 15

# Chunking
CHUNK_SIZE = 512
CHUNK_OVERLAP = 50
```

## 📈 Expected Performance

| Metric | v1 (Baseline) | v2 (SOTA) |
|--------|---------------|-----------|
| Retrieval Recall@10 | ? | ~85% |
| Answer Accuracy |  ? | ~90% |
| Citation Accuracy | ? | ~85% |
| Latency (p50) |  ? | 2-4s |

---

## 🔬 SOTA RAG Landscape (2024-2025)

This section documents state-of-the-art RAG techniques and how DevChat v2.0 compares.

### What DevChat v2.0 Implements ✅

| Technique | Implementation | Notes |
|-----------|----------------|-------|
| **Hybrid Search** | Dense (Cohere) + Sparse (BM25) + RRF | Industry standard |
| **Cross-Encoder Reranking** | Cohere Rerank v3.5 | 15-20% precision boost |
| **Query Expansion** | LLM-based synonym expansion | "CCTs" → "conditional cash transfers" |
| **Metadata Filtering** | Year, Sector, Country, Study Type | Extracted from natural language |
| **Adaptive Routing** | Simple → Fast model, Complex → Reasoning | Cost optimization |
| **Observability** | Langfuse tracing | Full pipeline visibility |

### Advanced Techniques for Future Roadmap 🚀

#### 1. Enhanced Retrieval

| Technique | Description | Benefit | Complexity |
|-----------|-------------|---------|------------|
| **Contextual Retrieval** | Prepend document context to each chunk before embedding | +49% recall with reranking | Medium |
| **ColBERTv2** | Late interaction model - token-level matching at query time | Better than cross-encoders | High |
| **Late Chunking** | Embed full document, then chunk embeddings | Preserves context | Medium |

**References:**
- [Anthropic Contextual Retrieval (2024)](https://www.anthropic.com/news/contextual-retrieval)
- [ColBERTv2 Paper](https://arxiv.org/abs/2112.01488)

#### 2. Query Enhancement

| Technique | Description | Benefit | Complexity |
|-----------|-------------|---------|------------|
| **Multi-Query / RAG-Fusion** | Generate 3-5 query variants, fuse results | Robust retrieval | Low |
| **HyDE** | Generate hypothetical answer, embed that instead | Works when no exact match | Medium |
| **Recursive Retrieval** | Retrieve → Generate sub-questions → Retrieve again | Complex questions | Medium |

**References:**
- [RAG-Fusion Paper](https://arxiv.org/abs/2402.03367)
- [HyDE Paper](https://arxiv.org/abs/2212.10496)

#### 3. Self-Correction Loops

| Technique | Description | Benefit | Complexity |
|-----------|-------------|---------|------------|
| **CRAG** | Retrieve → Score relevance → Web fallback if low | Reduces hallucination | Medium |
| **Self-RAG** | LLM critiques its own retrieval and generation | Higher accuracy | High |
| **Active RAG** | Iterate until confidence threshold met | Quality guarantee | High |

**References:**
- [CRAG Paper](https://arxiv.org/abs/2401.15884)
- [Self-RAG Paper](https://arxiv.org/abs/2310.11511)

#### 4. Hierarchical & Graph-Based

| Technique | Description | Benefit | Complexity |
|-----------|-------------|---------|------------|
| **RAPTOR** | Build tree of summaries from leaf chunks | Multi-hop reasoning | High |
| **GraphRAG** | Entity extraction → knowledge graph → graph-aware retrieval | Complex relationships | Very High |
| **Agentic RAG** | Autonomous agent decides when/what to retrieve | Dynamic workflows | High |

**References:**
- [RAPTOR Paper](https://arxiv.org/abs/2401.18059)
- [Microsoft GraphRAG](https://www.microsoft.com/en-us/research/blog/graphrag-unlocking-llm-discovery-on-narrative-private-data/)

#### 5. Evaluation Frameworks

| Framework | Metrics | Use Case |
|-----------|---------|----------|
| **RAGAS** | Faithfulness, Answer Relevancy, Context Precision | Automated eval |
| **TruLens** | Groundedness, Context Relevance | Production monitoring |
| **DeepEval** | Hallucination, Toxicity, Bias | Safety checks |

**References:**
- [RAGAS Documentation](https://docs.ragas.io/)
- [TruLens Documentation](https://www.trulens.org/)

### DevChat v2.0 → v3.0 Upgrade Path

```
Current (v2.0)              →  Next Steps (v2.5)           →  Future (v3.0)
─────────────────────────────────────────────────────────────────────────────
Hybrid Search + Reranking   →  + Multi-Query RAG-Fusion    →  + ColBERTv2
Query Expansion             →  + Contextual Retrieval      →  + Late Chunking  
Adaptive Routing            →  + CRAG Sanity Check         →  + Self-RAG
Manual Evaluation           →  + RAGAS in CI               →  + TruLens Prod
Flat Chunks                 →  + Parent-Child Chunks       →  + RAPTOR Trees
```

---


