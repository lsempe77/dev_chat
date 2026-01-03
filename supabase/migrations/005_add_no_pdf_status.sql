-- Migration: Add 'no_pdf' status to documents table
-- This allows Zotero items without PDF attachments to be stored as metadata-only records

-- Drop and recreate the status constraint to add 'no_pdf'
ALTER TABLE documents DROP CONSTRAINT IF EXISTS documents_status_check;
ALTER TABLE documents ADD CONSTRAINT documents_status_check 
    CHECK (status IN ('pending', 'processing', 'completed', 'failed', 'no_pdf'));

-- Add comment for clarity
COMMENT ON COLUMN documents.status IS 'Document processing status: pending, processing, completed, failed, or no_pdf (for Zotero items without PDF attachments)';
