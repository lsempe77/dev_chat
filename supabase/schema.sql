-- DevChat Multi-Tenant RAG Schema
-- Run this in Supabase SQL Editor to set up the database

-- =============================================================================
-- RAG Projects Table
-- =============================================================================
-- Each user can create multiple RAG projects
-- Each RAG project has its own Qdrant collection

CREATE TABLE IF NOT EXISTS rag_projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    
    -- Project info
    name TEXT NOT NULL,
    description TEXT,
    slug TEXT UNIQUE,  -- URL-friendly identifier (e.g., "my-research-rag")
    
    -- Qdrant collection (auto-generated: rag_{id})
    qdrant_collection TEXT NOT NULL UNIQUE,
    
    -- Access control
    is_public BOOLEAN NOT NULL DEFAULT false,  -- If true, anyone can chat with this RAG
    
    -- Status
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'processing', 'error', 'deleted')),
    
    -- Stats (denormalized for performance)
    document_count INTEGER NOT NULL DEFAULT 0,
    chunk_count INTEGER NOT NULL DEFAULT 0,
    
    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- Ensure unique names per user
    UNIQUE(user_id, name)
);

-- Index for fast user lookups
CREATE INDEX IF NOT EXISTS idx_rag_projects_user_id ON rag_projects(user_id);
CREATE INDEX IF NOT EXISTS idx_rag_projects_qdrant_collection ON rag_projects(qdrant_collection);
CREATE INDEX IF NOT EXISTS idx_rag_projects_slug ON rag_projects(slug);
CREATE INDEX IF NOT EXISTS idx_rag_projects_is_public ON rag_projects(is_public) WHERE is_public = true;

-- =============================================================================
-- Documents Table  
-- =============================================================================
-- Track documents per RAG project

CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rag_project_id UUID NOT NULL REFERENCES rag_projects(id) ON DELETE CASCADE,
    
    -- Document info
    filename TEXT NOT NULL,
    original_filename TEXT NOT NULL,
    file_size_bytes BIGINT,
    mime_type TEXT,
    
    -- Processing status
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
    error_message TEXT,
    
    -- R2 storage paths
    r2_input_key TEXT,  -- input-pdfs/{rag_id}/{filename}
    r2_output_key TEXT, -- output-markdown/{rag_id}/{filename}/
    
    -- Metadata (extracted or user-provided)
    metadata JSONB NOT NULL DEFAULT '{}',
    
    -- Stats
    chunk_count INTEGER NOT NULL DEFAULT 0,
    
    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_at TIMESTAMPTZ
);

-- Index for fast project lookups
CREATE INDEX IF NOT EXISTS idx_documents_rag_project_id ON documents(rag_project_id);
CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status);

-- =============================================================================
-- Processing Jobs Table
-- =============================================================================
-- Track async processing jobs

CREATE TABLE IF NOT EXISTS processing_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rag_project_id UUID NOT NULL REFERENCES rag_projects(id) ON DELETE CASCADE,
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    
    -- Job info
    job_type TEXT NOT NULL CHECK (job_type IN ('ingest', 'reprocess', 'delete', 'embed')),
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'running', 'completed', 'failed')),
    
    -- Progress tracking
    progress INTEGER NOT NULL DEFAULT 0 CHECK (progress >= 0 AND progress <= 100),
    message TEXT,
    error_message TEXT,
    
    -- External job reference (e.g., Modal call ID)
    external_job_id TEXT,
    
    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ
);

-- Index for fast lookups
CREATE INDEX IF NOT EXISTS idx_processing_jobs_rag_project_id ON processing_jobs(rag_project_id);
CREATE INDEX IF NOT EXISTS idx_processing_jobs_status ON processing_jobs(status);

-- =============================================================================
-- Row Level Security (RLS) Policies
-- =============================================================================
-- Users can only see/modify their own data

ALTER TABLE rag_projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE processing_jobs ENABLE ROW LEVEL SECURITY;

