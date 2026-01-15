# Post 5: Supabase Database Setup

**Part 5 of 50** | ⏱️ 45 minutes | [← Previous](04-nextjs-basics.md) | [Next: Authentication →](06-authentication.md)

---

## 🎯 What You'll Learn

- Supabase PostgreSQL fundamentals
- Database schema design for multi-tenancy
- Row-Level Security (RLS)
- Migrations and schema management
- Real DevChat database structure

---

## 📖 What is Supabase?

**Supabase** is an open-source Firebase alternative built on PostgreSQL. It provides:
- 🗄️ **PostgreSQL database**: Full SQL power
- 🔐 **Built-in auth**: User management out of the box
- 🛡️ **Row-Level Security**: Database-level authorization
- 📡 **Auto-generated APIs**: RESTful and real-time
- 📦 **Storage**: File uploads and CDN

### Why Supabase for DevChat?

```sql
-- Traditional approach: Check permissions in app code
SELECT * FROM documents WHERE id = 123
-- ❌ App must check if user can access document
-- ❌ Easy to forget permission checks
-- ❌ Security bugs

-- Supabase RLS: Enforce in database
SELECT * FROM documents WHERE id = 123
-- ✅ Database automatically filters by user_id
-- ✅ Impossible to bypass
-- ✅ Security guaranteed
```

---

## 🗄️ DevChat Database Schema

### Core Tables

```
┌─────────────┐
│   users     │ (managed by Supabase Auth)
└──────┬──────┘
       │
       ├──────────────────┐
       │                  │
┌──────▼──────┐    ┌──────▼──────────┐
│ rag_projects│    │  usage_logs     │
└──────┬──────┘    └─────────────────┘
       │
       ├──────────────────┬──────────────────┐
       │                  │                  │
┌──────▼──────┐    ┌──────▼──────┐   ┌──────▼──────┐
│  documents  │    │ chat_history│   │project_config│
└──────┬──────┘    └─────────────┘   └─────────────┘
       │
┌──────▼──────┐
│document_meta│
└─────────────┘
```

### 1. RAG Projects

```sql
CREATE TABLE rag_projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id),
    name VARCHAR(100) NOT NULL,
    description TEXT,
    model VARCHAR(50) DEFAULT 'gpt-4o',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for fast user lookups
CREATE INDEX idx_projects_user ON rag_projects(user_id);
```

**Purpose:** Isolate document collections per user/project.

### 2. Documents

```sql
CREATE TABLE documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES rag_projects(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES auth.users(id),
    title VARCHAR(500) NOT NULL,
    file_path TEXT,
    file_size INTEGER,
    status VARCHAR(20) DEFAULT 'pending',
    -- pending | processing | completed | failed
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Compound index for project-specific queries
CREATE INDEX idx_docs_project ON documents(project_id, created_at DESC);
CREATE INDEX idx_docs_status ON documents(status) WHERE status = 'pending';
```

**Purpose:** Track uploaded documents and processing status.

### 3. Document Metadata

```sql
CREATE TABLE document_metadata (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    doi VARCHAR(255),
    authors TEXT[],  -- Array of author names
    year INTEGER,
    journal VARCHAR(500),
    abstract TEXT,
    keywords TEXT[],
    study_design VARCHAR(50),
    -- RCT | Quasi-experimental | Observational | etc.
    enriched_at TIMESTAMPTZ
);

-- Index for search by DOI
CREATE INDEX idx_metadata_doi ON document_metadata(doi);
CREATE INDEX idx_metadata_year ON document_metadata(year);
```

**Purpose:** Store enriched metadata from external sources.

### 4. Chat History

```sql
CREATE TABLE chat_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES rag_projects(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES auth.users(id),
    query TEXT NOT NULL,
    response TEXT NOT NULL,
    citations JSONB,  -- Array of citation objects
    tokens_used INTEGER,
    latency_ms INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for recent chat history
CREATE INDEX idx_chat_project ON chat_history(project_id, created_at DESC);
```

**Purpose:** Audit trail and usage analytics.

### 5. Usage Logs

```sql
CREATE TABLE usage_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id),
    project_id UUID REFERENCES rag_projects(id),
    operation VARCHAR(50) NOT NULL,
    -- chat | upload | enrich | export
    model VARCHAR(50),
    tokens_input INTEGER,
    tokens_output INTEGER,
    cost_usd DECIMAL(10, 6),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for cost reporting
CREATE INDEX idx_usage_user_date ON usage_logs(user_id, created_at);
```

**Purpose:** Track costs per user and project.

---

## 🛡️ Row-Level Security (RLS)

### The Authorization Problem

Imagine you're building a notes app. Every user should only see their own notes, right?

