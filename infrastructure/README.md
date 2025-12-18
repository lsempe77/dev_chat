# Infrastructure Setup Guide

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         DEVCHAT v2.0 INFRASTRUCTURE                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   ┌──────────────────┐                      ┌──────────────────┐            │
│   │   Next.js UI     │──────────────────────│   FastAPI        │            │
│   │   (Vercel)       │    REST API          │   (Modal/Render) │            │
│   └──────────────────┘                      └────────┬─────────┘            │
│                                                      │                       │
│   ┌──────────────────────────────────────────────────┼───────────────────┐  │
│   │                         STORAGE                  │                    │  │
│   │                                                  │                    │  │
│   │   ┌──────────────┐  ┌──────────────┐  ┌─────────▼────────┐           │  │
│   │   │ Cloudflare   │  │   Turso      │  │   Qdrant Cloud   │           │  │
│   │   │ R2 (files)   │  │   (SQLite)   │  │   (vectors)      │           │  │
│   │   │              │  │              │  │                  │           │  │
│   │   │ $0 egress    │  │ 9GB free     │  │ 1GB free         │           │  │
│   │   └──────────────┘  └──────────────┘  └──────────────────┘           │  │
│   │                                                                       │  │
│   └───────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│   ┌───────────────────────────────────────────────────────────────────────┐  │
│   │                      PROCESSING (Modal)                                │  │
│   │                                                                        │  │
│   │   ┌─────────────────┐         ┌─────────────────┐                     │  │
│   │   │  orchestrator() │────────▶│  process_pdf()  │                     │  │
│   │   │  (CPU, $0.10/hr)│  spawn  │  (T4 GPU, $0.59)│                     │  │
│   │   └─────────────────┘         └─────────────────┘                     │  │
│   │                                                                        │  │
│   │   Scale: 0 → 10 workers automatically                                 │  │
│   │   Cost: ~$0.01 per PDF (30 pages)                                     │  │
│   │                                                                        │  │
│   └───────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 1. Cloudflare R2 Setup

### Create R2 Bucket

