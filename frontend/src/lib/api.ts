import { QueryResponse, Filter, Study } from "@/types";
import type { SearchSettings } from "@/components/workbench/SettingsDrawer";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// Production timeout settings (in milliseconds)
const QUERY_TIMEOUT_MS = 120_000; // 2 minutes for complex queries
const DEFAULT_TIMEOUT_MS = 30_000; // 30 seconds for simple requests

/**
 * Create a fetch request with timeout and abort controller
 */
async function fetchWithTimeout(
  url: string,
  options: RequestInit,
  timeoutMs: number = DEFAULT_TIMEOUT_MS
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
      throw new Error(
        `Request timed out after ${timeoutMs / 1000} seconds. ` +
        `The query may be too complex or the server is busy. ` +
        `Try simplifying your query or reducing the number of studies.`
      );
    }
    throw error;
  }
}

export async function queryEvidence(
  query: string,
  filters: Filter[] = [],
  settings?: SearchSettings
): Promise<QueryResponse> {
  console.log("[API] queryEvidence called with settings:", settings);
  
  const requestBody = {
    query,
    filters: filters.map((f) => ({
      type: f.type,
      value: f.value,
    })),
    settings: settings ? {
      relevanceThreshold: settings.relevanceThreshold,
      maxStudies: settings.maxStudies,
      answerStyle: settings.answerStyle,
      useReranking: settings.useReranking,
      minConfidence: settings.minConfidence,
      yearCutoff: settings.yearCutoff,
    } : undefined,
  };
  
  console.log("[API] Request body:", JSON.stringify(requestBody, null, 2));
  
  const response = await fetchWithTimeout(
    `${API_BASE_URL}/api/query`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(requestBody),
    },
    QUERY_TIMEOUT_MS // Use longer timeout for queries
  );

  if (!response.ok) {
    // Parse error details if available
    let errorMessage = `API error: ${response.statusText}`;
    try {
      const errorData = await response.json();
      if (errorData.detail) {
        errorMessage = errorData.detail;
      } else if (errorData.message) {
        errorMessage = errorData.message;
      }
    } catch {
      // Ignore JSON parse errors
    }
    throw new Error(errorMessage);
  }

  return response.json();
}

export async function compareStudies(studyIds: string[]): Promise<{
  comparison: Record<string, Record<string, string>>;
  conflicts: string[];
}> {
  const response = await fetch(`${API_BASE_URL}/api/compare`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ study_ids: studyIds }),
  });

  if (!response.ok) {
    throw new Error(`API error: ${response.statusText}`);
  }

  return response.json();
}

export async function getSuggestions(
  query: string,
  context: string
): Promise<string[]> {
  const response = await fetch(`${API_BASE_URL}/api/suggest`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ query, context }),
  });

  if (!response.ok) {
    throw new Error(`API error: ${response.statusText}`);
  }

  const data = await response.json();
  return data.suggestions;
}

export async function exportResults(
  query: string,
  answer: string,
  studies: Study[],
  format: "pdf" | "docx" | "markdown"
): Promise<Blob> {
  const response = await fetch(`${API_BASE_URL}/api/export`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      query,
      answer,
      studies,
      format,
    }),
  });

  if (!response.ok) {
    throw new Error(`API error: ${response.statusText}`);
  }

  return response.blob();
}

export async function getAvailableFilters(): Promise<{
  countries: string[];
  sectors: string[];
  studyTypes: string[];
  years: { min: number; max: number };
}> {
  const response = await fetch(`${API_BASE_URL}/api/filters`);

  if (!response.ok) {
    throw new Error(`API error: ${response.statusText}`);
  }

  return response.json();
}

// =============================================================================
// Chat History API
// =============================================================================

export interface ChatHistoryItem {
  id: string;
  query: string;
  studyCount: number;
  timestamp: string;
}

export async function getChatHistory(
  ragId: string,
  sessionId?: string
): Promise<ChatHistoryItem[]> {
  const params = sessionId ? `?session_id=${sessionId}` : "";
  const response = await fetch(`${API_BASE_URL}/api/chat-history/${ragId}${params}`);

  if (!response.ok) {
    console.error("Failed to fetch chat history");
    return [];
  }

  const data = await response.json();
  return data.history || [];
}

export async function addChatHistory(
  ragId: string,
  query: string,
  studyCount: number,
  sessionId?: string
): Promise<ChatHistoryItem | null> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/chat-history/${ragId}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, studyCount, sessionId }),
    });

    if (!response.ok) {
      console.error("Failed to add chat history");
      return null;
    }

    return response.json();
  } catch (error) {
    console.error("Failed to add chat history:", error);
    return null;
  }
}

export async function deleteChatHistoryItem(
  ragId: string,
  historyId: string
): Promise<boolean> {
  try {
    const response = await fetch(
      `${API_BASE_URL}/api/chat-history/${ragId}/${historyId}`,
      { method: "DELETE" }
    );
    return response.ok;
  } catch (error) {
    console.error("Failed to delete chat history:", error);
    return false;
  }
}

export async function clearChatHistory(
  ragId: string,
  sessionId?: string
): Promise<boolean> {
  try {
    const params = sessionId ? `?session_id=${sessionId}` : "";
    const response = await fetch(
      `${API_BASE_URL}/api/chat-history/${ragId}${params}`,
      { method: "DELETE" }
    );
    return response.ok;
  } catch (error) {
    console.error("Failed to clear chat history:", error);
    return false;
  }
}
