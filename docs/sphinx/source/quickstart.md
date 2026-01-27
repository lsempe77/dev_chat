# Quickstart

## Prerequisites

- Python 3.12+
- Node.js 18+
- Access to: Supabase, Qdrant, Cohere, OpenRouter, Cloudflare R2, Modal

## Local Development

### 1. Clone Repository

```bash
git clone https://github.com/lsempe77/dev_chat.git
cd dev_chat
```

### 2. Backend Setup

```bash
# Create virtual environment
python -m venv .venv
.venv\Scripts\activate  # Windows
source .venv/bin/activate  # Linux/Mac

# Install dependencies
pip install -r requirements.txt

# Copy environment variables
cp .env.example .env
# Edit .env with your API keys

# Run backend
uvicorn api.server:app --reload --port 8000
```

### 3. Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

### 4. Modal Setup (PDF Processing)

```bash
# Login to Modal
modal token new

# Test locally
modal run infrastructure/modal_mineru.py --help

# Deploy
modal deploy infrastructure/modal_mineru.py
```

## Environment Variables

```bash
# Database
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_SERVICE_KEY=eyJ...

# Vector DB
QDRANT_URL=https://xxx.qdrant.io
QDRANT_API_KEY=xxx

# LLM
OPENROUTER_API_KEY=sk-or-xxx

# Embeddings & Reranking
COHERE_API_KEY=xxx

# Storage
CLOUDFLARE_R2_ACCESS_KEY_ID=xxx
CLOUDFLARE_R2_SECRET_ACCESS_KEY=xxx
CLOUDFLARE_R2_BUCKET=devchat-pdfs
CLOUDFLARE_R2_ENDPOINT=https://xxx.r2.cloudflarestorage.com

# Observability
LANGFUSE_HOST=https://cloud.langfuse.com
LANGFUSE_PUBLIC_KEY=pk-xxx
LANGFUSE_SECRET_KEY=sk-xxx
```

## Running Tests

```bash
# Python tests
pytest tests/

# Frontend tests
cd frontend && npm test
```

## Common Tasks

### Process a PDF

```bash
# Via Modal CLI
modal run infrastructure/modal_mineru.py::process_document \
  --project-id "your-project-id" \
  --pdf-key "path/to/file.pdf"
```

### Run Extraction Pipeline

```bash
cd extraction_pipeline
python pipeline.py --study_id 121058356
```

### Validate Extraction

```bash
cd evaluation
python validate_extraction.py
```