**Traditional approach (check in application code):**

```python
# In your API endpoint
@app.get("/notes")
def get_notes(user_id: str):
    # YOU have to remember to filter by user_id
    notes = db.query("SELECT * FROM notes WHERE user_id = ?", user_id)
    return notes

# Another endpoint
@app.delete("/notes/{id}")
def delete_note(note_id: str, user_id: str):
    # YOU have to remember to check ownership
    note = db.query("SELECT * FROM notes WHERE id = ?", note_id)
    if note.user_id != user_id:  # EASY TO FORGET!
        raise Exception("Not authorized")
    db.delete(note_id)
```

**Problems:**
- ❌ You might forget the check in one endpoint
- ❌ Security depends on perfect code
- ❌ Junior dev could expose all data by accident
- ❌ One SQL injection = all data exposed

### Row-Level Security: Database Enforces Access

**Supabase RLS approach:**

```sql
-- Set up RLS policy ONCE in the database
CREATE POLICY "Users can only see own notes"
ON notes
FOR SELECT
USING (auth.uid() = user_id);
```

**Now in your application:**

```python
# You don't need to filter anymore!
@app.get("/notes")
def get_notes():
    # This AUTOMATICALLY only returns the user's notes
    # Even if you forget to filter!
    notes = supabase.table("notes").select("*").execute()
    return notes.data  # Only user's notes - guaranteed!

@app.delete("/notes/{id}")
def delete_note(note_id: str):
    # This AUTOMATICALLY fails if user doesn't own the note
    supabase.table("notes").delete().eq("id", note_id).execute()
    # If they don't own it, nothing happens - safe!
```

**Why this is magical:**

1. **Cannot be bypassed**: Even if you write `SELECT * FROM notes` (no filter), the database automatically adds `WHERE user_id = current_user`

2. **Prevents accidents**: Junior dev forgets to check permissions? Database still protects the data.

3. **SQL injection safe**: Even malicious SQL can't access other users' data.

4. **Less code**: No permission checks scattered everywhere.

### How It Works

```
1. User logs in → Gets JWT token with user_id
2. Frontend sends request with token
3. Supabase extracts user_id from token
4. Database uses auth.uid() in policies
5. Every query automatically filtered!

  SELECT * FROM notes
    ↓
  SELECT * FROM notes WHERE user_id = 'abc123'
```

**Example: Multi-user query**

```python
# Alice's code (user_id = 'alice')
notes = supabase.table("notes").select("*").execute()
# Database executes: SELECT * FROM notes WHERE user_id = 'alice'
# Returns: Only Alice's notes

# Bob's code (user_id = 'bob') - SAME CODE!
notes = supabase.table("notes").select("*").execute()
# Database executes: SELECT * FROM notes WHERE user_id = 'bob'
# Returns: Only Bob's notes
```

Same code, different user, correct data every time!

### Enable RLS

```sql
ALTER TABLE rag_projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE chat_history ENABLE ROW LEVEL SECURITY;
```

### Create Policies

#### 1. Users can only see their own projects

```sql
CREATE POLICY "Users can view own projects"
ON rag_projects
FOR SELECT
USING (auth.uid() = user_id);

CREATE POLICY "Users can create own projects"
ON rag_projects
FOR INSERT
WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own projects"
ON rag_projects
FOR UPDATE
USING (auth.uid() = user_id);

CREATE POLICY "Users can delete own projects"
ON rag_projects
FOR DELETE
USING (auth.uid() = user_id);
```

#### 2. Users can only access documents in their projects

```sql
CREATE POLICY "Users can view own documents"
ON documents
FOR SELECT
USING (
    auth.uid() = user_id
    OR
    -- Or document belongs to user's project
    project_id IN (
        SELECT id FROM rag_projects WHERE user_id = auth.uid()
    )
);

CREATE POLICY "Users can create documents in own projects"
ON documents
FOR INSERT
WITH CHECK (
    auth.uid() = user_id
    AND
    project_id IN (
        SELECT id FROM rag_projects WHERE user_id = auth.uid()
    )
);
```

#### 3. Admin override (for admin panel)

```sql
CREATE POLICY "Admins can view all projects"
ON rag_projects
FOR SELECT
USING (
    auth.uid() IN (
        SELECT id FROM auth.users WHERE raw_user_meta_data->>'role' = 'admin'
    )
);
```

---

## 📝 Migrations

DevChat uses SQL migration files to version control schema changes.

### Migration Structure

```
scripts/migrations/
├── 001_initial_schema.sql
├── 002_add_metadata.sql
├── 003_add_usage_logs.sql
└── 004_add_rls_policies.sql
```

### Example Migration

`scripts/migrations/002_add_metadata.sql`:

