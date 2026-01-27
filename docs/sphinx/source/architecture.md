# Architecture

## System Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                           Frontend (Vercel)                          │
│                         Next.js + React + shadcn                     │
└─────────────────────────────────┬───────────────────────────────────┘
                                  │ HTTPS
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                          Backend (Railway)                           │
│                       FastAPI + Python 3.12                          │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────────────┐ │
│  │  /chat   │  │  /rags   │  │ /admin/* │  │   /api/documents/*   │ │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └──────────┬───────────┘ │
└───────┼─────────────┼─────────────┼────────────────────┼────────────┘
        │             │             │                    │
        ▼             ▼             ▼                    ▼
┌───────────────┐ ┌────────────┐ ┌────────────┐ ┌──────────────────┐
│    Qdrant     │ │  Supabase  │ │  Langfuse  │ │  Cloudflare R2   │
│  (Vectors)    │ │   (Auth)   │ │  (Traces)  │ │   (PDF Storage)  │
└───────────────┘ └────────────┘ └────────────┘ └────────┬─────────┘
                                                         │
                                                         ▼
                                               ┌──────────────────┐
                                               │  Modal (GPU)     │
                                               │  MineRU Parser   │
                                               └──────────────────┘
```

## Data Flow

### Document Upload Flow

1. User uploads PDF via frontend
2. Backend stores PDF in Cloudflare R2
3. Backend triggers Modal job
4. Modal:
   - Downloads PDF from R2
   - Parses with MineRU (extracts text, tables, formulas)
   - Chunks with contextual retrieval
   - Embeds with Cohere
   - Indexes in Qdrant
5. Backend updates document status in Supabase

### Query Flow

1. User sends query via chat
2. Backend:
   - Generates query variants (Multi-Query RAG-Fusion)
   - Searches Qdrant (hybrid: dense + sparse)
   - Reranks with Cohere rerank-v3.5
   - Applies MMR diversity
   - Reorders for Lost-in-Middle
3. ClaimLedger synthesizes answer with citations
4. MiniCheck verifies claims
5. Response streamed to frontend

## Module Structure

```
src/
├── agents/           # DevChatAgent - main orchestrator
├── generation/       # Synthesis and verification
│   ├── claim_ledger.py      # Two-pass citation extraction
│   ├── post_hoc_verifier.py # MiniCheck NLI
│   └── synthesizer.py       # Response generation
├── retrieval/        # Search and ranking
│   ├── hybrid_retriever.py  # Dense + sparse search
│   ├── reranker.py          # Cohere reranking
│   └── context_builder.py   # Context assembly
├── ingestion/        # Document processing
│   ├── chunking.py          # Text chunking
│   ├── contextualizer.py    # Contextual retrieval
│   └── embeddings.py        # Vector generation
└── config/           # Settings and prompts
```

## Key Design Decisions

### Hybrid Search
Combines dense (semantic) and sparse (BM25) vectors for better retrieval. Dense captures meaning, sparse handles exact terms and acronyms.

### Binary Quantization
Qdrant stores 1024-dim Cohere vectors as binary (32x compression). Search happens in binary space, then rescores top candidates with full vectors.

### Claim Ledger
Two-pass extraction: first identifies claims with citations, second verifies each citation against source text using NLI.

### Multi-tenant Architecture
Each RAG project has its own Qdrant collection. Supabase RLS ensures users only see their own data.
