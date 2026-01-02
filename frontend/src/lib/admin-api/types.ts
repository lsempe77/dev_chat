/**
 * Admin API Types
 * 
 * TypeScript interfaces for admin API requests and responses.
 */

// =============================================================================
// Core Types
// =============================================================================

export interface UploadResponse {
  success: boolean;
  filename: string;
  r2_key: string;
  size_bytes: number;
  queued_for_processing: boolean;
  doc_id?: string;
  message?: string;
  is_duplicate?: boolean;
}

export interface ProcessingJob {
  id: string;
  filename: string;
  status: "queued" | "processing" | "completed" | "failed";
  progress: number;
  started_at?: string;
  completed_at?: string;
  error?: string;
  pages?: number;
  chunks?: number;
}

export interface ProcessingJobsResponse {
  jobs: ProcessingJob[];
  queued_count: number;
  processing_count: number;
  completed_count: number;
  failed_count: number;
}

export interface DocumentMetadata {
  id: string;
  title: string;
  filename: string;
  authors: string[];
  year?: number;
  status: "indexed" | "pending" | "error";
  page_count: number;
  chunk_count: number;
  uploaded_at: string;
  processed_at?: string;
}

export interface DocumentsResponse {
  documents: DocumentMetadata[];
  total_count: number;
  total_chunks: number;
  total_pages: number;
}

// =============================================================================
// R2 Storage Types
// =============================================================================

export interface R2File {
  key: string;
  size_bytes: number;
  last_modified: string;
}

export interface R2ListResponse {
  prefix: string;
  file_count: number;
  files: R2File[];
}

// =============================================================================
// Admin Status Types
// =============================================================================

export interface ServiceConnection {
  name: string;
  status: "connected" | "disconnected" | "error";
  details?: string;
  latency_ms?: number;
}

export interface StorageStatus {
  bucket: string;
  input_path: string;
  output_path: string;
  storage_used_bytes: number;
  file_count: number;
}

export interface AdminStatusResponse {
  storage: StorageStatus;
  connections: ServiceConnection[];
  pending_jobs: number;
  active_workers: number;
}

// =============================================================================
// Backend Settings Types
// =============================================================================

export interface BackendSettings {
  chunking: {
    chunk_size: number;
    chunk_overlap: number;
    parent_chunk_size: number;
    use_semantic_chunking: boolean;
  };
  retrieval: {
    hybrid_enabled: boolean;
    hybrid_alpha: number;
    retrieval_top_k: number;
    final_top_k: number;
    rerank_enabled: boolean;
    rerank_model: string;
    rerank_top_n: number;
  };
  embeddings: {
    provider: string;
    model: string;
    dimension: number;
  };
  llm: {
    provider: string;
    fast_model: string;
    reasoning_model: string;
    temperature: number;
    max_tokens: number;
  };
  processing: {
    qdrant_collection: string;
  };
}

export interface TriggerProcessingRequest {
  force_reprocess?: boolean;
  specific_files?: string[];
  max_documents?: number;
}

export interface TriggerProcessingResponse {
  queued: number;
  skipped: number;
  message: string;
}

// =============================================================================
// Bibliography Export Types
// =============================================================================

export type ExportFormat = "bibtex" | "ris";

export interface ExportResponse {
  format: string;
  count: number;
  data: string;
  filename: string;
}

// =============================================================================
// Metadata Review Types (Zotero-Compatible)
// =============================================================================

/**
 * Zotero-compatible document metadata structure
 */
export interface DocumentMetadataDetail {
  id: string;
  title: string;
  filename: string;
  authors: string[];
  year?: number;
  abstract?: string;
  
  // Zotero item type
  item_type?: string;
  
  // Identifiers
  doi?: string;
  isbn?: string;
  issn?: string;
  url?: string;
  
  // Publication info
  publication?: string;
  journal?: string;
  volume?: string;
  issue?: string;
  pages?: string;
  edition?: string;
  
  // Publisher info
  publisher?: string;
  place?: string;
  
  // Series info
  series?: string;
  series_number?: string;
  
  // Book-specific
  book_title?: string;
  num_pages?: string;
  
  // Report/Thesis specific
  institution?: string;
  report_number?: string;
  report_type?: string;
  thesis_type?: string;
  
  // Conference-specific
  conference_name?: string;
  proceedings_title?: string;
  
  // Access info
  accessed_date?: string;
  
  // Citation metrics
  cited_by_count?: number;
  is_open_access: boolean;
  
  // 3ie Classification
  countries: string[];
  sectors: string[];
  study_type?: string;
  intervention_type?: string;
  sdgs: string[];
  keywords: string[];
  
  // Processing metadata
  metadata_source: string;
  metadata_confidence: number;
  needs_review: boolean;
  chunk_count: number;
  page_count?: number;
  needs_reprocessing?: boolean;
  
  // Extra fields
  extra?: Record<string, unknown>;
}

export interface MetadataReviewResponse {
  documents: DocumentMetadataDetail[];
  total_count: number;
  needs_review_count: number;
  low_confidence_count: number;
}

/**
 * Zotero-compatible metadata update request
 */
export interface MetadataUpdateRequest {
  // Core
  title?: string;
  authors?: string[];
  year?: number;
  abstract?: string;
  
  // Item type
  item_type?: string;
  
  // Identifiers
  doi?: string;
  isbn?: string;
  issn?: string;
  url?: string;
  
  // Publication
  publication?: string;
  journal?: string;
  volume?: string;
  issue?: string;
  pages?: string;
  edition?: string;
  
  // Publisher
  publisher?: string;
  place?: string;
  
  // Series
  series?: string;
  series_number?: string;
  
  // Book
  book_title?: string;
  num_pages?: string;

  // Report/Thesis
  institution?: string;
  report_number?: string;
  report_type?: string;
  thesis_type?: string;
  
  // Conference
  conference_name?: string;
  proceedings_title?: string;
  
  // Access
  accessed_date?: string;
  
  // Classification
  countries?: string[];
  sectors?: string[];
  study_type?: string;
  intervention_type?: string;
  
  // Review status
  needs_review?: boolean;
  
  // Extra fields
  extra?: Record<string, unknown>;
}

export interface MetadataUpdateResponse {
  success: boolean;
  document_id: string;
  updated_chunks: number;
  message: string;
}

// =============================================================================
// PDF Viewer Types
// =============================================================================

export interface PDFUrlResponse {
  document_id: string;
  url: string;
  expires_in: number;
  r2_key: string;
}

// =============================================================================
// Bibliography Import Types
// =============================================================================

export interface ImportedEntry {
  index: number;
  title: string;
  authors: string[];
  year?: number;
  doi?: string;
  abstract?: string;
  journal?: string;
  entry_type?: string;
  matched_document_id?: string;
  match_confidence?: number;
  is_duplicate: boolean;
  extra?: Record<string, unknown>;
}

export interface ImportPreviewResponse {
  success: boolean;
  file_format: string;
  total_entries: number;
  valid_entries: number;
  entries: ImportedEntry[];
  errors: string[];
  duplicates: string[];  // Titles that already exist in the database
}

export interface ImportConfirmResponse {
  success: boolean;
  imported: number;
  skipped: number;
  updated: number;
  enriched: number;
  errors: string[];
}
