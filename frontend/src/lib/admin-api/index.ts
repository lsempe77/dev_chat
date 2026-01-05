/**
 * Admin API Client
 * 
 * Handles all admin-related API calls for document management,
 * processing jobs, and system status.
 * 
 * Authentication:
 * - Browser users: Login with password → receive session token
 * - Session token stored in localStorage and sent as X-Admin-Session header
 * - Optional: X-Admin-API-Key for programmatic access
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
const ADMIN_API_KEY = process.env.NEXT_PUBLIC_ADMIN_API_KEY || "";
const ADMIN_TIMEOUT_MS = 120_000; // 120 seconds (metadata enrichment can be slow)

// Storage key for session token
const SESSION_TOKEN_KEY = "devchat_admin_session";

// =============================================================================
// Session Management
// =============================================================================

/**
 * Get stored session token from localStorage
 */
export function getSessionToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(SESSION_TOKEN_KEY);
}

/**
 * Store session token in localStorage
 */
export function setSessionToken(token: string): void {
  if (typeof window !== "undefined") {
    localStorage.setItem(SESSION_TOKEN_KEY, token);
  }
}

/**
 * Clear session token from localStorage
 */
export function clearSessionToken(): void {
  if (typeof window !== "undefined") {
    localStorage.removeItem(SESSION_TOKEN_KEY);
  }
}

/**
 * Get default headers for admin API calls (includes auth)
 */
function getAdminHeaders(additionalHeaders: Record<string, string> = {}): HeadersInit {
  const headers: Record<string, string> = {
    ...additionalHeaders,
  };
  
  // Prefer session token (browser login)
  const sessionToken = getSessionToken();
  if (sessionToken) {
    headers["X-Admin-Session"] = sessionToken;
  }
  
  // Also include API key if configured (programmatic access)
  if (ADMIN_API_KEY) {
    headers["X-Admin-API-Key"] = ADMIN_API_KEY;
  }
  
  return headers;
}

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
      headers: {
        ...getAdminHeaders(),
        ...options.headers,
      },
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

/**
 * Admin fetch wrapper that includes auth headers
 */
async function adminFetch(url: string, options: RequestInit = {}): Promise<Response> {
  const response = await fetch(url, {
    ...options,
    headers: {
      ...getAdminHeaders(),
      ...options.headers,
    },
  });
  
  if (response.status === 401) {
    // Clear invalid session
    clearSessionToken();
    throw new Error("Authentication required. Please log in.");
  }
  
  return response;
}

// =============================================================================
// Authentication
// =============================================================================

export interface LoginResponse {
  success: boolean;
  token: string;
  expires_in: number;
  message: string;
}

export interface AuthStatusResponse {
  authenticated: boolean;
  auth_required: boolean;
  message: string;
}

/**
 * Login with admin password
 */
export async function adminLogin(password: string): Promise<LoginResponse> {
  const response = await fetch(`${API_BASE_URL}/admin/login`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ password }),
  });
  
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Login failed" }));
    throw new Error(error.detail || "Login failed");
  }
  
  const data = await response.json();
  
  // Store session token
  if (data.success && data.token) {
    setSessionToken(data.token);
  }
  
  return data;
}

/**
 * Logout and clear session
 */
export async function adminLogout(): Promise<void> {
  const sessionToken = getSessionToken();
  
  if (sessionToken) {
    try {
      await fetch(`${API_BASE_URL}/admin/logout`, {
        method: "POST",
        headers: {
          "X-Admin-Session": sessionToken,
        },
      });
    } catch {
      // Ignore errors, just clear local session
    }
  }
  
  clearSessionToken();
}

/**
 * Check if user is authenticated
 */
