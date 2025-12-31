/**
 * Admin API Client
 * 
 * Handles all admin-related API calls for document management,
 * processing jobs, and system status.
 */

import type {
  AdminStatusResponse,
  DocumentMetadataDetail,
  DocumentsResponse,
  MetadataReviewResponse,
  MetadataUpdateRequest,
  MetadataUpdateResponse,
  PDFUrlResponse,
  ProcessingJobsResponse,
  R2ListResponse,
  TriggerProcessingRequest,
  TriggerProcessingResponse,
  UploadResponse,
} from "./types";

// Re-export all types
export * from "./types";

// =============================================================================
// Configuration
// =============================================================================

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
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
// Document Upload & Processing
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

// =============================================================================
// Document Management
// =============================================================================

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

// =============================================================================
// Storage & Status
// =============================================================================

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
  const response = await fetchWithTimeout(`${API_BASE_URL}/admin/status`, {}, 15000);

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
  const response = await fetchWithTimeout(`${API_BASE_URL}/admin/collection`, {}, 15000);

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
  const response = await fetchWithTimeout(`${API_BASE_URL}/health`, {}, 8000);

  if (!response.ok) {
    throw new Error(`Health check failed: ${response.statusText}`);
  }

  return response.json();
}

// =============================================================================
// Metadata Review
// =============================================================================

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
    throw new Error(`Failed to update metadata: ${response.statusText}`);
  }

  return response.json();
}

// =============================================================================
// PDF Viewer
// =============================================================================

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
