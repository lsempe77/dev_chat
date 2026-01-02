/**
 * Per-RAG API Client
 * 
 * Handles API calls for per-RAG project operations including
 * document management and metadata with Zotero-compatible fields.
 * 
 * Uses Supabase authentication instead of admin tokens.
 */

import { createBrowserClient } from '@supabase/ssr'

// =============================================================================
// Configuration
// =============================================================================

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const TIMEOUT_MS = 60_000; // 60 seconds

// =============================================================================
// Types
// =============================================================================

export interface MetadataDetail {
  id: string;
  title: string;
  filename: string;
  authors: string[];
  year: number | null;
  abstract: string | null;
  
  // Zotero item type
  item_type: string | null;
  
  // Identifiers
  doi: string | null;
  isbn: string | null;
  issn: string | null;
  url: string | null;
  
  // Publication info
  publication: string | null;
  journal: string | null;
  volume: string | null;
  issue: string | null;
  pages: string | null;
  
  // Publisher info
  publisher: string | null;
  place: string | null;
  
  // Book-specific fields
  edition: string | null;
  series: string | null;
  series_number: string | null;
  book_title: string | null;
  num_pages: string | null;
  
  // Report/Working Paper fields
  institution: string | null;
  report_number: string | null;
  report_type: string | null;
  thesis_type: string | null;
  
  // Conference fields
  conference_name: string | null;
  proceedings_title: string | null;
  
  // Other
  accessed_date: string | null;
  
  // 3ie Classification
  countries: string[];
  sectors: string[];
  study_type: string | null;
  intervention_type: string | null;
  
  // Processing metadata
  metadata_source: string;
  metadata_confidence: number;
  needs_review: boolean;
  chunk_count: number;
  
  // Flags for issues
  needs_reprocessing: boolean;  // True if chunk_count=0 but status=completed
}

export interface MetadataListResponse {
  documents: MetadataDetail[];
  total_count: number;
  needs_review_count: number;
}

export interface MetadataUpdateRequest {
  title?: string;
  authors?: string[];
  year?: number;
  abstract?: string;
  item_type?: string;
  doi?: string;
  isbn?: string;
  issn?: string;
  url?: string;
  publication?: string;
  journal?: string;
  volume?: string;
  issue?: string;
  pages?: string;
  publisher?: string;
  place?: string;
  
  // Book-specific fields
  edition?: string;
  series?: string;
  series_number?: string;
  book_title?: string;
  num_pages?: string;
  
  // Report/Working Paper fields
  institution?: string;
  report_number?: string;
  report_type?: string;
  thesis_type?: string;
  
  // Conference fields
  conference_name?: string;
  proceedings_title?: string;
  
  // Other
  accessed_date?: string;
  
  // 3ie Classification
  countries?: string[];
  sectors?: string[];
  study_type?: string;
  intervention_type?: string;
  needs_review?: boolean;
}

// =============================================================================
// Helper Functions
// =============================================================================

function getSupabase() {
  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL!;
  const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!;
  return createBrowserClient(supabaseUrl, supabaseAnonKey);
}

async function fetchWithAuth(
  url: string,
  options: RequestInit = {},
  timeoutMs: number = TIMEOUT_MS
): Promise<Response> {
  const supabase = getSupabase();
  const { data: { session } } = await supabase.auth.getSession();
  
  if (!session) {
    throw new Error("Not authenticated");
  }
  
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
  
  try {
    const response = await fetch(url, {
      ...options,
      signal: controller.signal,
      headers: {
        ...options.headers,
        "Authorization": `Bearer ${session.access_token}`,
        "Content-Type": "application/json",
      },
    });
    clearTimeout(timeoutId);
    return response;
  } catch (error) {
    clearTimeout(timeoutId);
    if (error instanceof Error && error.name === "AbortError") {
      throw new Error(`Request timed out after ${timeoutMs / 1000} seconds.`);
    }
    throw error;
  }
}

// =============================================================================
// Per-RAG Metadata API
// =============================================================================

/**
 * Get all documents with metadata for a RAG project
 */
export async function getRagMetadata(
  ragId: string,
  params?: {
    filter?: "all" | "needs_review";
  }
): Promise<MetadataListResponse> {
  const searchParams = new URLSearchParams();
  if (params?.filter) searchParams.set("filter_type", params.filter);
  
  const response = await fetchWithAuth(
    `${API_BASE_URL}/rags/${ragId}/metadata?${searchParams.toString()}`
  );
  
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || `Failed to fetch metadata: ${response.statusText}`);
  }
  
  return response.json();
}

/**
 * Get metadata for a specific document
 */
export async function getRagDocumentMetadata(
  ragId: string,
  documentId: string
): Promise<MetadataDetail> {
  const response = await fetchWithAuth(
    `${API_BASE_URL}/rags/${ragId}/metadata/${encodeURIComponent(documentId)}`
  );
  
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || `Failed to fetch document: ${response.statusText}`);
  }
  
  return response.json();
}

/**
 * Update document metadata
 */
export async function updateRagDocumentMetadata(
  ragId: string,
  documentId: string,
  update: MetadataUpdateRequest
): Promise<MetadataDetail> {
  const response = await fetchWithAuth(
    `${API_BASE_URL}/rags/${ragId}/metadata/${encodeURIComponent(documentId)}`,
    {
      method: "PATCH",
      body: JSON.stringify(update),
    }
  );
  
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || `Failed to update metadata: ${response.statusText}`);
  }
  
  return response.json();
}

/**
 * Enrich document metadata from CrossRef using DOI
 */
export async function enrichRagDocumentMetadata(
  ragId: string,
  documentId: string
): Promise<MetadataDetail> {
  const response = await fetchWithAuth(
    `${API_BASE_URL}/rags/${ragId}/metadata/${encodeURIComponent(documentId)}/enrich`,
    {
      method: "POST",
    }
  );
  
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || `Failed to enrich metadata: ${response.statusText}`);
  }
  
  return response.json();
}

export interface EnrichAllResult {
  enriched: number;
  failed: number;
  skipped: number;
  total: number;
  details: Array<{ id: string; status: string; source?: string; reason?: string }>;
}

/**
 * Enrich metadata for all documents in a RAG project
 */
export async function enrichAllRagDocuments(ragId: string): Promise<EnrichAllResult> {
  const response = await fetchWithAuth(
    `${API_BASE_URL}/rags/${ragId}/metadata/enrich-all`,
    {
      method: "POST",
    }
  );
  
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || `Failed to enrich all: ${response.statusText}`);
  }
  
  return response.json();
}

/**
 * Get presigned URL for PDF viewing (using documents endpoint)
 */
export async function getRagPdfUrl(
  ragId: string,
  documentId: string
): Promise<{ url: string }> {
  const response = await fetchWithAuth(
    `${API_BASE_URL}/rags/${ragId}/documents/${encodeURIComponent(documentId)}/pdf`
  );
  
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || `Failed to get PDF URL: ${response.statusText}`);
  }
  
  return response.json();
}

/**
 * Delete a document from a RAG project
 */
export async function deleteRagDocument(
  ragId: string,
  documentId: string
): Promise<{ message: string; document_id: string; filename: string }> {
  const response = await fetchWithAuth(
    `${API_BASE_URL}/rags/${ragId}/documents/${encodeURIComponent(documentId)}`,
    {
      method: "DELETE",
    }
  );
  
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || `Failed to delete document: ${response.statusText}`);
  }
  
  return response.json();
}
