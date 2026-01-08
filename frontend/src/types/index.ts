// Types for the Research Workbench

// Study design classification types
export type StudyDesignCategory = 
  | "experimental" 
  | "quasi-experimental" 
  | "observational" 
  | "qualitative" 
  | "synthesis" 
  | "other";

export type StudyDesign =
  // Experimental
  | "rct"
  | "cluster_rct"
  | "stepped_wedge"
  // Quasi-experimental
  | "regression_discontinuity"
  | "difference_in_differences"
  | "synthetic_control"
  | "instrumental_variable"
  | "propensity_score"
  | "propensity_score_matching"
  | "interrupted_time_series"
  | "matching"
  | "natural_experiment"
  // Observational
  | "cohort"
  | "case_control"
  | "cross_sectional"
  | "panel"
  | "descriptive"
  // Qualitative
  | "qualitative"
  | "mixed_methods"
  | "case_study"
  | "ethnography"
  // Synthesis
  | "systematic_review"
  | "meta_analysis"
  // Other
  | "modeling"
  | "theory"
  | "unknown";

export interface Study {
  id: string;
  title: string;
  authors: string;
  year: number;
  country: string;
  sector: string;
  studyType: string;
  studyDesign?: StudyDesign;  // LLM-classified study design
  studyDesignConfidence?: number;  // 0.0-1.0
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
