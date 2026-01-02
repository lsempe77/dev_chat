/**
 * Zotero-compatible constants for metadata management.
 * These follow Zotero's exact field names and item types for compatibility.
 * @see https://www.zotero.org/support/kb/item_types_and_fields
 */

// Zotero-compatible item types
export const ITEM_TYPES = [
  "journalArticle",
  "book",
  "bookSection",
  "report",
  "workingPaper",
  "thesis",
  "conferencePaper",
  "manuscript",
  "document",
  "webpage",
  "dataset",
  "preprint",
  "other",
] as const;

export type ItemType = typeof ITEM_TYPES[number];

// Thesis types (Zotero-compatible)
export const THESIS_TYPES = [
  "PhD Dissertation",
  "Master's Thesis",
  "Bachelor's Thesis",
  "Doctoral Thesis",
] as const;

// Report types (Zotero-compatible)
export const REPORT_TYPES = [
  "Technical Report",
  "Working Paper",
  "Policy Brief",
  "Research Report",
  "White Paper",
  "Annual Report",
] as const;

// 3ie Study types
export const STUDY_TYPES = [
  "RCT",
  "quasi-experimental",
  "systematic-review",
  "meta-analysis",
  "observational",
  "qualitative",
  "mixed-methods",
  "other",
] as const;

// 3ie Sectors
export const SECTORS = [
  "education",
  "health",
  "agriculture",
  "finance",
  "infrastructure",
  "governance",
  "social-protection",
  "water-sanitation",
  "energy",
  "environment",
  "other",
] as const;

/**
 * Defines which bibliographic fields to show for each item type.
 * Follows Zotero's field structure.
 */
export const FIELDS_BY_ITEM_TYPE: Record<string, string[]> = {
  journalArticle: ["journal", "publication", "volume", "issue", "pages", "doi", "issn", "abstract"],
  book: ["publisher", "place", "edition", "isbn", "series", "series_number", "num_pages", "abstract"],
  bookSection: ["book_title", "publisher", "place", "edition", "pages", "isbn", "series", "abstract"],
  report: ["institution", "report_number", "report_type", "place", "pages", "series", "abstract"],
  workingPaper: ["institution", "report_number", "place", "series", "abstract"],
  thesis: ["institution", "thesis_type", "place", "num_pages", "abstract"],
  conferencePaper: ["conference_name", "proceedings_title", "publisher", "place", "pages", "doi", "abstract"],
  manuscript: ["place", "num_pages", "abstract"],
  document: ["publisher", "place", "abstract"],
  webpage: ["url", "accessed_date", "abstract"],
  dataset: ["publisher", "url", "doi", "abstract"],
  preprint: ["publication", "doi", "url", "abstract"],
  other: ["publisher", "place", "abstract"],
  // Default for no item type selected - show common fields
  "": ["journal", "volume", "issue", "pages", "publisher", "abstract"],
};

/**
 * Human-readable labels for Zotero fields.
 */
export const FIELD_LABELS: Record<string, string> = {
  // Identifiers
  doi: "DOI",
  isbn: "ISBN",
  issn: "ISSN",
  url: "URL",
  // Publication
  publication: "Publication",
  journal: "Journal",
  volume: "Volume",
  issue: "Issue",
  pages: "Pages",
  edition: "Edition",
  // Publisher
  publisher: "Publisher",
  place: "Place",
  // Series
  series: "Series",
  series_number: "Series Number",
  // Book
  book_title: "Book Title",
  num_pages: "# of Pages",
  // Report/Thesis
  institution: "Institution",
  report_number: "Report Number",
  report_type: "Report Type",
  thesis_type: "Thesis Type",
  // Conference
  conference_name: "Conference Name",
  proceedings_title: "Proceedings Title",
  // Access
  accessed_date: "Date Accessed",
};

/**
 * Get the human-readable label for a field.
 */
export function getFieldLabel(field: string): string {
  return FIELD_LABELS[field] || field.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());
}