export async function checkAuthStatus(): Promise<AuthStatusResponse> {
  const sessionToken = getSessionToken();
  
  const response = await fetch(`${API_BASE_URL}/admin/auth-status`, {
    headers: sessionToken ? { "X-Admin-Session": sessionToken } : {},
  });
  
  if (!response.ok) {
    return {
      authenticated: false,
      auth_required: true,
      message: "Unable to check auth status",
    };
  }
  
  return response.json();
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

  const response = await adminFetch(`${API_BASE_URL}/admin/upload`, {
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
  const response = await adminFetch(`${API_BASE_URL}/admin/jobs`);

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
  const response = await adminFetch(`${API_BASE_URL}/admin/jobs/trigger`, {
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
  const response = await adminFetch(`${API_BASE_URL}/admin/jobs/clear-locks`, {
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
  const response = await adminFetch(url);

  if (!response.ok) {
    throw new Error(`Failed to fetch documents: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Delete a document from the knowledge base
 */
export async function deleteDocument(documentId: string): Promise<{ success: boolean; deleted: string }> {
  const response = await adminFetch(`${API_BASE_URL}/admin/documents/${documentId}`, {
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
  const response = await adminFetch(`${API_BASE_URL}/admin/documents/${documentId}/reprocess`, {
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
  const response = await adminFetch(`${API_BASE_URL}/admin/r2/list?prefix=${encodeURIComponent(prefix)}`);

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

/**
 * Get backend settings (read-only)
 */
import type { BackendSettings } from "./types";
export type { BackendSettings };

export async function getBackendSettings(): Promise<BackendSettings> {
  const response = await adminFetch(`${API_BASE_URL}/admin/settings`);

  if (!response.ok) {
    throw new Error(`Failed to fetch backend settings: ${response.statusText}`);
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

  const response = await adminFetch(
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
  const response = await adminFetch(
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
  const response = await adminFetch(
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
  const response = await adminFetch(
    `${API_BASE_URL}/admin/pdf/${encodeURIComponent(documentId)}`
  );

  if (!response.ok) {
    throw new Error(`Failed to get PDF URL: ${response.statusText}`);
  }

  return response.json();
}

// =============================================================================
// Bibliography Import
// =============================================================================

import type { ImportPreviewResponse, ImportConfirmResponse, ImportedEntry, ExportFormat, ExportResponse } from "./types";
export type { ImportedEntry, ImportPreviewResponse, ImportConfirmResponse, ExportFormat, ExportResponse };

/**
 * Preview a bibliography file before importing
 */
export async function previewBibliographyImport(
  file: File
): Promise<ImportPreviewResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await adminFetch(
    `${API_BASE_URL}/admin/bibliography/import/preview`,
    {
      method: "POST",
      body: formData,
    }
  );

  if (!response.ok) {
    const error = await response.text();
    throw new Error(`Failed to preview bibliography: ${error}`);
  }

  return response.json();
}

/**
 * Confirm and import bibliography entries
 */
export async function confirmBibliographyImport(
  entries: ImportedEntry[],
  options: {
    skip_duplicates?: boolean;
    merge_duplicates?: boolean;
    enrich_from_doi?: boolean;
  } = {}
): Promise<ImportConfirmResponse> {
  const response = await adminFetch(
    `${API_BASE_URL}/admin/bibliography/import/confirm`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        entries,
        skip_duplicates: options.skip_duplicates ?? true,
        merge_duplicates: options.merge_duplicates ?? false,
        enrich_from_doi: options.enrich_from_doi ?? false,
      }),
    }
  );

  if (!response.ok) {
    const error = await response.text();
    throw new Error(`Failed to import bibliography: ${error}`);
  }

  return response.json();
}

// =============================================================================
// Bibliography Export
// =============================================================================

/**
 * Download bibliography in BibTeX or RIS format
 */
export async function downloadBibliography(
  format: ExportFormat = "bibtex",
  docIds?: string[]
): Promise<ExportResponse> {
  const params = new URLSearchParams();
  params.append("format", format);
  if (docIds && docIds.length > 0) {
    params.append("doc_ids", docIds.join(","));
  }

  const response = await adminFetch(
    `${API_BASE_URL}/admin/bibliography/export?${params.toString()}`,
    {
      method: "GET",
    }
  );

  if (!response.ok) {
    const error = await response.text();
    throw new Error(`Failed to export bibliography: ${error}`);
  }

  return response.json();
}

// =============================================================================
// Usage & Cost Tracking
// =============================================================================

import type {
  UsageSummaryResponse,
  CostProjection,
  PricingResponse,
  AdminOverviewStats,
} from "./types";

/**
 * Get usage summary for a date range
 */
export async function getUsageSummary(
  days: number = 30
): Promise<UsageSummaryResponse> {
  const response = await adminFetch(
    `${API_BASE_URL}/admin/usage/summary?days=${days}`
  );

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Failed to fetch usage" }));
    throw new Error(error.detail || "Failed to fetch usage summary");
  }

  return response.json();
}

/**
 * Get cost projection (daily avg → monthly/annual)
 */
export async function getCostProjection(
  days: number = 30
): Promise<CostProjection> {
  const response = await adminFetch(
    `${API_BASE_URL}/admin/usage/costs?days=${days}`
  );

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Failed to fetch costs" }));
    throw new Error(error.detail || "Failed to fetch cost projection");
  }

  return response.json();
}

/**
 * Get model pricing configuration
 */
export async function getModelPricing(): Promise<PricingResponse> {
  const response = await adminFetch(
    `${API_BASE_URL}/admin/usage/pricing`
  );

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Failed to fetch pricing" }));
    throw new Error(error.detail || "Failed to fetch pricing");
  }

  return response.json();
}

/**
 * Force flush buffered usage events
 */
export async function flushUsageBuffer(): Promise<{ success: boolean; message: string }> {
  const response = await adminFetch(
    `${API_BASE_URL}/admin/usage/flush`,
    { method: "POST" }
  );

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Failed to flush" }));
    throw new Error(error.detail || "Failed to flush usage buffer");
  }

  return response.json();
}

/**
 * Get admin overview stats (users, projects, documents, etc.)
 */
export async function getAdminOverview(): Promise<AdminOverviewStats> {
  const response = await adminFetch(
    `${API_BASE_URL}/admin/overview`
  );

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Failed to fetch overview" }));
    throw new Error(error.detail || "Failed to fetch admin overview");
  }

  return response.json();
}

// =============================================================================
// Quality Monitoring
// =============================================================================

export interface EvaluationMetrics {
  faithfulness: number;
  citation_recall: number;
  citation_precision: number;
  overall_score: number;
}

export interface EvaluationRun {
  id: string;
  run_type: string;
  evaluator: string;
  collection_name?: string;
  metrics: EvaluationMetrics;
  num_queries: number;
  num_successful: number;
  avg_latency_ms?: number;
  started_at: string;
  completed_at?: string;
  triggered_by?: string;
}

export interface LatestMetricsResponse {
  metrics: EvaluationMetrics | null;
  last_run: string | null;
  targets: Record<string, number>;
  status: string;
}

export interface EvaluationHistory {
  runs: EvaluationRun[];
  summary: Record<string, number | string | null>;
}

export interface RunEvaluationRequest {
  evaluator?: string;
  collection_name?: string;
  num_queries?: number;
}

export interface RunEvaluationResponse {
  run_id: string;
  status: string;
  message: string;
}

export interface QueryQualityLog {
  id: string;
  query: string;
  answer_preview?: string;
  rag_project_id?: string;
  num_sources: number;
  num_citations: number;
  faithfulness?: number;
  citation_recall?: number;
  citation_precision?: number;
  was_sampled: boolean;
  latency_ms?: number;
  created_at: string;
}

/**
 * Get latest quality metrics
 */
export async function getLatestMetrics(): Promise<LatestMetricsResponse> {
  const response = await adminFetch(
    `${API_BASE_URL}/admin/quality/metrics`
  );

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Failed to fetch metrics" }));
    throw new Error(error.detail || "Failed to fetch quality metrics");
  }

  return response.json();
}

/**
 * Start a new evaluation run
 */
export async function runEvaluation(request: RunEvaluationRequest = {}): Promise<RunEvaluationResponse> {
  const response = await adminFetch(
    `${API_BASE_URL}/admin/quality/run`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    }
  );

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Failed to start evaluation" }));
    throw new Error(error.detail || "Failed to start evaluation");
  }

  return response.json();
}

/**
 * Get evaluation run history
 */
export async function getEvaluationHistory(limit: number = 10, evaluator?: string): Promise<EvaluationHistory> {
  const params = new URLSearchParams({ limit: limit.toString() });
  if (evaluator) params.append("evaluator", evaluator);

  const response = await adminFetch(
    `${API_BASE_URL}/admin/quality/history?${params}`
  );

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Failed to fetch history" }));
    throw new Error(error.detail || "Failed to fetch evaluation history");
  }

  return response.json();
}

/**
 * Get details of a specific evaluation run
 */
export async function getEvaluationRun(runId: string): Promise<EvaluationRun & { details?: Record<string, unknown> }> {
  const response = await adminFetch(
    `${API_BASE_URL}/admin/quality/run/${runId}`
  );

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Failed to fetch run" }));
    throw new Error(error.detail || "Failed to fetch evaluation run");
  }

  return response.json();
}

/**
 * Get recent queries with quality logs
 */
export async function getRecentQueries(limit: number = 20, sampledOnly: boolean = false): Promise<{ queries: QueryQualityLog[]; total: number }> {
  const params = new URLSearchParams({ 
    limit: limit.toString(),
    sampled_only: sampledOnly.toString()
  });

  const response = await adminFetch(
    `${API_BASE_URL}/admin/quality/recent-queries?${params}`
  );

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Failed to fetch queries" }));
    throw new Error(error.detail || "Failed to fetch recent queries");
  }

  return response.json();
}
