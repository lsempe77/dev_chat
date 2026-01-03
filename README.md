# DevChat v2.0 - Multi-Tenant RAG Platform

**DevChat** is an AI-powered **Research Workbench** for exploring academic literature with state-of-the-art RAG (Retrieval-Augmented Generation).

**Live Demo:** https://dev-chat-frontend.vercel.app/

---

## 📊 Current Status (January 2026)

| Component | Status | URL/Notes |
|-----------|--------|-----------|
| **Frontend** | ✅ Live | Vercel - Next.js 15 |
| **Backend** | ✅ Live | Railway - FastAPI |
| **PDF Processing** | ✅ Working | Modal - MinerU GPU |
| **Vector DB** | ✅ Connected | Qdrant Cloud |
| **Auth & Database** | ✅ Working | Supabase |
| **Multi-Tenant RAG** | ✅ Done | Per-user projects with isolated collections |

### Citation Quality Metrics

| Metric | Score | Target |
|--------|-------|--------|
| **Faithfulness** | 0.699 | 0.70+ ✅ |
| **Citation Recall** | 1.000 | 0.70 ✅ |
| **Citation Precision** | 1.000 | 0.70 ✅ |

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Frontend (Vercel) - Next.js 15                                │
│  • /auth - Login/Signup (Supabase Auth)                        │
│  • /dashboard - Create & manage RAG projects                    │
│  • /r/{slug} - Chat with public RAGs                           │
└─────────────────────────────────────────────────────────────────┘
              │ JWT Token
              ▼
┌─────────────────────────────────────────────────────────────────┐
│  Backend (Railway) - FastAPI                                    │
│  • /rags/* - RAG project CRUD                                  │
│  • /api/query - Chat with document context                      │
│  • /admin/* - Document & metadata management                    │
└─────────────────────────────────────────────────────────────────┘
              │
              ▼
┌───────────────────────────────────────┬─────────────────────────┐
│  Supabase                             │  Qdrant Cloud           │
│  • Auth (users)                       │  • Vector collections    │
│  • PostgreSQL (projects, docs)        │  • Dense + Sparse search │
│  • Row Level Security                 │  • Per-project isolation │
└───────────────────────────────────────┴─────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────────┐
│  Modal (GPU Processing)                                         │
│  • MinerU PDF parsing                                           │
│  • Cohere embeddings (dense + sparse)                           │
│  • Metadata enrichment (CrossRef/OpenAlex)                      │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🚀 Key Features

### Multi-Tenant RAG
- Users create their own RAG projects with isolated document collections
- Public sharing via slugs (e.g., `/r/graduation`)
- Per-project Qdrant collections

### Smart Document Processing
- **MinerU GPU parsing** - High-quality PDF to markdown
- **CrossRef/OpenAlex enrichment** - Automatic metadata lookup
- **Hybrid indexing** - Dense (Cohere) + Sparse (BM25) vectors

### Advanced Retrieval
- **Hybrid Search** - Combines semantic + keyword matching
- **Cohere Reranking** - Precision filtering
- **Metadata filtering** - Year, country, sector, study type

### Citation Quality
- **Claim Ledger synthesis** - Grounded, citation-rich responses
- **Page-aware chunking** - Click citations to jump to PDF page
- **Post-hoc verification** - NLI-based faithfulness checking

---

## 📁 Project Structure

```
devchat_v2_sota/
├── api/                    # FastAPI backend
│   ├── routes/            # Modular route handlers
│   └── schemas/           # Pydantic models
├── src/                    # Core libraries
│   ├── agents/            # RAG agent logic
│   ├── retrieval/         # Hybrid retriever
│   ├── generation/        # LLM synthesis
│   └── ingestion/         # Embeddings, metadata
├── frontend/               # Next.js 15 app
│   └── src/
│       ├── app/           # App router pages
│       ├── components/    # React components
│       └── lib/           # API clients
├── infrastructure/         # Modal, Docker configs
├── evaluation/             # Citation quality metrics
├── scripts/                # Utility scripts
├── docs/                   # Documentation
└── archive/                # Historical files
```

---

## 🔧 Tech Stack

| Layer | Technology |
|-------|------------|
| **Frontend** | Next.js 15, TypeScript, Tailwind, shadcn/ui |
| **Backend** | FastAPI, Python 3.12 |
| **Auth** | Supabase Auth (JWT) |
| **Database** | Supabase PostgreSQL |
| **Vector Store** | Qdrant Cloud |
| **Embeddings** | Cohere embed-v4 (1536 dims) |
| **Sparse Vectors** | BM25-style (hybrid search) |
| **Reranking** | Cohere rerank-v3.5 |
| **LLM** | OpenRouter (GPT-4o, GPT-4o-mini) |
| **PDF Parsing** | MinerU 2.6.8 (Modal GPU) |
| **Storage** | Cloudflare R2 |
| **Observability** | Langfuse |

---

## 🚀 Quick Start

### Prerequisites
- Python 3.12+
- Node.js 18+
- Supabase account
- Qdrant Cloud account
- Modal account
- Cohere API key
- OpenRouter API key

### Backend Setup

```bash
# Clone and install
git clone https://github.com/lsempe77/dev_chat.git
cd dev_chat
pip install -e .

# Configure environment
cp .env.example .env
# Edit .env with your API keys

# Run locally
uvicorn api.server:app --reload
```

### Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

### Deploy Modal Worker

```bash
modal deploy infrastructure/modal_mineru.py
```

---

## 📚 Documentation

- [Multi-Tenant Setup Guide](docs/MULTI_TENANT_SETUP.md)
- [CHANGELOG](CHANGELOG.md)

---

## 📄 License

MIT License - See LICENSE file for details.

---

**Built with ❤️ for 3ie (International Initiative for Impact Evaluation)**
