# Overview

DevChat is a RAG-powered research workbench designed for academic literature analysis at 3ie (International Initiative for Impact Evaluation).

## What is DevChat?

DevChat helps researchers:

1. **Upload and process** academic papers (PDFs) with AI-powered parsing
2. **Search** across their document corpus using hybrid semantic + keyword search  
3. **Get answers** with inline citations verified by NLI models
4. **Extract data** from results tables (coefficients, standard errors, p-values)

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
- Admin endpoints for document management

### PDF Processing (Modal)
- GPU-accelerated PDF parsing with MineRU
- Table and formula extraction
- Contextual chunking with Claude
- Vector embedding with Cohere

### Vector Database (Qdrant)
- Hybrid search (dense + sparse vectors)
- Binary quantization for fast search
- Multi-tenant with collection per project

### Synthesis Pipeline
- Claim Ledger: Two-pass extraction with citations
- MiniCheck: NLI verification of claims
- Study design classification

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