1. Go to [Cloudflare Dashboard](https://dash.cloudflare.com)
2. Select your account → R2 → Create bucket
3. Name: `devchat-pdfs`
4. Location: Auto (or select nearest region)

### Create API Token

1. R2 → Manage R2 API Tokens → Create API token
2. Permissions: Object Read & Write
3. Specify bucket: `devchat-pdfs`
4. Save the credentials:
   - Access Key ID
   - Secret Access Key
   - Account ID (from URL)

### Create Folder Structure

Upload a placeholder file to create folders:
```
devchat-pdfs/
├── input-pdfs/
│   └── .gitkeep
└── outputs/
    ├── md/
    │   └── .gitkeep
    └── json/
        └── .gitkeep
```

---

## 2. Qdrant Cloud Setup

### Create Cluster

1. Go to [Qdrant Cloud](https://cloud.qdrant.io)
2. Create Cluster → Free tier (1GB)
3. Region: Choose nearest
4. Save:
   - Cluster URL: `https://xxx.qdrant.io`
   - API Key

### Create Collection (Optional - auto-created by Modal)

```python
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance

client = QdrantClient(url="YOUR_URL", api_key="YOUR_KEY")

client.create_collection(
    collection_name="devchat_v2",
    vectors_config=VectorParams(
        size=1024,  # Cohere embed-v4 dimension
        distance=Distance.COSINE,
    ),
)
```

---

## 3. Turso Setup (SQLite Database)

### Create Database

1. Install CLI: `brew install tursodatabase/tap/turso` (or curl install)
2. Login: `turso auth login`
3. Create database:
   ```bash
   turso db create devchat-metadata
   turso db show devchat-metadata
   ```
4. Get credentials:
   - URL: `libsql://devchat-metadata-xxx.turso.io`
   - Token: `turso db tokens create devchat-metadata`

### Initialize Schema

```sql
-- Run via turso db shell devchat-metadata

CREATE TABLE documents (
    id TEXT PRIMARY KEY,
    r2_key TEXT NOT NULL,
    title TEXT,
    authors TEXT,  -- JSON array
    year INTEGER,
    status TEXT DEFAULT 'pending',  -- pending, processing, completed, failed
    error_message TEXT,
    page_count INTEGER,
    chunk_count INTEGER,
    created_at TEXT DEFAULT (datetime('now')),
    processed_at TEXT,
    file_hash TEXT
);

CREATE TABLE processing_jobs (
    id TEXT PRIMARY KEY,
    document_id TEXT REFERENCES documents(id),
    modal_task_id TEXT,
    status TEXT DEFAULT 'queued',
    started_at TEXT,
    completed_at TEXT,
    error TEXT
);

CREATE INDEX idx_documents_status ON documents(status);
CREATE INDEX idx_documents_hash ON documents(file_hash);
```

---

## 4. Modal Setup

### Install and Authenticate

```bash
pip install modal
modal token new
```

### Create Secrets

```bash
# R2 credentials
modal secret create r2-credentials \
    R2_ACCOUNT_ID=your_account_id \
    R2_ACCESS_KEY_ID=your_access_key \
    R2_SECRET_ACCESS_KEY=your_secret_key \
    R2_BUCKET_NAME=devchat-pdfs

# Qdrant credentials
modal secret create qdrant-credentials \
    QDRANT_URL=https://xxx.qdrant.io \
    QDRANT_API_KEY=your_api_key

# Cohere credentials
modal secret create cohere-credentials \
    COHERE_API_KEY=your_cohere_key

# Turso credentials (optional, for metadata DB)
modal secret create turso-credentials \
    TURSO_DATABASE_URL=libsql://xxx.turso.io \
    TURSO_AUTH_TOKEN=your_token
```

### Deploy

```bash
cd infrastructure
modal deploy modal_mineru.py
```

### Test

```bash
# Check status
modal run modal_mineru.py --action status

# Process all new PDFs
modal run modal_mineru.py --action run

# Process single PDF
modal run modal_mineru.py --action single --pdf-key "input-pdfs/paper.pdf"
```

---

## 5. Environment Variables Summary

### For Modal (Secrets)

| Secret Name | Variables |
|-------------|-----------|
| `r2-credentials` | `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET_NAME` |
| `qdrant-credentials` | `QDRANT_URL`, `QDRANT_API_KEY` |
| `cohere-credentials` | `COHERE_API_KEY` |
| `turso-credentials` | `TURSO_DATABASE_URL`, `TURSO_AUTH_TOKEN` |

### For FastAPI Backend (.env)

```env
# Storage
R2_ACCOUNT_ID=your_account_id
R2_ACCESS_KEY_ID=your_access_key
R2_SECRET_ACCESS_KEY=your_secret_key
R2_BUCKET_NAME=devchat-pdfs

# Vector DB (already configured)
QDRANT_URL=https://xxx.qdrant.cloud
QDRANT_API_KEY=your_key

# Embeddings (already configured)
COHERE_API_KEY=your_key

# Metadata DB
TURSO_DATABASE_URL=libsql://xxx.turso.io
TURSO_AUTH_TOKEN=your_token

# LLM (already configured)
OPENROUTER_API_KEY=your_key
```

### For Next.js Frontend (.env.local)

```env
NEXT_PUBLIC_API_URL=http://localhost:8000  # or production URL
```

---

## 6. Cost Estimates

### Free Tier Coverage

| Service | Free Tier | Your Usage Estimate | Status |
|---------|-----------|---------------------|--------|
| Cloudflare R2 | 10GB storage, 10M reads/mo | ~5GB, 100k reads | ✅ Free |
| Qdrant Cloud | 1GB vectors | ~500MB (50k chunks) | ✅ Free |
| Turso | 9GB, 500M reads/mo | ~100MB, 10k reads | ✅ Free |
| Cohere Embed | 1000 calls/min | ~500 calls/batch | ✅ Free |
| Modal | $30 credits/mo | ~20 GPU-hours | ✅ Covered |
| Vercel | Hobby free | Static hosting | ✅ Free |

### Paid Usage (1000+ PDFs/month)

| Service | Rate | 1000 PDFs/mo |
|---------|------|--------------|
| Modal GPU | $0.59/hr T4 | ~$12 (20 hrs) |
| R2 Storage | $0.015/GB | ~$0.15 (10GB) |
| Cohere | Free tier | $0 |
| **Total** | | **~$12/month** |

---

## 7. Deployment Commands Cheatsheet

```bash
# Modal
modal deploy infrastructure/modal_mineru.py    # Deploy
modal run infrastructure/modal_mineru.py       # Test run
modal app logs devchat-mineru                  # View logs

# Backend (local)
uvicorn api.server:app --reload --port 8000

# Frontend (local)
cd frontend && npm run dev

# Full stack (Docker)
docker-compose up -d
```

---

## 8. Troubleshooting

### Modal: "No GPU available"
- Free tier has limited GPU quota
- Try during off-peak hours or upgrade

### R2: "Access Denied"
- Check API token permissions (Object Read & Write)
- Verify bucket name in secrets

### Qdrant: "Collection not found"
- Collection auto-created on first upsert
- Or create manually (see section 2)

### MinerU: "CUDA out of memory"
- PDF too large for T4 (16GB VRAM)
- Split PDF or use A10G ($0.99/hr, 24GB)
