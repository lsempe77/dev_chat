"use client";

import { useState, useCallback } from "react";
import {
  SplitLayout,
  FilterChips,
  FilterDrawer,
  SettingsDrawer,
  defaultSettings,
  EvidencePanel,
  AnswerPanel,
  SearchInput,
  CompareModal,
} from "@/components/workbench";
import type { SearchSettings } from "@/components/workbench";
import { Button } from "@/components/ui/button";
import { ArrowLeft, Database, X, ExternalLink, Copy, Check, FileText } from "lucide-react";
import Link from "next/link";
import { Study, Citation, Filter, EvidenceHealth, AnswerStyle } from "@/types";
import { queryEvidence } from "@/lib/api";
import { PDFViewer } from "@/components/pdf";
import { getPDFUrl } from "@/lib/admin-api";

// Default evidence health for initial state
const defaultEvidenceHealth: EvidenceHealth = {
  studyCount: 0,
  dateRange: "",
  gaps: [],
  coverageWarning: undefined,
};

/**
 * Evidence Snippet Card - Shows the matched text with copy-to-find functionality
 * This provides a reliable highlight experience even when browser PDF viewers don't support #search=
 */
function EvidenceSnippetCard({ 
  snippet, 
  page, 
  title 
}: { 
  snippet: string; 
  page: number; 
  title: string;
}) {
  const [copied, setCopied] = useState(false);
  
  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(snippet);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error("Failed to copy:", err);
    }
  };
  
  return (
    <div className="p-3 border-b bg-amber-50 dark:bg-amber-950/30">
      <div className="flex items-start gap-2">
        <FileText className="h-4 w-4 mt-0.5 text-amber-600 flex-shrink-0" />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-xs font-medium text-amber-800 dark:text-amber-200">
              Page {page}
            </span>
            <span className="text-xs text-amber-600 dark:text-amber-400">
              • Use Ctrl/Cmd+F to find this text
            </span>
          </div>
          <p className="text-sm text-amber-900 dark:text-amber-100 italic line-clamp-2">
            "{snippet}"
          </p>
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={handleCopy}
          className="flex-shrink-0 h-7 px-2"
          title="Copy snippet to clipboard"
        >
          {copied ? (
            <Check className="h-3.5 w-3.5 text-green-600" />
          ) : (
            <Copy className="h-3.5 w-3.5" />
          )}
        </Button>
      </div>
    </div>
  );
}

