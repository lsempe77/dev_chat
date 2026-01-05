-- Add answer column to chat_history table
-- This stores the AI-generated response for analysis and improvement

ALTER TABLE chat_history ADD COLUMN IF NOT EXISTS answer TEXT;
ALTER TABLE chat_history ADD COLUMN IF NOT EXISTS citations_used INTEGER;

-- Comment on columns for documentation
COMMENT ON COLUMN chat_history.answer IS 'The AI-generated answer to the user query';
COMMENT ON COLUMN chat_history.citations_used IS 'Number of citations/sources referenced in the answer';
