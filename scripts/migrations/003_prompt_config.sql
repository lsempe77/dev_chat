-- Migration: Add prompt configuration to rag_projects
-- Date: 2026-01-05
-- Feature: Context Prompts & Prompt Customization

-- Add context_prompt column (simple domain instructions)
ALTER TABLE rag_projects 
ADD COLUMN IF NOT EXISTS context_prompt TEXT DEFAULT NULL;

-- Add custom_prompts column (JSONB for extraction/synthesis prompt overrides)
-- Schema: {
--   "extraction": "custom extraction prompt...",
--   "synthesis": "custom synthesis prompt...",
--   "modified_at": "2026-01-05T12:00:00Z",
--   "modified_by": "user_id"
-- }
ALTER TABLE rag_projects 
ADD COLUMN IF NOT EXISTS custom_prompts JSONB DEFAULT NULL;

-- Add comment for documentation
COMMENT ON COLUMN rag_projects.context_prompt IS 'Domain-specific instructions prepended to all synthesis prompts (e.g., "You are a health economics expert")';
COMMENT ON COLUMN rag_projects.custom_prompts IS 'Advanced: Custom extraction/synthesis prompts. Use with caution - may break citation quality.';

-- Example usage:
-- UPDATE rag_projects 
-- SET context_prompt = 'You are a health economics expert. Focus on cost-effectiveness and QALY analyses.'
-- WHERE id = 'project-uuid';

-- UPDATE rag_projects 
-- SET custom_prompts = '{
--   "extraction": "Extract claims focusing on economic outcomes...",
--   "synthesis": "Write in policy brief style...",
--   "modified_at": "2026-01-05T12:00:00Z"
-- }'::jsonb
-- WHERE id = 'project-uuid';
