import { QueryResponse, Filter, Study } from "@/types";
import type { SearchSettings } from "@/components/workbench/SettingsDrawer";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

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
  
  const response = await fetch(`${API_BASE_URL}/api/query`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(requestBody),
  });

  if (!response.ok) {
    throw new Error(`API error: ${response.statusText}`);
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
