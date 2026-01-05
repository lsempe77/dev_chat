-- DevChat v2.0 - Usage Logs Table
-- Created: January 5, 2026
-- Purpose: Persistent tracking of API usage, tokens, and costs

-- Create usage_logs table
CREATE TABLE IF NOT EXISTS usage_logs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at timestamptz NOT NULL DEFAULT now(),
    
    -- User and project context (nullable for anonymous/system calls)
    user_id uuid REFERENCES auth.users(id) ON DELETE SET NULL,
    rag_project_id uuid REFERENCES rag_projects(id) ON DELETE SET NULL,
    
    -- Event classification
    event_type text NOT NULL, -- 'query', 'embed', 'rerank', 'llm', 'metadata_enrichment'
    
    -- Model and provider info
    provider text, -- 'openrouter', 'cohere', 'openai'
    model text, -- 'gpt-4o', 'gpt-4o-mini', 'embed-v4', 'rerank-v3.5'
    
    -- Token usage
    input_tokens int DEFAULT 0,
    output_tokens int DEFAULT 0,
    total_tokens int GENERATED ALWAYS AS (input_tokens + output_tokens) STORED,
    
    -- Cost tracking (in USD, 6 decimal precision)
    cost_usd numeric(10, 6) DEFAULT 0,
    
    -- Performance
    latency_ms int,
    
    -- Additional context
    metadata jsonb DEFAULT '{}',
    
    -- Query info (for 'query' events)
    query_text text,
    query_id text,
    session_id text
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_usage_logs_created_at ON usage_logs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_usage_logs_user_id ON usage_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_usage_logs_rag_project_id ON usage_logs(rag_project_id);
CREATE INDEX IF NOT EXISTS idx_usage_logs_event_type ON usage_logs(event_type);
CREATE INDEX IF NOT EXISTS idx_usage_logs_model ON usage_logs(model);

-- Composite index for daily aggregations
CREATE INDEX IF NOT EXISTS idx_usage_logs_daily ON usage_logs(date_trunc('day', created_at), event_type);

-- RLS Policies
ALTER TABLE usage_logs ENABLE ROW LEVEL SECURITY;

-- Admins (service role) can see all
CREATE POLICY "Service role has full access to usage_logs"
ON usage_logs
FOR ALL
TO service_role
USING (true)
WITH CHECK (true);

-- Users can only see their own usage (read-only)
CREATE POLICY "Users can view their own usage"
ON usage_logs
FOR SELECT
TO authenticated
USING (user_id = auth.uid());

-- Helpful views for admin dashboard

-- Daily summary view
CREATE OR REPLACE VIEW usage_daily_summary AS
SELECT 
    date_trunc('day', created_at)::date as day,
    event_type,
    model,
    COUNT(*) as count,
    SUM(input_tokens) as total_input_tokens,
    SUM(output_tokens) as total_output_tokens,
    SUM(cost_usd) as total_cost_usd,
    AVG(latency_ms) as avg_latency_ms,
    COUNT(DISTINCT user_id) as unique_users,
    COUNT(DISTINCT rag_project_id) as unique_projects
FROM usage_logs
GROUP BY date_trunc('day', created_at), event_type, model
ORDER BY day DESC, event_type, model;

-- User summary view
CREATE OR REPLACE VIEW usage_user_summary AS
SELECT 
    user_id,
    COUNT(*) as total_events,
    COUNT(DISTINCT rag_project_id) as projects_used,
    SUM(CASE WHEN event_type = 'query' THEN 1 ELSE 0 END) as query_count,
    SUM(input_tokens) as total_input_tokens,
    SUM(output_tokens) as total_output_tokens,
    SUM(cost_usd) as total_cost_usd,
    MIN(created_at) as first_activity,
    MAX(created_at) as last_activity
FROM usage_logs
GROUP BY user_id;

-- Grant access to views
GRANT SELECT ON usage_daily_summary TO authenticated;
GRANT SELECT ON usage_user_summary TO service_role;

COMMENT ON TABLE usage_logs IS 'Tracks all API usage including LLM calls, embeddings, reranking for cost and usage analytics';
