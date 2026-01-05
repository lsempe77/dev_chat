-- =============================================================================
-- Migration: Add Model Configuration to RAG Projects
-- =============================================================================
-- Allows RAG owners to choose their preferred LLM provider and model
-- 
-- Run this in Supabase SQL Editor

-- Add model_config JSONB column with sensible defaults
ALTER TABLE rag_projects 
ADD COLUMN IF NOT EXISTS model_config JSONB NOT NULL DEFAULT '{
  "provider": "openai",
  "model": "gpt-4o-mini",
  "temperature": 0.1,
  "reasoning_model": "gpt-4o"
}'::jsonb;

-- Add comment for documentation
COMMENT ON COLUMN rag_projects.model_config IS 'LLM configuration for this RAG project: {provider, model, temperature, reasoning_model}';

-- =============================================================================
-- Model Configuration Schema (for reference)
-- =============================================================================
-- {
--   "provider": "openai" | "anthropic" | "google" | "meta",
--   "model": string,          -- Fast model for simple tasks
--   "reasoning_model": string, -- Strong model for synthesis
--   "temperature": number      -- 0.0 to 1.0
-- }
--
-- Provider-Model Mappings (via OpenRouter):
-- -----------------------------------------
-- openai:
--   - gpt-4o-mini (fast, cheap)
--   - gpt-4o (reasoning)
--   - gpt-4-turbo
--
-- anthropic:
--   - claude-3-5-haiku-20241022 (fast)
--   - claude-sonnet-4-20250514 (reasoning)
--   - claude-3-5-sonnet-20241022
--
-- google:
--   - gemini-2.0-flash-exp (fast)
--   - gemini-exp-1206 (reasoning)
--
-- meta:
--   - meta-llama/llama-3.1-70b-instruct (fast)
--   - meta-llama/llama-3.1-405b-instruct (reasoning)

-- =============================================================================
-- Update existing projects to have defaults (if needed)
-- =============================================================================
UPDATE rag_projects 
SET model_config = '{
  "provider": "openai",
  "model": "gpt-4o-mini",
  "temperature": 0.1,
  "reasoning_model": "gpt-4o"
}'::jsonb
WHERE model_config IS NULL;

-- =============================================================================
-- Create index for querying by provider (optional, for analytics)
-- =============================================================================
CREATE INDEX IF NOT EXISTS idx_rag_projects_model_provider 
ON rag_projects ((model_config->>'provider'));

-- =============================================================================
-- Verify migration
-- =============================================================================
SELECT 
    id,
    name,
    model_config->>'provider' as provider,
    model_config->>'model' as model,
    model_config->>'reasoning_model' as reasoning_model
FROM rag_projects
LIMIT 5;
