-- Chat History Table
-- Track user queries per RAG project for chat history sidebar

CREATE TABLE IF NOT EXISTS chat_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rag_project_id UUID NOT NULL REFERENCES rag_projects(id) ON DELETE CASCADE,
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,  -- NULL for anonymous public users
    session_id TEXT,  -- For anonymous users, track by session
    
    -- Query data
    query TEXT NOT NULL,
    study_count INTEGER DEFAULT 0,
    
    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for fast lookups
CREATE INDEX IF NOT EXISTS idx_chat_history_rag_project_id ON chat_history(rag_project_id);
CREATE INDEX IF NOT EXISTS idx_chat_history_user_id ON chat_history(user_id);
CREATE INDEX IF NOT EXISTS idx_chat_history_session_id ON chat_history(session_id);
CREATE INDEX IF NOT EXISTS idx_chat_history_created_at ON chat_history(created_at DESC);

-- RLS Policy
ALTER TABLE chat_history ENABLE ROW LEVEL SECURITY;

-- Users can view their own chat history
CREATE POLICY "Users can view own chat_history"
    ON chat_history FOR SELECT
    USING (
        auth.uid() = user_id 
        OR user_id IS NULL  -- Anonymous users can see their session-based history
    );

-- Users can insert their own chat history
CREATE POLICY "Users can insert own chat_history"
    ON chat_history FOR INSERT
    WITH CHECK (
        auth.uid() = user_id 
        OR (user_id IS NULL AND session_id IS NOT NULL)
    );

-- Users can delete their own chat history
CREATE POLICY "Users can delete own chat_history"
    ON chat_history FOR DELETE
    USING (
        auth.uid() = user_id 
        OR user_id IS NULL
    );

-- Service role bypass for API
CREATE POLICY "Service role has full access to chat_history"
    ON chat_history FOR ALL
    USING (auth.jwt() ->> 'role' = 'service_role');
