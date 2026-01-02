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