-- RAG Projects: Users can only access their own projects
CREATE POLICY "Users can view own rag_projects"
    ON rag_projects FOR SELECT
    USING (auth.uid() = user_id);

-- Public RAGs: Anyone can view public projects (for chat)
CREATE POLICY "Anyone can view public rag_projects"
    ON rag_projects FOR SELECT
    USING (is_public = true);

CREATE POLICY "Users can insert own rag_projects"
    ON rag_projects FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own rag_projects"
    ON rag_projects FOR UPDATE
    USING (auth.uid() = user_id);

CREATE POLICY "Users can delete own rag_projects"
    ON rag_projects FOR DELETE
    USING (auth.uid() = user_id);

-- Documents: Users can access documents in their projects
CREATE POLICY "Users can view documents in own projects"
    ON documents FOR SELECT
    USING (
        rag_project_id IN (
            SELECT id FROM rag_projects WHERE user_id = auth.uid()
        )
    );

CREATE POLICY "Users can insert documents in own projects"
    ON documents FOR INSERT
    WITH CHECK (
        rag_project_id IN (
            SELECT id FROM rag_projects WHERE user_id = auth.uid()
        )
    );

CREATE POLICY "Users can update documents in own projects"
    ON documents FOR UPDATE
    USING (
        rag_project_id IN (
            SELECT id FROM rag_projects WHERE user_id = auth.uid()
        )
    );

CREATE POLICY "Users can delete documents in own projects"
    ON documents FOR DELETE
    USING (
        rag_project_id IN (
            SELECT id FROM rag_projects WHERE user_id = auth.uid()
        )
    );

-- Processing Jobs: Users can access jobs in their projects
CREATE POLICY "Users can view jobs in own projects"
    ON processing_jobs FOR SELECT
    USING (
        rag_project_id IN (
            SELECT id FROM rag_projects WHERE user_id = auth.uid()
        )
    );

CREATE POLICY "Users can insert jobs in own projects"
    ON processing_jobs FOR INSERT
    WITH CHECK (
        rag_project_id IN (
            SELECT id FROM rag_projects WHERE user_id = auth.uid()
        )
    );

-- =============================================================================
-- Updated_at Trigger
-- =============================================================================

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_rag_projects_updated_at
    BEFORE UPDATE ON rag_projects
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_documents_updated_at
    BEFORE UPDATE ON documents
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- =============================================================================
-- Helper Functions
-- =============================================================================

-- Generate unique Qdrant collection name
CREATE OR REPLACE FUNCTION generate_qdrant_collection_name()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.qdrant_collection IS NULL THEN
        NEW.qdrant_collection := 'rag_' || REPLACE(NEW.id::TEXT, '-', '');
    END IF;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER set_qdrant_collection_name
    BEFORE INSERT ON rag_projects
    FOR EACH ROW
    EXECUTE FUNCTION generate_qdrant_collection_name();

-- Update document/chunk counts on rag_projects
CREATE OR REPLACE FUNCTION update_rag_project_stats()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' OR TG_OP = 'UPDATE' THEN
        UPDATE rag_projects 
        SET 
            document_count = (SELECT COUNT(*) FROM documents WHERE rag_project_id = NEW.rag_project_id),
            chunk_count = (SELECT COALESCE(SUM(chunk_count), 0) FROM documents WHERE rag_project_id = NEW.rag_project_id)
        WHERE id = NEW.rag_project_id;
        RETURN NEW;
    ELSIF TG_OP = 'DELETE' THEN
        UPDATE rag_projects 
        SET 
            document_count = (SELECT COUNT(*) FROM documents WHERE rag_project_id = OLD.rag_project_id),
            chunk_count = (SELECT COALESCE(SUM(chunk_count), 0) FROM documents WHERE rag_project_id = OLD.rag_project_id)
        WHERE id = OLD.rag_project_id;
        RETURN OLD;
    END IF;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_rag_stats_on_document_change
    AFTER INSERT OR UPDATE OR DELETE ON documents
    FOR EACH ROW
    EXECUTE FUNCTION update_rag_project_stats();
