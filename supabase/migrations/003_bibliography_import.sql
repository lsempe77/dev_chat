-- Bibliography Import Columns Migration
-- Run this in Supabase SQL Editor

-- Add columns for tracking bibliography imports and matching
ALTER TABLE documents 
ADD COLUMN IF NOT EXISTS import_source TEXT,  -- 'upload', 'zotero', 'ris', 'bibtex', 'csv'
ADD COLUMN IF NOT EXISTS match_confidence FLOAT,  -- 0.0-1.0, how confident the auto-match was
ADD COLUMN IF NOT EXISTS external_id TEXT;  -- Zotero item key, DOI, cite key, etc.

-- Add index for external_id lookups (useful for Zotero sync)
CREATE INDEX IF NOT EXISTS idx_documents_external_id ON documents(external_id) WHERE external_id IS NOT NULL;

-- Add check constraint for match_confidence
ALTER TABLE documents 
ADD CONSTRAINT check_match_confidence 
CHECK (match_confidence IS NULL OR (match_confidence >= 0 AND match_confidence <= 1));

-- Comment on columns
COMMENT ON COLUMN documents.import_source IS 'Source of the document: upload, zotero, ris, bibtex, csv';
COMMENT ON COLUMN documents.match_confidence IS 'Auto-matching confidence score 0.0-1.0';
COMMENT ON COLUMN documents.external_id IS 'External identifier: Zotero key, DOI, cite key';
