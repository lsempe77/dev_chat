/**
 * Admin API Client
 * 
 * Handles all admin-related API calls for document management,
 * processing jobs, and system status.
 */

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// =============================================================================
// Types
// =============================================================================

export interface UploadResponse {
  success: boolean;
  filename: string;
  r2_key: string;
  size_bytes: number;
  queued_for_processing: boolean;
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
  const response = await fetch(`${API_BASE_URL}/admin/status`);

  if (!response.ok) {
    throw new Error(`Failed to fetch admin status: ${response.statusText}`);
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
  const response = await fetch(`${API_BASE_URL}/admin/collection`);

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
  const response = await fetch(`${API_BASE_URL}/health`);

  if (!response.ok) {
    throw new Error(`Health check failed: ${response.statusText}`);
  }

  return response.json();
}
