-- Migration: Add Zotero Connection table for RAG projects
-- Phase 3: Zotero Integration
-- Date: 2026-01-03

-- =============================================================================
-- Zotero Connection Table
-- =============================================================================
-- Stores Zotero API credentials and sync configuration per RAG project
-- Each RAG project can have one Zotero connection

CREATE TABLE IF NOT EXISTS zotero_connections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rag_project_id UUID NOT NULL REFERENCES rag_projects(id) ON DELETE CASCADE,
    
    -- Zotero credentials
    api_key TEXT NOT NULL,  -- Zotero API key (from https://www.zotero.org/settings/keys)
    zotero_user_id TEXT NOT NULL,  -- Zotero user ID (number, not username)
    library_type TEXT NOT NULL DEFAULT 'user',  -- 'user' or 'group'
    
    -- Sync configuration
    selected_collection_key TEXT,  -- Specific collection to sync (optional, null = entire library)
    auto_sync_enabled BOOLEAN NOT NULL DEFAULT false,
    sync_pdfs BOOLEAN NOT NULL DEFAULT true,  -- Whether to download PDF attachments
    
    -- Sync metadata
    last_synced_at TIMESTAMPTZ,
    last_sync_version INTEGER,  -- Zotero library version number for incremental sync
    total_items_synced INTEGER NOT NULL DEFAULT 0,
    
    -- Connection metadata
    connected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    connected_by UUID REFERENCES auth.users(id),
    
    -- Error tracking
    last_sync_error TEXT,
    
    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- One Zotero connection per RAG project
    CONSTRAINT unique_rag_project_zotero UNIQUE (rag_project_id),
    
    -- Valid library types
    CONSTRAINT valid_library_type CHECK (library_type IN ('user', 'group'))
);

-- Index for faster lookups
CREATE INDEX IF NOT EXISTS idx_zotero_connections_rag_project 
    ON zotero_connections(rag_project_id);

-- RLS Policies
ALTER TABLE zotero_connections ENABLE ROW LEVEL SECURITY;

-- Policy: Users can view connections for projects they own
CREATE POLICY "Users can view own project zotero connections"
    ON zotero_connections
    FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM rag_projects 
            WHERE rag_projects.id = zotero_connections.rag_project_id 
            AND rag_projects.user_id = auth.uid()
        )
    );

-- Policy: Users can insert connections for projects they own
CREATE POLICY "Users can insert zotero connections for own projects"
    ON zotero_connections
    FOR INSERT
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM rag_projects 
            WHERE rag_projects.id = zotero_connections.rag_project_id 
            AND rag_projects.user_id = auth.uid()
        )
    );

-- Policy: Users can update connections for projects they own
CREATE POLICY "Users can update own project zotero connections"
    ON zotero_connections
    FOR UPDATE
    USING (
        EXISTS (
            SELECT 1 FROM rag_projects 
            WHERE rag_projects.id = zotero_connections.rag_project_id 
            AND rag_projects.user_id = auth.uid()
        )
    );

-- Policy: Users can delete connections for projects they own
CREATE POLICY "Users can delete own project zotero connections"
    ON zotero_connections
    FOR DELETE
    USING (
        EXISTS (
            SELECT 1 FROM rag_projects 
            WHERE rag_projects.id = zotero_connections.rag_project_id 
            AND rag_projects.user_id = auth.uid()
        )
    );

-- Updated_at trigger
CREATE OR REPLACE FUNCTION update_zotero_connections_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER zotero_connections_updated_at
    BEFORE UPDATE ON zotero_connections
    FOR EACH ROW
    EXECUTE FUNCTION update_zotero_connections_updated_at();

-- Comment
COMMENT ON TABLE zotero_connections IS 'Stores Zotero API credentials and sync configuration per RAG project';
