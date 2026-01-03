"use client";

import { useState, useEffect, useCallback } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { 
  FileText, 
  Search,
  Edit2,
  Check,
  CheckCircle,
  AlertCircle,
  Loader2,
  RefreshCw,
  Globe,
  Building,
  Beaker,
  Eye,
  ExternalLink,
  X,
  Sparkles,
  Trash2,
} from "lucide-react";
import { 
  getRagMetadata, 
  updateRagDocumentMetadata,
  enrichRagDocumentMetadata,
  enrichAllRagDocuments,
  getRagPdfUrl,
  deleteRagDocument,
  type MetadataDetail,
  type MetadataUpdateRequest,
} from "@/lib/rag-api";
import { PDFViewer } from "@/components/pdf";
import { MetadataEditPanel } from "@/components/admin/metadata/MetadataEditPanel";
import { type DocumentMetadataDetail } from "@/lib/admin-api/types";

interface RagMetadataTabProps {
  ragId: string;
}

export function RagMetadataTab({ ragId }: RagMetadataTabProps) {
  // State
  const [documents, setDocuments] = useState<MetadataDetail[]>([]);
  const [filterType, setFilterType] = useState<"all" | "needs_review">("needs_review");
  const [searchQuery, setSearchQuery] = useState("");
  const [page, setPage] = useState(1);
  const [limit, setLimit] = useState(50);
  const [totalPages, setTotalPages] = useState(1);
  const [stats, setStats] = useState({
    needsReview: 0,
    total: 0,
  });
  
  const [editingDoc, setEditingDoc] = useState<MetadataDetail | null>(null);
  const [editForm, setEditForm] = useState<MetadataUpdateRequest>({});
  const [viewingPdfDoc, setViewingPdfDoc] = useState<MetadataDetail | null>(null);
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [isLoadingPdf, setIsLoadingPdf] = useState(false);
  const [isEnriching, setIsEnriching] = useState<string | null>(null);
  const [isEnrichingAll, setIsEnrichingAll] = useState(false);
  const [enrichAllResult, setEnrichAllResult] = useState<string | null>(null);
  const [isDeleting, setIsDeleting] = useState<string | null>(null);

  // Open PDF viewer
  const openPdfViewer = async (doc: MetadataDetail) => {
    setIsLoadingPdf(true);
    setViewingPdfDoc(doc);
    try {
      const response = await getRagPdfUrl(ragId, doc.id);
      setPdfUrl(response.url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load PDF");
      setViewingPdfDoc(null);
    } finally {
      setIsLoadingPdf(false);
    }
  };

  // Close PDF viewer
  const closePdfViewer = () => {
    setViewingPdfDoc(null);
    setPdfUrl(null);
  };

  // Fetch documents
  const fetchDocuments = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await getRagMetadata(ragId, {
        filter: filterType,
        page,
        limit,
        search: searchQuery,
      });
      setDocuments(response.documents);
      setStats({
        needsReview: response.needs_review_count,
        total: response.total_count,
      });
      setTotalPages(Math.ceil(response.total_count / limit));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load documents");
    } finally {
      setIsLoading(false);
    }
  }, [ragId, filterType, page, limit, searchQuery]);

  // Initial load
  useEffect(() => {
    fetchDocuments();
  }, [fetchDocuments]);

  // Convert MetadataDetail to DocumentMetadataDetail for edit panel compatibility
  const toDocumentMetadataDetail = (doc: MetadataDetail): DocumentMetadataDetail => ({
    id: doc.id,
    filename: doc.filename,
    title: doc.title,
    authors: doc.authors,
    year: doc.year ?? undefined,
    abstract: doc.abstract ?? undefined,
    item_type: doc.item_type ?? undefined,
    doi: doc.doi ?? undefined,
    isbn: doc.isbn ?? undefined,
    issn: doc.issn ?? undefined,
    url: doc.url ?? undefined,
    publication: doc.publication ?? undefined,
    journal: doc.journal ?? undefined,
    volume: doc.volume ?? undefined,
    issue: doc.issue ?? undefined,
    pages: doc.pages ?? undefined,
    publisher: doc.publisher ?? undefined,
    place: doc.place ?? undefined,
    // New Zotero fields
    edition: doc.edition ?? undefined,
    series: doc.series ?? undefined,
    series_number: doc.series_number ?? undefined,
    book_title: doc.book_title ?? undefined,
    num_pages: doc.num_pages ?? undefined,
    institution: doc.institution ?? undefined,
    report_number: doc.report_number ?? undefined,
    report_type: doc.report_type ?? undefined,
    thesis_type: doc.thesis_type ?? undefined,
    conference_name: doc.conference_name ?? undefined,
    proceedings_title: doc.proceedings_title ?? undefined,
    accessed_date: doc.accessed_date ?? undefined,
    // Classification
    countries: doc.countries,
    sectors: doc.sectors,
    study_type: doc.study_type ?? undefined,
    intervention_type: doc.intervention_type ?? undefined,
    metadata_source: doc.metadata_source,
    metadata_confidence: doc.metadata_confidence,
    needs_review: doc.needs_review,
    chunk_count: doc.chunk_count,
    // Additional fields with defaults
    is_open_access: false,
    sdgs: [],
    keywords: [],
  });

  // Open edit modal
  const openEditModal = (doc: MetadataDetail) => {
    setEditingDoc(doc);
    setEditForm({
      title: doc.title,
      authors: doc.authors,
      year: doc.year ?? undefined,
      abstract: doc.abstract ?? undefined,
      item_type: doc.item_type ?? undefined,
      doi: doc.doi ?? undefined,
      isbn: doc.isbn ?? undefined,
      issn: doc.issn ?? undefined,
      url: doc.url ?? undefined,
      publication: doc.publication ?? undefined,
      journal: doc.journal ?? undefined,
      volume: doc.volume ?? undefined,
      issue: doc.issue ?? undefined,
      pages: doc.pages ?? undefined,
      publisher: doc.publisher ?? undefined,
      place: doc.place ?? undefined,
      // New Zotero fields
      edition: doc.edition ?? undefined,
      series: doc.series ?? undefined,
      series_number: doc.series_number ?? undefined,
      book_title: doc.book_title ?? undefined,
      num_pages: doc.num_pages ?? undefined,
      institution: doc.institution ?? undefined,
      report_number: doc.report_number ?? undefined,
      report_type: doc.report_type ?? undefined,
      thesis_type: doc.thesis_type ?? undefined,
      conference_name: doc.conference_name ?? undefined,
      proceedings_title: doc.proceedings_title ?? undefined,
      accessed_date: doc.accessed_date ?? undefined,
      // Classification
      countries: doc.countries,
      sectors: doc.sectors,
      study_type: doc.study_type ?? undefined,
      intervention_type: doc.intervention_type ?? undefined,
    });
  };

  // Save changes
  const handleSave = async () => {
    if (!editingDoc) return;
    
    setIsSaving(true);
    try {
      await updateRagDocumentMetadata(ragId, editingDoc.id, {
        ...editForm,
        // Don't auto-remove from review - user can explicitly mark as reviewed
      });
      setEditingDoc(null);
      fetchDocuments();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save changes");
    } finally {
      setIsSaving(false);
    }
  };

  // Mark as reviewed
  const markAsReviewed = async (docId: string) => {
    try {
      await updateRagDocumentMetadata(ragId, docId, { needs_review: false });
      fetchDocuments();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update");
    }
  };

  // Enrich from CrossRef/OpenAlex
  const handleEnrich = async (doc: MetadataDetail) => {
    setIsEnriching(doc.id);
    try {
      await enrichRagDocumentMetadata(ragId, doc.id);
      fetchDocuments();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Enrichment failed");
    } finally {
      setIsEnriching(null);
    }
  };

  // Enrich all documents
  const handleEnrichAll = async () => {
    setIsEnrichingAll(true);
    setEnrichAllResult(null);
    try {
      const result = await enrichAllRagDocuments(ragId);
      setEnrichAllResult(`Enriched ${result.enriched} of ${result.total} documents (${result.skipped} skipped, ${result.failed} failed)`);
      fetchDocuments();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Enrich all failed");
    } finally {
      setIsEnrichingAll(false);
    }
  };

  // Delete a document
  const handleDelete = async (doc: MetadataDetail) => {
    if (!confirm(`Delete "${doc.filename}"?\n\nThis will also remove associated vectors and files. This action cannot be undone.`)) {
      return;
    }
    
    setIsDeleting(doc.id);
    try {
      await deleteRagDocument(ragId, doc.id);
      // Close edit panel if deleting the currently edited doc
      if (editingDoc?.id === doc.id) {
        setEditingDoc(null);
      }
      // Close PDF viewer if viewing this doc
      if (viewingPdfDoc?.id === doc.id) {
        closePdfViewer();
      }
      fetchDocuments();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete document");
    } finally {
      setIsDeleting(null);
    }
  };

  const getConfidenceBadge = (confidence: number) => {
    if (confidence >= 0.8) {
      return <Badge variant="default" className="bg-green-600">High ({(confidence * 100).toFixed(0)}%)</Badge>;
    } else if (confidence >= 0.5) {
      return <Badge variant="default" className="bg-yellow-600">Medium ({(confidence * 100).toFixed(0)}%)</Badge>;
    } else {
      return <Badge variant="destructive">Low ({(confidence * 100).toFixed(0)}%)</Badge>;
    }
  };

  const getSourceBadge = (source: string) => {
    switch (source) {
      case "crossref":
        return <Badge variant="outline" className="border-blue-500 text-blue-600">CrossRef</Badge>;
      case "openalex":
        return <Badge variant="outline" className="border-purple-500 text-purple-600">OpenAlex</Badge>;
      case "user":
        return <Badge variant="outline" className="border-green-500 text-green-600">Verified</Badge>;
      default:
        return <Badge variant="outline">Extracted</Badge>;
    }
  };

  return (
    <div className="space-y-6">
      {/* Stats Cards */}
      <div className="grid grid-cols-2 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Needs Review
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-2">
              <AlertCircle className="h-5 w-5 text-yellow-500" />
              <span className="text-2xl font-bold">{stats.needsReview}</span>
            </div>
          </CardContent>
        </Card>
        
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Total Documents
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-2">
              <FileText className="h-5 w-5 text-blue-500" />
              <span className="text-2xl font-bold">{stats.total}</span>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Main Content */}
      <div className="flex gap-4" style={{ height: 'calc(100vh - 320px)' }}>
        {/* Left Panel: Document List */}
        <Card className={editingDoc || viewingPdfDoc ? "w-1/3 flex flex-col" : "w-full"}>
          <CardHeader className="flex-shrink-0">
            <div className="flex items-center justify-between">
              <div>
                <CardTitle>Metadata Review</CardTitle>
                <CardDescription>
                  Review and correct document metadata for accurate citations
                </CardDescription>
              </div>
              <div className="flex gap-2">
                <Button 
                  variant="outline" 
                  size="sm" 
                  onClick={handleEnrichAll}
                  disabled={isEnrichingAll || stats.total === 0}
                  title="Auto-fetch metadata for all documents from CrossRef/OpenAlex"
                >
                  {isEnrichingAll ? (
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  ) : (
                    <Sparkles className="h-4 w-4 mr-2" />
                  )}
                  Enrich All
                </Button>
                <Button variant="outline" size="sm" onClick={fetchDocuments}>
                  <RefreshCw className="h-4 w-4 mr-2" />
                  Refresh
                </Button>
              </div>
            </div>
          </CardHeader>
          <CardContent className="flex-1 overflow-hidden">
            <div className="flex gap-4 mb-4">
              <div className="flex-1">
                <div className="relative">
                  <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    placeholder="Search documents..."
                    value={searchQuery}
                    onChange={(e) => { setSearchQuery(e.target.value); setPage(1); }}
                    className="pl-10"
                  />
                </div>
              </div>
              <Tabs value={filterType} onValueChange={(v) => { setFilterType(v as typeof filterType); setPage(1); }}>
                <TabsList>
                  <TabsTrigger value="needs_review">Needs Review</TabsTrigger>
                  <TabsTrigger value="all">All</TabsTrigger>
                </TabsList>
              </Tabs>
            </div>

            {error && (
              <div className="flex items-center gap-2 p-3 mb-4 text-red-600 bg-red-50 rounded-lg">
                <AlertCircle className="h-4 w-4" />
                {error}
                <Button variant="ghost" size="sm" onClick={() => setError(null)}>
                  <X className="h-4 w-4" />
                </Button>
              </div>
            )}

            {enrichAllResult && (
              <div className="flex items-center gap-2 p-3 mb-4 text-green-600 bg-green-50 rounded-lg">
                <CheckCircle className="h-4 w-4" />
                {enrichAllResult}
                <Button variant="ghost" size="sm" onClick={() => setEnrichAllResult(null)}>
                  <X className="h-4 w-4" />
                </Button>
              </div>
            )}

            {isLoading ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
              </div>
            ) : (
              <ScrollArea className="h-full">
                <div className="space-y-3 pr-2">
                  {documents.map((doc) => (
                    <Card 
                      key={doc.id} 
                      className={`hover:bg-muted/50 ${editingDoc?.id === doc.id ? 'ring-2 ring-primary' : ''} ${viewingPdfDoc?.id === doc.id ? 'ring-2 ring-blue-400' : ''}`}
                    >
                      <CardContent className="p-4">
                        <div className="space-y-3">
                          <div>
                            <div className="flex items-center gap-2 mb-1">
                              <h4 className="font-medium line-clamp-2">{doc.title}</h4>
                              {doc.needs_review && (
                                <Badge variant="outline" className="text-yellow-600 border-yellow-500 flex-shrink-0">
                                  Needs Review
                                </Badge>
                              )}
                            </div>
                            
                            <div className="flex flex-wrap gap-2 text-sm text-muted-foreground mb-2">
                              {doc.authors.length > 0 && (
                                <span>{doc.authors.slice(0, 2).join(", ")}{doc.authors.length > 2 ? " et al." : ""}</span>
                              )}
                              {doc.year && <span>• {doc.year}</span>}
                              {doc.journal && <span>• {doc.journal}</span>}
                            </div>

                            <div className="flex flex-wrap gap-2 mb-2">
                              {doc.needs_reprocessing && (
                                <Badge variant="destructive" className="gap-1">
                                  <AlertCircle className="h-3 w-3" />
                                  Needs Reprocessing
                                </Badge>
                              )}
                              {getConfidenceBadge(doc.metadata_confidence)}
                              {getSourceBadge(doc.metadata_source)}
                              {doc.doi && (
                                <Badge variant="outline" className="gap-1">
                                  <ExternalLink className="h-3 w-3" />
                                  DOI
                                </Badge>
                              )}
                              {doc.countries.length > 0 && (
                                <Badge variant="secondary" className="gap-1">
                                  <Globe className="h-3 w-3" />
                                  {doc.countries.slice(0, 2).join(", ")}
                                </Badge>
                              )}
                              {doc.sectors.length > 0 && (
                                <Badge variant="secondary" className="gap-1">
                                  <Building className="h-3 w-3" />
                                  {doc.sectors.slice(0, 2).join(", ")}
                                </Badge>
                              )}
                              {doc.study_type && (
                                <Badge variant="secondary" className="gap-1">
                                  <Beaker className="h-3 w-3" />
                                  {doc.study_type}
                                </Badge>
                              )}
                              {doc.item_type && (
                                <Badge variant="outline" className="gap-1">
                                  <FileText className="h-3 w-3" />
                                  {doc.item_type}
                                </Badge>
                              )}
                            </div>

                            <div className="text-xs text-muted-foreground">
                              {doc.chunk_count} chunks indexed • {doc.filename}
                            </div>
                          </div>

                          <div className="flex gap-2 pt-2 border-t flex-wrap">
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => openPdfViewer(doc)}
                            >
                              <Eye className="h-4 w-4 mr-1" />
                              View PDF
                            </Button>
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => openEditModal(doc)}
                            >
                              <Edit2 className="h-4 w-4 mr-1" />
                              Edit
                            </Button>
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => handleEnrich(doc)}
                              disabled={isEnriching === doc.id}
                              title="Auto-fetch metadata from CrossRef/OpenAlex"
                            >
                              {isEnriching === doc.id ? (
                                <Loader2 className="h-4 w-4 mr-1 animate-spin" />
                              ) : (
                                <Sparkles className="h-4 w-4 mr-1" />
                              )}
                              Enrich
                            </Button>
                            {doc.needs_review && (
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => markAsReviewed(doc.id)}
                              >
                                <Check className="h-4 w-4 mr-1" />
                                Mark OK
                              </Button>
                            )}
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => handleDelete(doc)}
                              disabled={isDeleting === doc.id}
                              className="text-destructive hover:text-destructive hover:bg-destructive/10"
                              title="Delete document"
                            >
                              {isDeleting === doc.id ? (
                                <Loader2 className="h-4 w-4 animate-spin" />
                              ) : (
                                <Trash2 className="h-4 w-4" />
                              )}
                            </Button>
                          </div>
                        </div>
                      </CardContent>
                    </Card>
                  ))}

                  {documents.length === 0 && !isLoading && (
                    <div className="text-center py-12 text-muted-foreground">
                      <CheckCircle className="h-12 w-12 mx-auto mb-3 text-green-500" />
                      <p>No documents {filterType === "needs_review" ? "need review" : "found"}!</p>
                    </div>
                  )}
                </div>
              </ScrollArea>
            )}
            
            <div className="flex items-center justify-between pt-4 border-t mt-2 shrink-0">
               <div className="text-sm text-muted-foreground">
                 Page {page} of {totalPages}
               </div>
               <div className="flex gap-2">
                 <Button variant="outline" size="sm" onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}>
                   Previous
                 </Button>
                 <Button variant="outline" size="sm" onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page === totalPages}>
                   Next
                 </Button>
               </div>
            </div>
          </CardContent>
        </Card>

        {/* Center Panel: Metadata Edit */}
        {editingDoc && (
          <div className="w-1/3 h-full">
            <MetadataEditPanel
              document={toDocumentMetadataDetail(editingDoc)}
              editForm={editForm}
              setEditForm={setEditForm as any}
              onClose={() => setEditingDoc(null)}
              onSave={handleSave}
              onViewPdf={() => openPdfViewer(editingDoc)}
              isSaving={isSaving}
              isPdfOpen={viewingPdfDoc?.id === editingDoc.id}
            />
          </div>
        )}

        {/* Right Panel: PDF Viewer */}
        {viewingPdfDoc && (
          <div className="w-1/3 flex flex-col border rounded-lg overflow-hidden bg-white h-full">
            <div className="flex items-center justify-between px-3 py-2 border-b bg-gray-50">
              <span className="text-sm font-medium truncate">{viewingPdfDoc.filename}</span>
              <Button 
                variant="ghost" 
                size="sm"
                onClick={closePdfViewer}
              >
                <X className="h-4 w-4" />
              </Button>
            </div>
            <div className="flex-1 min-h-0">
              {isLoadingPdf ? (
                <div className="flex items-center justify-center h-full">
                  <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                </div>
              ) : pdfUrl ? (
                <PDFViewer 
                  url={pdfUrl} 
                  className="h-full"
                />
              ) : (
                <div className="flex items-center justify-center h-full text-muted-foreground">
                  <AlertCircle className="h-6 w-6 mr-2" />
                  Failed to load PDF
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
