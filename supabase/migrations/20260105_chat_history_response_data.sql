-- Add response_data column to store full cached response
-- This includes citations, studies, suggestions, evidenceHealth as JSON

ALTER TABLE chat_history ADD COLUMN IF NOT EXISTS response_data JSONB;

-- Comment on column for documentation
COMMENT ON COLUMN chat_history.response_data IS 'Full cached response including citations, studies, suggestions, evidenceHealth as JSON';
