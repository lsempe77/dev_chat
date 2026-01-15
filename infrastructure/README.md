# Infrastructure Setup Guide

**Last Updated:** January 15, 2026

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         DEVCHAT v2.0 INFRASTRUCTURE                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   ┌──────────────────┐                      ┌──────────────────┐            │
│   │   Next.js UI     │──────────────────────│   FastAPI        │            │
│   │   (Vercel)       │    REST API          │   (Railway)      │            │
│   └──────────────────┘                      └────────┬─────────┘            │
│                                                      │                       │
│   ┌──────────────────────────────────────────────────┼───────────────────┐  │
│   │                         STORAGE                  │                    │  │
│   │                                                  │                    │  │
│   │   ┌──────────────┐  ┌──────────────┐  ┌─────────▼────────┐           │  │
│   │   │ Cloudflare   │  │   Supabase   │  │   Qdrant Cloud   │           │  │
│   │   │ R2 (files)   │  │  (PostgreSQL)│  │   (vectors)      │           │  │
│   │   │              │  │   + Auth     │  │                  │           │  │
│   │   │ $0 egress    │  │ 500MB free   │  │ 1GB free         │           │  │
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

## 3. Supabase Setup (PostgreSQL + Auth)

> **Note:** DevChat now uses Supabase instead of Turso for the metadata database.

### Create Supabase Project