```sql
-- Migration: Add document metadata table
-- Date: 2026-01-10

BEGIN;

-- Create table
CREATE TABLE IF NOT EXISTS document_metadata (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    doi VARCHAR(255),
    authors TEXT[],
    year INTEGER,
    journal VARCHAR(500),
    abstract TEXT,
    keywords TEXT[],
    study_design VARCHAR(50),
    enriched_at TIMESTAMPTZ DEFAULT NOW()
);

-- Add indexes
CREATE INDEX idx_metadata_doc ON document_metadata(document_id);
CREATE INDEX idx_metadata_doi ON document_metadata(doi);

-- Enable RLS
ALTER TABLE document_metadata ENABLE ROW LEVEL SECURITY;

-- Policy: Users can see metadata for their documents
CREATE POLICY "Users can view document metadata"
ON document_metadata
FOR SELECT
USING (
    document_id IN (
        SELECT id FROM documents WHERE user_id = auth.uid()
    )
);

COMMIT;
```

### Run Migrations

```python
# scripts/run_migration.py
from supabase import create_client
import os

supabase = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_SERVICE_KEY")  # Service key bypasses RLS
)

def run_migration(filepath: str):
    with open(filepath) as f:
        sql = f.read()
    
    try:
        supabase.rpc("exec_sql", {"sql": sql}).execute()
        print(f"✅ Migration {filepath} completed")
    except Exception as e:
        print(f"❌ Migration failed: {e}")
```

---

## 🔍 Querying with Supabase Client

### Python Client

```python
from supabase import create_client

supabase = create_client(
    supabase_url="https://xxx.supabase.co",
    supabase_key="your-service-key"
)

# Simple query
projects = supabase.table("rag_projects")\\
    .select("*")\\
    .eq("user_id", user_id)\\
    .execute()

# Join query
documents = supabase.table("documents")\\
    .select("""
        *,
        document_metadata(*),
        rag_projects(name)
    """)\\
    .eq("project_id", project_id)\\
    .order("created_at", desc=True)\\
    .limit(10)\\
    .execute()

# Insert
new_project = supabase.table("rag_projects").insert({
    "user_id": user_id,
    "name": "My Project",
    "model": "gpt-4o"
}).execute()

# Update
supabase.table("documents")\\
    .update({"status": "completed"})\\
    .eq("id", doc_id)\\
    .execute()
```

### TypeScript Client

```typescript
import { createClient } from '@supabase/supabase-js'

const supabase = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL,
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY
)

// Query
const { data: projects, error } = await supabase
  .from('rag_projects')
  .select('*')
  .eq('user_id', userId)

// With types
interface Project {
  id: string
  name: string
  created_at: string
}

const { data, error } = await supabase
  .from('rag_projects')
  .select<'*', Project>('*')
```

---

## 💡 Real DevChat Example: Project Creation

From `api/routes/api.py`:

```python
from supabase import create_client
from pydantic import BaseModel

class CreateProjectRequest(BaseModel):
    name: str
    description: str | None = None

async def create_project(
    request: CreateProjectRequest,
    user_id: str
):
    """Create a new RAG project."""
    
    # Check user limit
    existing = supabase.table("rag_projects")\\
        .select("id", count="exact")\\
        .eq("user_id", user_id)\\
        .execute()
    
    if existing.count >= 10:
        raise Exception("Maximum 10 projects per user")
    
    # Create project
    project = supabase.table("rag_projects").insert({
        "user_id": user_id,
        "name": request.name,
        "description": request.description,
        "model": "gpt-4o",
    }).execute()
    
    # Create default config
    supabase.table("project_config").insert({
        "project_id": project.data[0]["id"],
        "prompt_template": "You are a research assistant...",
        "temperature": 0.7,
        "max_tokens": 1000,
    }).execute()
    
    return project.data[0]
```

---

## ✅ Knowledge Check

1. What does RLS stand for and why is it important?
2. What happens to documents when you delete a project?
3. How do you query data across multiple tables?
4. What's the difference between the service key and anon key?
5. Why use migrations instead of manual SQL?

<details>
<summary>Answers</summary>

1. Row-Level Security - enforces authorization at database level
2. They're deleted automatically due to `ON DELETE CASCADE`
3. Use `.select()` with joined table names: `.select("*, rag_projects(*)")`
4. Service key bypasses RLS (backend only), anon key respects RLS (frontend safe)
5. Migrations version control schema, enable rollbacks, and ensure consistency

</details>

---

**Next:** [Post 6: Authentication & Authorization →](06-authentication.md)

Learn how to implement user authentication with Supabase Auth.

---

[🏠 Back to Index](../README.md) | [← Previous](04-nextjs-basics.md) | [Next: Authentication →](06-authentication.md)
