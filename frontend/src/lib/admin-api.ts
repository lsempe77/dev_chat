/**
 * Admin API Client
 * 
 * Handles all admin-related API calls for document management,
 * processing jobs, and system status.
 */

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// Timeout for admin API calls (shorter than query timeout)
const ADMIN_TIMEOUT_MS = 60_000; // 60 seconds

/**
 * Fetch with timeout for admin endpoints
 */
async function fetchWithTimeout(
  url: string,
  options: RequestInit = {},
  timeoutMs: number = ADMIN_TIMEOUT_MS
): Promise<Response> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(url, {
      ...options,
      signal: controller.signal,
    });
    clearTimeout(timeoutId);
    return response;
  } catch (error) {
    clearTimeout(timeoutId);
    if (error instanceof Error && error.name === "AbortError") {
      throw new Error(`Request timed out after ${timeoutMs / 1000} seconds`);
    }
    throw error;
  }
}

// =============================================================================
// Types
// =============================================================================

export interface UploadResponse {
  success: boolean;
  filename: string;
  r2_key: string;
  size_bytes: number;
  queued_for_processing: boolean;
  is_duplicate?: boolean;
  existing_doc_id?: string;
  content_hash?: string;
  message?: string;
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
// API Functions
// =============================================================================

/**
 * Upload a document to R2 for processing
 */
export async function uploadDocument(file: File): Promise<UploadResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(`${API_BASE_URL}/admin/upload`, {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(error.detail || `Upload failed: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Get list of processing jobs
 */
export async function getProcessingJobs(): Promise<ProcessingJobsResponse> {
  const response = await fetch(`${API_BASE_URL}/admin/jobs`);

  if (!response.ok) {
    throw new Error(`Failed to fetch jobs: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Trigger batch processing of pending PDFs
 */
export async function triggerProcessing(
  options: TriggerProcessingRequest = {}
): Promise<TriggerProcessingResponse> {
  const response = await fetch(`${API_BASE_URL}/admin/jobs/trigger`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(options),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(error.detail || `Trigger failed: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Clear stale processing locks from R2
 * Locks can become stale if Modal times out or crashes
 */
export async function clearProcessingLocks(): Promise<{
  success: boolean;
  cleared: number;
  message: string;
}> {
  const response = await fetch(`${API_BASE_URL}/admin/jobs/clear-locks`, {
    method: "POST",
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(error.detail || `Clear locks failed: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Get list of indexed documents
 */
export async function getDocuments(options?: {
  search?: string;
  status?: string;
  limit?: number;
  offset?: number;
}): Promise<DocumentsResponse> {
  const params = new URLSearchParams();
  if (options?.search) params.append("search", options.search);
  if (options?.status) params.append("status", options.status);
  if (options?.limit) params.append("limit", String(options.limit));
  if (options?.offset) params.append("offset", String(options.offset));

  const url = `${API_BASE_URL}/admin/documents${params.toString() ? `?${params}` : ""}`;
  const response = await fetch(url);

  if (!response.ok) {
    throw new Error(`Failed to fetch documents: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Delete a document from the knowledge base
 */
export async function deleteDocument(documentId: string): Promise<{ success: boolean; deleted: string }> {
  const response = await fetch(`${API_BASE_URL}/admin/documents/${documentId}`, {
    method: "DELETE",
  });

  if (!response.ok) {
    throw new Error(`Failed to delete document: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Reprocess a document
 */
export async function reprocessDocument(documentId: string): Promise<{
  success: boolean;
  document_id: string;
  job_id: string;
  message: string;
}> {
  const response = await fetch(`${API_BASE_URL}/admin/documents/${documentId}/reprocess`, {
    method: "POST",
  });

  if (!response.ok) {
    throw new Error(`Failed to reprocess document: ${response.statusText}`);
  }

  return response.json();
}

/**
 * List files in R2 bucket
 */
export async function listR2Files(prefix: string = "input-pdfs/"): Promise<R2ListResponse> {
  const response = await fetch(`${API_BASE_URL}/admin/r2/list?prefix=${encodeURIComponent(prefix)}`);

  if (!response.ok) {
    throw new Error(`Failed to list R2 files: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Get admin status (connections, storage, workers)
 */
export async function getAdminStatus(): Promise<AdminStatusResponse> {
  const response = await fetchWithTimeout(`${API_BASE_URL}/admin/status`, {}, 15000); // 15s timeout

  if (!response.ok) {
    throw new Error(`Failed to fetch admin status: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Backend settings response structure
 */
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

/**
 * Get backend settings (read-only)
 */
export async function getBackendSettings(): Promise<BackendSettings> {
  const response = await fetchWithTimeout(`${API_BASE_URL}/admin/settings`, {}, 10000);

  if (!response.ok) {
    throw new Error(`Failed to fetch settings: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Get collection info from Qdrant
 */
export async function getCollectionInfo(): Promise<{
  name: string;
  points_count: number;
  vectors_count: number;
  status: string;
}> {
  const response = await fetchWithTimeout(`${API_BASE_URL}/admin/collection`, {}, 15000); // 15s timeout

  if (!response.ok) {
    throw new Error(`Failed to fetch collection info: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Health check
 */
export async function checkHealth(): Promise<{
  status: string;
  version: string;
  timestamp: string;
  components: Record<string, boolean>;
}> {
  const response = await fetchWithTimeout(`${API_BASE_URL}/health`, {}, 8000); // 8s timeout for health (backend has 2s Qdrant timeout)

  if (!response.ok) {
    throw new Error(`Health check failed: ${response.statusText}`);
  }

  return response.json();
}

// =============================================================================
// Metadata Review Types & Functions
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
  item_type?: string;  // journalArticle, book, bookSection, report, thesis, conferencePaper, etc.
  
  // Identifiers
  doi?: string;
  isbn?: string;
  issn?: string;
  url?: string;
  
  // Publication info (journal articles, magazines)
  publication?: string;  // Journal/Magazine name
  journal?: string;  // Alias for backward compatibility
  volume?: string;
  issue?: string;
  pages?: string;
  edition?: string;
  
  // Publisher info
  publisher?: string;
  place?: string;  // Publication place
  
  // Series info
  series?: string;
  series_number?: string;
  
  // Book-specific
  book_title?: string;  // For book sections
  num_pages?: number;  // Total pages
  
  // Report/Thesis specific
  institution?: string;  // Report institution or thesis university
  report_number?: string;
  report_type?: string;  // "Technical Report", "Working Paper"
  thesis_type?: string;  // "PhD Dissertation", "Master's Thesis"
  
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
  study_type?: string;  // RCT, Quasi-experimental, etc.
  intervention_type?: string;
  sdgs: string[];
  keywords: string[];
  
  // Processing metadata
  metadata_source: string;
  metadata_confidence: number;
  needs_review: boolean;
  chunk_count: number;
  page_count?: number;
  
  // Extra fields (JSON)
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
  num_pages?: number;
  
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

/**
 * Get documents needing metadata review
 */
export async function getMetadataForReview(params?: {
  filter?: "all" | "needs_review" | "low_confidence";
  limit?: number;
  offset?: number;
}): Promise<MetadataReviewResponse> {
  const searchParams = new URLSearchParams();
  if (params?.filter) searchParams.set("filter_type", params.filter);
  if (params?.limit) searchParams.set("limit", params.limit.toString());
  if (params?.offset) searchParams.set("offset", params.offset.toString());

  const response = await fetch(
    `${API_BASE_URL}/admin/metadata/review?${searchParams.toString()}`
  );

  if (!response.ok) {
    throw new Error(`Failed to fetch metadata: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Get detailed metadata for a specific document
 */
export async function getDocumentMetadata(
  documentId: string
): Promise<DocumentMetadataDetail> {
  const response = await fetch(
    `${API_BASE_URL}/admin/metadata/${encodeURIComponent(documentId)}`
  );

  if (!response.ok) {
    throw new Error(`Failed to fetch document metadata: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Update document metadata
 */
export async function updateDocumentMetadata(
  documentId: string,
  update: MetadataUpdateRequest
): Promise<MetadataUpdateResponse> {
  console.log("Updating metadata for:", documentId, update);
  
  const response = await fetch(
    `${API_BASE_URL}/admin/metadata/${encodeURIComponent(documentId)}`,
    {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(update),
    }
  );

  if (!response.ok) {
    const errorText = await response.text();
    console.error("Metadata update failed:", response.status, errorText);
    throw new Error(`Failed to update metadata: ${response.statusText} - ${errorText}`);
  }

  const result = await response.json();
  console.log("Metadata update result:", result);
  return result;
}

// =============================================================================
// PDF Viewer
// =============================================================================

export interface PDFUrlResponse {
  document_id: string;
  url: string;
  expires_in: number;
  r2_key: string;
}

/**
 * Get a presigned URL to view a PDF document
 */
export async function getPDFUrl(documentId: string): Promise<PDFUrlResponse> {
  const response = await fetch(
    `${API_BASE_URL}/admin/pdf/${encodeURIComponent(documentId)}`
  );

  if (!response.ok) {
    throw new Error(`Failed to get PDF URL: ${response.statusText}`);
  }

  return response.json();
}

// =============================================================================
// Bibliography Import/Export
// =============================================================================

export type ExportFormat = "bibtex" | "ris";

/**
 * Export documents as BibTeX or RIS format
 * @param format - "bibtex" or "ris"
 * @param docIds - Optional list of document IDs to export (all if omitted)
 */
export async function exportBibliography(
  format: ExportFormat = "bibtex",
  docIds?: string[]
): Promise<Blob> {
  const params = new URLSearchParams({ format });
  if (docIds && docIds.length > 0) {
    params.set("doc_ids", docIds.join(","));
  }

  const response = await fetch(
    `${API_BASE_URL}/admin/bibliography/export?${params}`
  );

  if (!response.ok) {
    throw new Error(`Export failed: ${response.statusText}`);
  }

  return response.blob();
}

/**
 * Download exported bibliography as file
 */
export async function downloadBibliography(
  format: ExportFormat = "bibtex",
  docIds?: string[]
): Promise<void> {
  const blob = await exportBibliography(format, docIds);
  
  // Get filename from format
  const extension = format === "bibtex" ? "bib" : "ris";
  const filename = `devchat_export_${new Date().toISOString().split("T")[0]}.${extension}`;
  
  // Create download link
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

/**
 * Parsed bibliography entry from import preview
 */
export interface ImportedEntry {
  title: string;
  authors: string[];
  year?: number;
  doi?: string;
  abstract?: string;
  item_type?: string;
  journal?: string;
  volume?: string;
  issue?: string;
  pages?: string;
  publisher?: string;
  url?: string;
  keywords: string[];
}

/**
 * Response from import preview
 */
export interface ImportPreviewResponse {
  parsed_count: number;
  entries: ImportedEntry[];
  errors: string[];
  duplicates: string[];  // Titles that already exist in the database
}

/**
 * Preview a bibliography file before importing
 */
export async function previewBibliographyImport(
  file: File
): Promise<ImportPreviewResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(
    `${API_BASE_URL}/admin/bibliography/import/preview`,
    {
      method: "POST",
      body: formData,
    }
  );

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(error.detail || `Preview failed: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Response from confirmed import
 */
export interface ImportConfirmResponse {
  imported_count: number;
  skipped_count: number;
  updated_count: number;
  enriched_count: number;
  errors: string[];
}

/**
 * Options for bibliography import
 */
export interface ImportOptions {
  skipDuplicates?: boolean;
  mergeDuplicates?: boolean;
  enrichFromDoi?: boolean;
}

/**
 * Confirm and execute import of bibliography entries
 */
export async function confirmBibliographyImport(
  entries: ImportedEntry[],
  options: ImportOptions = {}
): Promise<ImportConfirmResponse> {
  const {
    skipDuplicates = true,
    mergeDuplicates = false,
    enrichFromDoi = true,
  } = options;

  const response = await fetch(
    `${API_BASE_URL}/admin/bibliography/import/confirm`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        entries,
        skip_duplicates: skipDuplicates,
        merge_duplicates: mergeDuplicates,
        enrich_from_doi: enrichFromDoi,
      }),
    }
  );

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(error.detail || `Import failed: ${response.statusText}`);
  }

  return response.json();
}