export default function Home() {
  const [query, setQuery] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  // Data state
  const [studies, setStudies] = useState<Study[]>([]);
  const [citations, setCitations] = useState<Citation[]>([]);
  const [answer, setAnswer] = useState("");
  const [evidenceHealth, setEvidenceHealth] = useState<EvidenceHealth>(defaultEvidenceHealth);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  
  // UI state
  const [filters, setFilters] = useState<Filter[]>([]);
  const [selectedStudies, setSelectedStudies] = useState<Study[]>([]);
  const [highlightedCitation, setHighlightedCitation] = useState<number | undefined>();
  const [answerStyle, setAnswerStyle] = useState<AnswerStyle>("executive");
  const [isCompareModalOpen, setIsCompareModalOpen] = useState(false);
  const [searchSettings, setSearchSettings] = useState<SearchSettings>(defaultSettings);
  const [isFilterDrawerOpen, setIsFilterDrawerOpen] = useState(false);
  
  // PDF Viewer state
  const [pdfViewerOpen, setPdfViewerOpen] = useState(false);
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [pdfPage, setPdfPage] = useState(1);
  const [pdfTitle, setPdfTitle] = useState("");
  const [pdfSearchText, setPdfSearchText] = useState<string | undefined>();
  const [pdfStudyId, setPdfStudyId] = useState<string | null>(null);  // Track which study's PDF is open

  const handleSearch = useCallback(async (searchQuery: string) => {
    console.log("[Page] handleSearch called with searchSettings:", searchSettings);
    setQuery(searchQuery);
    setIsLoading(true);
    setHasSearched(true);
    setError(null);
    
    try {
      // Call the real API with settings
      const response = await queryEvidence(searchQuery, filters, searchSettings);
      
      setStudies(response.studies);
      setCitations(response.citations);
      setAnswer(response.answer);
      setSuggestions(response.suggestions);
      setEvidenceHealth(response.evidenceHealth);
    } catch (err) {
      console.error("Search failed:", err);
      setError(err instanceof Error ? err.message : "Search failed. Please try again.");
      // Keep the UI in searched state so user can see the error
    } finally {
      setIsLoading(false);
    }
  }, [filters, searchSettings]);

  const handleCitationClick = useCallback(async (citationId: number) => {
    setHighlightedCitation(citationId);
    
    // Find the citation
    const citation = citations.find(c => c.id === citationId);
    if (!citation) return;
    
    // Scroll to the study card
    const studyElement = document.getElementById(`study-${citation.studyId}`);
    if (studyElement) {
      studyElement.scrollIntoView({ behavior: "smooth", block: "center" });
    }
    
    // Check if we already have this study's PDF open - don't re-fetch
    if (pdfViewerOpen && pdfStudyId === citation.studyId) {
      // Same PDF already open - no action needed
      // Clear highlight after 3 seconds
      setTimeout(() => setHighlightedCitation(undefined), 3000);
      return;
    }
    
    // Open PDF viewer with the citation's page and highlight text
    try {
      const response = await getPDFUrl(citation.studyId);
      setPdfUrl(response.url);
      setPdfPage(citation.page || 1);
      setPdfTitle(citation.study?.title || citation.studyId);
      setPdfStudyId(citation.studyId);  // Track which study
      // Use highlightText from citation, or fall back to first part of citation text
      setPdfSearchText(citation.highlightText || citation.text?.slice(0, 50));
      setPdfViewerOpen(true);
    } catch (err) {
      console.error("Failed to load PDF:", err);
      // Fall back to just highlighting
    }
    
    // Clear highlight after 3 seconds
    setTimeout(() => setHighlightedCitation(undefined), 3000);
  }, [citations, pdfViewerOpen, pdfStudyId]);
  
  const closePdfViewer = useCallback(() => {
    setPdfViewerOpen(false);
    setPdfUrl(null);
    setPdfStudyId(null);
  }, []);

  const handleSelectStudy = useCallback((study: Study) => {
    setSelectedStudies((prev) => {
      const isSelected = prev.some((s) => s.id === study.id);
      if (isSelected) {
        return prev.filter((s) => s.id !== study.id);
      }
      return [...prev, study];
    });
  }, []);

  const handleRemoveFilter = useCallback((filter: Filter) => {
    setFilters((prev) => prev.filter((f) => f.id !== filter.id));
  }, []);

  const handleAddFilter = useCallback((filter: Filter) => {
    setFilters((prev) => {
      // Don't add duplicates
      if (prev.some((f) => f.id === filter.id)) return prev;
      return [...prev, filter];
    });
  }, []);

  const handleReset = useCallback(() => {
    setHasSearched(false);
    setQuery("");
    setStudies([]);
    setCitations([]);
    setAnswer("");
    setSuggestions([]);
    setSelectedStudies([]);
    setFilters([]);
    setError(null);
  }, []);

  const handleSuggestionClick = useCallback((suggestion: string) => {
    handleSearch(suggestion);
  }, [handleSearch]);

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="border-b bg-card">
        <div className="container mx-auto px-4 py-4">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-3">
              {hasSearched && (
                <Button variant="ghost" size="sm" onClick={handleReset} className="gap-1">
                  <ArrowLeft className="h-4 w-4" />
                  New Search
                </Button>
              )}
              <h1 
                className="text-2xl font-bold cursor-pointer hover:opacity-80 transition-opacity"
                onClick={handleReset}
              >
                Chat Research Workbench
              </h1>
            </div>
            <div className="flex items-center gap-2">
              <Link href="/admin">
                <Button variant="outline" size="sm" className="gap-1">
                  <Database className="h-4 w-4" />
                  Admin
                </Button>
              </Link>
              <SettingsDrawer 
                settings={searchSettings} 
                onSettingsChange={setSearchSettings} 
              />
              <span className="text-sm text-muted-foreground">
                3ie
              </span>
            </div>
          </div>
          <SearchInput onSearch={handleSearch} isLoading={isLoading} />
        </div>
      </header>

      {/* Filter Bar */}
      {hasSearched && (
        <div className="container mx-auto px-4 py-2">
          <div className="flex items-center gap-2">
            <FilterChips
              filters={filters}
              onRemove={handleRemoveFilter}
              onAdd={() => setIsFilterDrawerOpen(true)}
            />
            <FilterDrawer
              isOpen={isFilterDrawerOpen}
              onOpenChange={setIsFilterDrawerOpen}
              currentFilters={filters}
              onAddFilter={handleAddFilter}
              onRemoveFilter={handleRemoveFilter}
            />
          </div>
        </div>
      )}

      {/* Main Content */}
      <main className="container mx-auto px-4 py-4">
        {!hasSearched ? (
          <div className="flex flex-col items-center justify-center min-h-[60vh] text-center">
            <h2 className="text-3xl font-semibold mb-4">
              Explore Development Evidence
            </h2>
            <p className="text-muted-foreground max-w-lg mb-8">
              Ask questions about development interventions, compare studies,
              and get AI-synthesized answers backed by rigorous evidence.
            </p>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 max-w-2xl">
              {[
                "What are the effects of cash transfers on food security?",
                "How do education interventions impact learning outcomes?",
                "Compare CCT vs UCT programs in Africa",
              ].map((example) => (
                <button
                  key={example}
                  onClick={() => handleSearch(example)}
                  className="p-4 text-left text-sm border rounded-lg hover:bg-muted transition-colors"
                >
                  {example}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <>
            {error && (
              <div className="bg-destructive/15 text-destructive border border-destructive/30 rounded-lg p-4 mb-4 mx-4">
                <p className="font-medium">Error</p>
                <p className="text-sm">{error}</p>
              </div>
            )}
            <SplitLayout
              leftPanel={
                <AnswerPanel
                  answer={answer}
                  citations={citations}
                  evidenceHealth={evidenceHealth}
                  suggestions={suggestions}
                  answerStyle={answerStyle}
                  isLoading={isLoading}
                  onCitationClick={handleCitationClick}
                  onSuggestionClick={handleSuggestionClick}
                />
              }
              rightPanel={
                <EvidencePanel
                  studies={studies}
                  citations={citations}
                  highlightedCitation={highlightedCitation}
                  selectedStudies={selectedStudies}
                  onSelectStudy={handleSelectStudy}
                  onExcludeStudy={(study) => {
                    setStudies((prev) => prev.filter((s) => s.id !== study.id));
                  }}
                  onOpenPdf={(study) => {
                    if (study.pdfUrl) window.open(study.pdfUrl, "_blank");
                  }}
                  query={query}
                  answer={answer}
                />
              }
            />
          </>
        )}
      </main>

      {/* Compare Bar (shows when studies selected) */}
      {selectedStudies.length > 0 && (
        <div className="fixed bottom-0 left-0 right-0 bg-card border-t p-4 z-50 shadow-lg">
          <div className="container mx-auto flex items-center justify-between">
            <span className="text-sm">
              <strong>{selectedStudies.length}</strong> studies selected for comparison
            </span>
            <div className="flex gap-2">
              <button
                onClick={() => setSelectedStudies([])}
                className="px-4 py-2 text-sm border rounded-lg hover:bg-muted"
              >
                Clear
              </button>
              <button
                onClick={() => setIsCompareModalOpen(true)}
                className="px-4 py-2 text-sm bg-primary text-primary-foreground rounded-lg hover:bg-primary/90"
              >
                Compare Studies
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Compare Modal */}
      <CompareModal
        isOpen={isCompareModalOpen}
        onClose={() => setIsCompareModalOpen(false)}
        studies={selectedStudies}
        onRemoveStudy={(study) => {
          setSelectedStudies((prev) => prev.filter((s) => s.id !== study.id));
          if (selectedStudies.length <= 1) {
            setIsCompareModalOpen(false);
          }
        }}
      />

      {/* PDF Viewer Side Panel with Evidence Card */}
      {pdfViewerOpen && pdfUrl && (
        <div className="fixed inset-y-0 right-0 w-1/2 bg-background border-l shadow-xl z-50 flex flex-col">
          {/* Header */}
          <div className="flex items-center justify-between p-3 border-b bg-card">
            <h3 className="font-medium text-sm truncate flex-1 mr-2">{pdfTitle}</h3>
            <div className="flex items-center gap-2">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => window.open(pdfUrl, '_blank')}
                title="Open in new tab"
              >
                <ExternalLink className="h-4 w-4" />
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={closePdfViewer}
              >
                <X className="h-4 w-4" />
              </Button>
            </div>
          </div>
          
          {/* Evidence Card - Shows the matched snippet with copy button */}
          {pdfSearchText && (
            <EvidenceSnippetCard 
              snippet={pdfSearchText}
              page={pdfPage}
              title={pdfTitle}
            />
          )}
          
          {/* PDF Content */}
          <div className="flex-1">
            <PDFViewer
              url={pdfUrl}
              initialPage={pdfPage}
              searchText={pdfSearchText}
              hideToolbar
            />
          </div>
        </div>
      )}
    </div>
  );
}
