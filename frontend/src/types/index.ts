// Types for the Research Workbench

export interface Study {
  id: string;
  title: string;
  authors: string;
  year: number;
  country: string;
  sector: string;
  studyType: string;
  confidence: "high" | "medium" | "low";
  snippet: string;
  score: number;
  pdfUrl?: string;
}

export interface Citation {
  id: number;
  studyId: string;
  text: string;
  study: Study;
  page?: number;  // Page number for PDF navigation
  highlightText?: string;  // Text to highlight in PDF viewer
}

export interface Filter {
  id: string;
  type: "country" | "sector" | "studyType" | "yearRange" | "confidence";
  value: string;
  label: string;
}

export interface QueryResponse {
  answer: string;
  citations: Citation[];
  studies: Study[];
  filters: Filter[];
  suggestions: string[];
  evidenceHealth: EvidenceHealth;
}

export interface EvidenceHealth {
  studyCount: number;
  dateRange: string;
  gaps: string[];
  coverageWarning?: string;
}

export interface CompareRow {
  field: string;
  [studyId: string]: string;
}

export type AnswerStyle = "executive" | "research" | "policy" | "citations";
