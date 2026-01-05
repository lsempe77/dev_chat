"use client";

import { useState, useCallback, useEffect } from "react";
import { useParams } from "next/navigation";
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
  ChatHistory,
} from "@/components/workbench";
import type { ChatHistoryItem } from "@/components/workbench";
import type { SearchSettings } from "@/components/workbench";
import { Button } from "@/components/ui/button";
import { ArrowLeft, X, ExternalLink, Copy, Check, FileText, Loader2, PanelLeftClose, PanelLeft } from "lucide-react";
import { Study, Citation, Filter, EvidenceHealth, AnswerStyle } from "@/types";
import { PDFViewer } from "@/components/pdf";
import { 
  getChatHistory, 
  addChatHistory, 
  deleteChatHistoryItem,
  ChatHistoryItem as ApiChatHistoryItem 
} from "@/lib/api";

// Default evidence health for initial state
const defaultEvidenceHealth: EvidenceHealth = {
  studyCount: 0,
  dateRange: "",
  gaps: [],
  coverageWarning: undefined,
};

interface RAGProject {
  id: string;
  name: string;
  description: string | null;
  qdrant_collection: string;
  is_public: boolean;
}

/**
 * Evidence Snippet Card - Shows the matched text with copy-to-find functionality
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
            &quot;{snippet}&quot;
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

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function RAGChatPage() {
  const params = useParams();
  const ragId = params.ragId as string;
  
  // RAG project state
  const [project, setProject] = useState<RAGProject | null>(null);
  const [projectLoading, setProjectLoading] = useState(true);
  const [projectError, setProjectError] = useState<string | null>(null);
  
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
  const [searchSettings, setSearchSettings] = useState<SearchSettings>(defaultSettings);
  const [isFilterDrawerOpen, setIsFilterDrawerOpen] = useState(false);
  const [isCompareModalOpen, setIsCompareModalOpen] = useState(false);
  
  // Chat history state
  const [chatHistory, setChatHistory] = useState<ChatHistoryItem[]>([]);
  const [currentQueryId, setCurrentQueryId] = useState<string | undefined>();
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  
  // PDF Viewer state
  const [pdfViewerOpen, setPdfViewerOpen] = useState(false);
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [pdfPage, setPdfPage] = useState(1);
  const [pdfTitle, setPdfTitle] = useState("");
  const [pdfSearchText, setPdfSearchText] = useState<string | undefined>();
  const [pdfStudyId, setPdfStudyId] = useState<string | null>(null);

  // Fetch RAG project info
  useEffect(() => {
    const fetchProject = async () => {
      try {
        const response = await fetch(`${API_BASE_URL}/rags/${ragId}/public`);
        if (!response.ok) {
          if (response.status === 404) {
            setProjectError("RAG not found");
          } else if (response.status === 403) {
            setProjectError("This RAG is private");
          } else {
            setProjectError("Failed to load RAG");
          }
          return;
        }
        const data = await response.json();
        setProject(data);
        
        // Load chat history for this project
        loadChatHistory(ragId);
      } catch (err) {
        setProjectError("Failed to connect to server");
      } finally {
        setProjectLoading(false);
      }
    };
    
    fetchProject();
  }, [ragId]);

  // Load chat history from API
  const loadChatHistory = useCallback(async (projectId: string) => {
    try {
      const sessionId = getSessionId();
      const history = await getChatHistory(projectId, sessionId);
      setChatHistory(history.map(item => ({
        id: item.id,
        query: item.query,
        timestamp: new Date(item.timestamp),
        studyCount: item.studyCount,
        answer: item.answer,
        citationsUsed: item.citationsUsed,
        responseData: item.responseData,
      })));
    } catch (error) {
      console.error("Failed to load chat history:", error);
    }
  }, []);

  // Get or create session ID for anonymous users
  const getSessionId = useCallback((): string => {
    if (typeof window === "undefined") return "";
    let sessionId = localStorage.getItem("chat_session_id");
    if (!sessionId) {
      sessionId = `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
      localStorage.setItem("chat_session_id", sessionId);
    }
    return sessionId;
  }, []);


  const handleSearch = useCallback(async (searchQuery: string) => {
    if (!project) return;
    
    setQuery(searchQuery);
    setIsLoading(true);
    setHasSearched(true);
    setError(null);
    
    try {
      // Call the API with the specific RAG collection
      const response = await fetch(`${API_BASE_URL}/api/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query: searchQuery,
          collection: project.qdrant_collection,
          settings: searchSettings,
        }),
      });
      
      if (!response.ok) {
        throw new Error("Search failed");
      }
      
      const data = await response.json();
      
      setStudies(data.studies || []);
      setCitations(data.citations || []);
      setAnswer(data.answer || "");
      setSuggestions(data.suggestions || []);
      setEvidenceHealth(data.evidenceHealth || defaultEvidenceHealth);
      
      // Save to API and update local state (including full response for caching)
      const studyCount = (data.studies || []).length;
      const sessionId = getSessionId();
      const answerText = data.answer || "";
      const citationsCount = (data.citations || []).length;
      
      // Cache the full response data for instant recall
      const responseData = {
        citations: data.citations || [],
        studies: data.studies || [],
        suggestions: data.suggestions || [],
        evidenceHealth: data.evidenceHealth || defaultEvidenceHealth,
      };
      
      const savedItem = await addChatHistory(ragId, searchQuery, studyCount, sessionId, answerText, citationsCount, responseData);
      
      if (savedItem) {
        // Add to local state (at the beginning, remove duplicates)
        setChatHistory(prev => [{
          id: savedItem.id,
          query: savedItem.query,
          timestamp: new Date(savedItem.timestamp),
          studyCount: savedItem.studyCount,
          answer: savedItem.answer,
          responseData: savedItem.responseData,
        }, ...prev.filter(h => h.query !== searchQuery)]);
        setCurrentQueryId(savedItem.id);
      }
      
    } catch (err) {
      console.error("Search failed:", err);
      setError(err instanceof Error ? err.message : "Search failed. Please try again.");
    } finally {
      setIsLoading(false);
    }
  }, [project, searchSettings, ragId, getSessionId]);

  const handleCitationClick = useCallback(async (citationId: number) => {
    if (!project) return;
    
    setHighlightedCitation(citationId);
    
    const citation = citations.find(c => c.id === citationId);
    if (!citation) return;
    
    const studyElement = document.getElementById(`study-${citation.studyId}`);
    if (studyElement) {
      studyElement.scrollIntoView({ behavior: "smooth", block: "center" });
    }
    
    if (pdfViewerOpen && pdfStudyId === citation.studyId) {
      setTimeout(() => setHighlightedCitation(undefined), 3000);
      return;
    }
    
    try {
      const response = await fetch(
        `${API_BASE_URL}/rags/${ragId}/documents/${citation.studyId}/pdf-url`
      );
      if (response.ok) {
        const data = await response.json();
        setPdfUrl(data.url);
        setPdfPage(citation.page || 1);
        setPdfTitle(citation.study?.title || citation.studyId);
        setPdfStudyId(citation.studyId);
        setPdfSearchText(citation.highlightText || citation.text?.slice(0, 50));
        setPdfViewerOpen(true);
      }
    } catch (err) {
      console.error("Failed to load PDF:", err);
    }
    
    setTimeout(() => setHighlightedCitation(undefined), 3000);
  }, [citations, pdfViewerOpen, pdfStudyId, project, ragId]);
  
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
    setCurrentQueryId(undefined);
  }, []);

  const handleSuggestionClick = useCallback((suggestion: string) => {
    handleSearch(suggestion);
  }, [handleSearch]);

  // Chat history handlers - use cached response if available, otherwise re-search
  const handleSelectHistoryItem = useCallback((item: ChatHistoryItem) => {
    // If we have a cached full response, restore it completely (no API call needed)
    if (item.responseData) {
      setQuery(item.query);
      setAnswer(item.answer || "");
      // Cast cached citations to Citation[] - the cache stores a compatible subset
      setCitations((item.responseData.citations || []) as Citation[]);
      setStudies((item.responseData.studies || []) as Study[]);
      setSuggestions(item.responseData.suggestions || []);
      setEvidenceHealth(item.responseData.evidenceHealth as EvidenceHealth || defaultEvidenceHealth);
      setHasSearched(true);
      setCurrentQueryId(item.id);
      setError(null);
    } else if (item.answer) {
      // Fallback: only answer cached (legacy), show answer but no citations/studies
      setQuery(item.query);
      setAnswer(item.answer);
      setHasSearched(true);
      setCurrentQueryId(item.id);
      setCitations([]);
      setStudies([]);
      setSuggestions([]);
      setError(null);
    } else {
      // No cached data, re-run the search
      handleSearch(item.query);
    }
  }, [handleSearch]);

  const handleDeleteHistoryItem = useCallback(async (id: string) => {
    // Delete from API
    await deleteChatHistoryItem(ragId, id);
    
    // Update local state
    setChatHistory(prev => prev.filter(h => h.id !== id));
    if (currentQueryId === id) {
      setCurrentQueryId(undefined);
    }
  }, [currentQueryId, ragId]);

  const handleNewChat = useCallback(() => {
    handleReset();
  }, [handleReset]);

  // Loading state
  if (projectLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="flex items-center gap-2 text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" />
          <span>Loading...</span>
        </div>
      </div>
    );
  }

  // Error state
  if (projectError || !project) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="text-center">
          <h1 className="text-2xl font-bold mb-2">
            {projectError || "RAG not found"}
          </h1>
          <p className="text-muted-foreground mb-4">
            The requested knowledge base could not be loaded.
          </p>
          <Button onClick={() => window.location.href = "/"}>
            Go Home
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background flex">
      {/* Chat History Sidebar */}
      {isSidebarOpen && (
        <aside className="w-64 shrink-0 h-screen sticky top-0">
          <ChatHistory
            history={chatHistory}
            currentQueryId={currentQueryId}
            onSelectQuery={handleSelectHistoryItem}
            onDeleteQuery={handleDeleteHistoryItem}
            onNewChat={handleNewChat}
          />
        </aside>
      )}
      
      {/* Main Content */}
      <div className="flex-1 min-w-0">
        {/* Header */}
        <header className="border-b bg-card">
          <div className="container mx-auto px-4 py-4">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-3">
                {/* Sidebar Toggle */}
                <Button 
                  variant="ghost" 
                  size="icon" 
                  onClick={() => setIsSidebarOpen(!isSidebarOpen)}
                  title={isSidebarOpen ? "Hide history" : "Show history"}
                  className="h-8 w-8"
                >
                  {isSidebarOpen ? (
                    <PanelLeftClose className="h-4 w-4" />
                  ) : (
                    <PanelLeft className="h-4 w-4" />
                  )}
                </Button>
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
                {project.name}
              </h1>
            </div>
            <div className="flex items-center gap-2">
              <SettingsDrawer 
                settings={searchSettings} 
                onSettingsChange={setSearchSettings} 
              />
            </div>
          </div>
          {project.description && !hasSearched && (
            <p className="text-muted-foreground text-sm mb-4">{project.description}</p>
          )}
          <SearchInput onSearch={handleSearch} isLoading={isLoading} value={query} />
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
              Ask anything about this knowledge base
            </h2>
            <p className="text-muted-foreground max-w-lg mb-8">
              Search through documents, get AI-synthesized answers with citations,
              and explore the evidence.
            </p>
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
                  answerStyle={"executive" as AnswerStyle}
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

      {/* Compare Bar */}
      {selectedStudies.length > 0 && (
        <div className="fixed bottom-0 left-0 right-0 bg-card border-t p-4 z-50 shadow-lg">
          <div className="container mx-auto flex items-center justify-between">
            <span className="text-sm">
              <strong>{selectedStudies.length}</strong> studies selected
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

      {/* PDF Viewer Side Panel */}
      {pdfViewerOpen && pdfUrl && (
        <div className="fixed inset-y-0 right-0 w-1/2 bg-background border-l shadow-xl z-50 flex flex-col">
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
          
          {pdfSearchText && (
            <EvidenceSnippetCard 
              snippet={pdfSearchText}
              page={pdfPage}
              title={pdfTitle}
            />
          )}
          
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
    </div>
  );
}