1. Go to [supabase.com](https://supabase.com) and sign up
2. Create a new project (wait ~2 minutes for provisioning)
3. Go to **Project Settings** → **API** and copy:
   - `Project URL` (e.g., `https://xxxxx.supabase.co`)
   - `anon public` key (safe for frontend)
   - `service_role` key (backend only - NEVER expose!)

### Initialize Schema

1. Go to **SQL Editor** in your Supabase dashboard
2. Copy contents of `supabase/schema.sql` and run it
3. Run migrations from `scripts/migrations/` as needed

This creates:
- `rag_projects` - User's RAG projects
- `documents` - Documents per project
- `processing_jobs` - Async job tracking
- `usage_logs` - Usage/cost tracking
- Row Level Security policies

See **Section 7: Multi-Tenant Supabase Architecture** for full details.

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

# Supabase credentials
modal secret create supabase-credentials \
    SUPABASE_URL=https://xxx.supabase.co \
    SUPABASE_SERVICE_KEY=your_service_role_key

# OpenRouter credentials (for LLM)
modal secret create openrouter-credentials \
    OPENROUTER_API_KEY=your_openrouter_key
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
| `supabase-credentials` | `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` |
| `openrouter-credentials` | `OPENROUTER_API_KEY` |

### For FastAPI Backend (.env)

```env
# Storage
R2_ACCOUNT_ID=your_account_id
R2_ACCESS_KEY_ID=your_access_key
R2_SECRET_ACCESS_KEY=your_secret_key
R2_BUCKET_NAME=devchat-pdfs
R2_PUBLIC_URL=https://your-bucket.r2.dev

# Vector DB
QDRANT_URL=https://xxx.qdrant.cloud
QDRANT_API_KEY=your_key

# Embeddings & Reranking
COHERE_API_KEY=your_key

# Database & Auth (Supabase)
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_SERVICE_KEY=your_service_role_key

# LLM
OPENROUTER_API_KEY=your_key

# Observability
LANGFUSE_HOST=https://cloud.langfuse.com
LANGFUSE_PUBLIC_KEY=pk-xxx
LANGFUSE_SECRET_KEY=sk-xxx
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
| Supabase | 500MB, 5GB bandwidth | ~100MB, 10k queries | ✅ Free |
| Cohere Embed | 1000 calls/min | ~500 calls/batch | ✅ Free |
| Modal | $30 credits/mo | ~20 GPU-hours | ✅ Covered |
| Vercel | Hobby free | Static hosting | ✅ Free |
| Railway | $5 free/mo | API hosting | ✅ Free |

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


---

# Multi-Tenant Setup

# Multi-Tenant RAG Platform Setup Guide

This guide explains how to set up the multi-tenant RAG platform where users can create their own knowledge bases.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│  Frontend (Vercel)                                              │
│  ─────────────────                                              │
│  • /auth - Login/Signup (Supabase Auth)                        │
│  • /dashboard - Manage RAG projects                             │
│  • / - Chat with selected RAG                                   │
└─────────────────────────────────────────────────────────────────┘
              │ JWT Token
              ▼
┌─────────────────────────────────────────────────────────────────┐
│  Backend (Railway)                                              │
│  ─────────────────                                              │
│  • /rags/* - RAG project CRUD (authenticated)                  │
│  • /admin/* - Document management per RAG                       │
│  • /api/query - Chat with RAG (authenticated)                   │
└─────────────────────────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────────┐
│  Supabase                                                       │
│  ─────────                                                      │
│  • Authentication (users table - automatic)                     │
│  • PostgreSQL (rag_projects, documents, processing_jobs)        │
│  • Row Level Security (users see only their data)               │
└─────────────────────────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────────┐
│  Qdrant Cloud                                                   │
│  ────────────                                                   │
│  • One collection per RAG project                               │
│  • Collection name: rag_{project_id}                            │
└─────────────────────────────────────────────────────────────────┘
```

## Step 1: Create Supabase Project

1. Go to [supabase.com](https://supabase.com) and sign up
2. Create a new project
3. Wait for the project to be provisioned (~2 minutes)

## Step 2: Run Database Schema

1. Go to **SQL Editor** in your Supabase dashboard
2. Copy the contents of `supabase/schema.sql`
3. Paste and run the SQL

This creates:
- `rag_projects` - User's RAG projects
- `documents` - Documents per project
- `processing_jobs` - Async job tracking
- Row Level Security policies (users see only their data)
- Triggers for auto-generating collection names and updating stats

## Step 3: Get Supabase Credentials

Go to **Project Settings** → **API** and copy:

| Setting | Description |
|---------|-------------|
| `Project URL` | e.g., `https://xxxxx.supabase.co` |
| `anon public` key | Safe for frontend |
| `service_role` key | Backend only - NEVER expose! |

Go to **Project Settings** → **API** → **JWT Settings** for:
| Setting | Description |
|---------|-------------|
| `JWT Secret` | Optional - for local token verification |

## Step 4: Configure Backend (Railway)

Add these environment variables:

```bash
# Supabase
SUPABASE_URL=https://xxxxx.supabase.co
SUPABASE_ANON_KEY=eyJhbGc...
SUPABASE_SERVICE_ROLE_KEY=eyJhbGc...
SUPABASE_JWT_SECRET=your-jwt-secret  # Optional

# Keep existing config
QDRANT_URL=https://your-cluster.qdrant.io
QDRANT_API_KEY=your-qdrant-key
# Remove QDRANT_COLLECTION_NAME - now per-user
```

## Step 5: Configure Frontend (Vercel)

Add these environment variables:

```bash
NEXT_PUBLIC_SUPABASE_URL=https://xxxxx.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJhbGc...
NEXT_PUBLIC_API_URL=https://your-backend.railway.app
```

## Step 6: Deploy

### Backend (Railway)
```bash
git push railway main
```

### Frontend (Vercel)
```bash
cd frontend
vercel --prod
```

## User Flow

### New User
1. User visits `/auth`
2. Signs up with email/password
3. Confirms email (Supabase sends verification)
4. Logs in → redirected to `/dashboard`

### Create RAG
1. User clicks "New RAG Project"
2. Enters name and description
3. Backend creates:
   - Database record in `rag_projects`
   - New Qdrant collection: `rag_{project_id}`
4. User sees project in dashboard

### Upload Documents
1. User clicks "Manage" on a project
2. Uploads PDFs (stored in R2 with project prefix)
3. Documents processed via Modal
4. Chunks indexed to project's Qdrant collection

### Chat with RAG
1. User clicks "Chat" on a project
2. Frontend passes `?rag={project_id}` to chat
3. Backend queries that project's Qdrant collection

## API Endpoints

### Authentication (no auth required)
- `GET /admin/auth-status` - Check if logged in
- `POST /admin/login` - Legacy password login

### RAG Projects (requires Supabase JWT)
- `GET /rags` - List user's projects
- `POST /rags` - Create new project
- `GET /rags/{id}` - Get project details
- `PATCH /rags/{id}` - Update project
- `DELETE /rags/{id}` - Delete project + Qdrant collection

### Document Management (requires auth + project context)
- All `/admin/*` routes now require project context
- Pass `X-RAG-Project-ID` header or query param

## Security Notes

1. **Row Level Security**: Supabase RLS ensures users only see their own data
2. **JWT Verification**: Backend verifies Supabase JWT tokens
3. **Service Role Key**: Only used on backend for admin operations
4. **Collection Isolation**: Each user's documents in separate Qdrant collection

## Fallback: Legacy Mode

If Supabase is not configured, the system falls back to:
- Single-tenant mode (existing behavior)
- Password-based admin auth
- Single Qdrant collection from `QDRANT_COLLECTION_NAME`

