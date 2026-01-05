-- Migration: 002_evaluation_runs
-- Description: Create table to store evaluation run history for quality monitoring
-- Created: 2026-01-05

-- Create evaluation_runs table to track quality metrics over time
CREATE TABLE IF NOT EXISTS public.evaluation_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Run metadata
    run_type TEXT NOT NULL DEFAULT 'manual',  -- 'manual', 'scheduled', 'deploy'
    evaluator TEXT NOT NULL DEFAULT 'minicheck',  -- 'minicheck', 'reliable', 'ragas'
    collection_name TEXT,  -- Optional: specific RAG collection tested
    
    -- Aggregate metrics (0-1 scale)
    faithfulness FLOAT,
    citation_recall FLOAT,
    citation_precision FLOAT,
    overall_score FLOAT,
    
    -- Additional metrics
    num_queries INTEGER DEFAULT 0,
    num_successful INTEGER DEFAULT 0,
    avg_latency_ms FLOAT,
    
    -- Detailed results (JSONB for flexibility)
    details JSONB,  -- Per-query breakdown
    
    -- Timestamps
    started_at TIMESTAMPTZ DEFAULT now(),
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now(),
    
    -- Who triggered it
    triggered_by TEXT  -- 'admin', 'ci', 'schedule'
);

-- Index for time-series queries
CREATE INDEX IF NOT EXISTS idx_evaluation_runs_created_at 
    ON public.evaluation_runs(created_at DESC);

-- Index for filtering by evaluator type
CREATE INDEX IF NOT EXISTS idx_evaluation_runs_evaluator 
    ON public.evaluation_runs(evaluator);

-- Create recent_queries table to log production query quality
CREATE TABLE IF NOT EXISTS public.query_quality_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Query info
    query_id UUID,  -- Links to chat history if available
    rag_project_id UUID REFERENCES public.rag_projects(id) ON DELETE SET NULL,
    user_id UUID,
    
    -- The actual content
    query TEXT NOT NULL,
    answer_preview TEXT,  -- First 500 chars
    num_sources INTEGER,
    num_citations INTEGER,
    
    -- Quality metrics (from sampling)
    faithfulness FLOAT,
    citation_recall FLOAT,
    citation_precision FLOAT,
    
    -- Sampling info
    was_sampled BOOLEAN DEFAULT false,  -- True if quality was evaluated
    sample_reason TEXT,  -- 'random', 'low_confidence', 'user_flagged'
    
    -- Performance
    latency_ms FLOAT,
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Index for recent queries view
CREATE INDEX IF NOT EXISTS idx_query_quality_logs_created_at 
    ON public.query_quality_logs(created_at DESC);

-- Index for sampled queries
CREATE INDEX IF NOT EXISTS idx_query_quality_logs_sampled 
    ON public.query_quality_logs(was_sampled) WHERE was_sampled = true;

-- RLS Policies (admin only)
ALTER TABLE public.evaluation_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.query_quality_logs ENABLE ROW LEVEL SECURITY;

-- Allow service role full access
CREATE POLICY "Service role has full access to evaluation_runs"
    ON public.evaluation_runs
    FOR ALL
    USING (auth.jwt() ->> 'role' = 'service_role')
    WITH CHECK (auth.jwt() ->> 'role' = 'service_role');

CREATE POLICY "Service role has full access to query_quality_logs"
    ON public.query_quality_logs
    FOR ALL
    USING (auth.jwt() ->> 'role' = 'service_role')
    WITH CHECK (auth.jwt() ->> 'role' = 'service_role');

-- View for quick metrics summary
CREATE OR REPLACE VIEW public.evaluation_metrics_summary AS
SELECT 
    evaluator,
    COUNT(*) as total_runs,
    ROUND(AVG(faithfulness)::numeric, 3) as avg_faithfulness,
    ROUND(AVG(citation_recall)::numeric, 3) as avg_citation_recall,
    ROUND(AVG(citation_precision)::numeric, 3) as avg_citation_precision,
    ROUND(AVG(overall_score)::numeric, 3) as avg_overall,
    MAX(created_at) as last_run
FROM public.evaluation_runs
WHERE completed_at IS NOT NULL
GROUP BY evaluator;

-- View for recent quality trend (last 30 days)
CREATE OR REPLACE VIEW public.evaluation_trend AS
SELECT 
    DATE(created_at) as run_date,
    evaluator,
    ROUND(AVG(faithfulness)::numeric, 3) as faithfulness,
    ROUND(AVG(citation_recall)::numeric, 3) as citation_recall,
    ROUND(AVG(citation_precision)::numeric, 3) as citation_precision,
    ROUND(AVG(overall_score)::numeric, 3) as overall_score
FROM public.evaluation_runs
WHERE created_at >= NOW() - INTERVAL '30 days'
    AND completed_at IS NOT NULL
GROUP BY DATE(created_at), evaluator
ORDER BY run_date DESC;

COMMENT ON TABLE public.evaluation_runs IS 'Stores results from evaluation suite runs for quality monitoring';
COMMENT ON TABLE public.query_quality_logs IS 'Logs quality metrics for sampled production queries';
