"use client";

import { useState, useEffect, useCallback } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
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
  Download,
  Upload,
} from "lucide-react";
import { 
  getMetadataForReview, 
  updateDocumentMetadata,
  getPDFUrl,
  downloadBibliography,
  type DocumentMetadataDetail,
  type MetadataUpdateRequest,
  type ExportFormat,
} from "@/lib/admin-api";
import { PDFViewer } from "@/components/pdf";
import { MetadataEditPanel } from "./metadata/MetadataEditPanel";
import { BibliographyImportDialog } from "./metadata/BibliographyImportDialog";
import { ITEM_TYPES } from "./metadata";

export function MetadataTab() {
  const [documents, setDocuments] = useState<DocumentMetadataDetail[]>([]);
  const [filterType, setFilterType] = useState<"all" | "needs_review" | "low_confidence">("needs_review");
  const [searchQuery, setSearchQuery] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [stats, setStats] = useState({ needsReview: 0, lowConfidence: 0, total: 0 });
  
  // Edit modal state
  const [editingDoc, setEditingDoc] = useState<DocumentMetadataDetail | null>(null);
  const [editForm, setEditForm] = useState<MetadataUpdateRequest>({});
  const [isSaving, setIsSaving] = useState(false);

  // PDF viewer state
  const [viewingPdfDoc, setViewingPdfDoc] = useState<DocumentMetadataDetail | null>(null);
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [isLoadingPdf, setIsLoadingPdf] = useState(false);

  // Import dialog state
  const [showImportDialog, setShowImportDialog] = useState(false);
  const [isExporting, setIsExporting] = useState(false);

  // Open PDF viewer for a document
  const openPdfViewer = async (doc: DocumentMetadataDetail) => {
    setIsLoadingPdf(true);
    setViewingPdfDoc(doc);
    try {
      const response = await getPDFUrl(doc.id);
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

  // Export bibliography
  const handleExport = async (format: ExportFormat) => {
    setIsExporting(true);
    try {
      await downloadBibliography(format);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Export failed");
    } finally {
      setIsExporting(false);
    }
  };

  // Fetch documents
  const fetchDocuments = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await getMetadataForReview({
        filter: filterType,  // "all", "needs_review", or "low_confidence"
      });
      setDocuments(response.documents);
      setStats({
        needsReview: response.needs_review_count,
        lowConfidence: response.low_confidence_count,
        total: response.total_count,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load documents");
    } finally {
      setIsLoading(false);
    }
  }, [filterType]);

  useEffect(() => {
    fetchDocuments();
  }, [fetchDocuments]);

  // Filter by search
  const filteredDocs = documents.filter(doc => 
    doc.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
    doc.id.toLowerCase().includes(searchQuery.toLowerCase())
  );

  // Open edit modal
  const openEditModal = (doc: DocumentMetadataDetail) => {
    setEditingDoc(doc);
    setEditForm({
      // Core fields
      title: doc.title,
      authors: doc.authors,
      year: doc.year,
      item_type: doc.item_type,
      // Identifiers
      doi: doc.doi,
      isbn: doc.isbn,
      issn: doc.issn,
      url: doc.url,
      // Publication
      publication: doc.publication || doc.journal,  // Fallback to journal for backward compat
      journal: doc.journal,
      volume: doc.volume,
      issue: doc.issue,
      pages: doc.pages,
      edition: doc.edition,
      // Publisher
      publisher: doc.publisher,
      place: doc.place,
      // Series
      series: doc.series,
      series_number: doc.series_number,
      // Book
      book_title: doc.book_title,
      num_pages: doc.num_pages,
      // Report/Thesis
      institution: doc.institution,
      report_number: doc.report_number,
      report_type: doc.report_type,
      thesis_type: doc.thesis_type,
      // Conference
      conference_name: doc.conference_name,
      proceedings_title: doc.proceedings_title,
      // Access
      accessed_date: doc.accessed_date,
      // Classification
      countries: doc.countries,
      sectors: doc.sectors,
      study_type: doc.study_type,
      intervention_type: doc.intervention_type,
    });
  };

  // Save changes
  const handleSave = async () => {
    if (!editingDoc) return;
    
    setIsSaving(true);
    try {
      await updateDocumentMetadata(editingDoc.id, {
        ...editForm,
        needs_review: false,
      });
      setEditingDoc(null);
      fetchDocuments();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save changes");
    } finally {
      setIsSaving(false);
    }
  };

  // Mark as reviewed (no changes)
  const markAsReviewed = async (docId: string) => {
    try {
      await updateDocumentMetadata(docId, { needs_review: false });
      fetchDocuments();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update");
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
      <div className="grid grid-cols-3 gap-4">
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
              Low Confidence
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-2">
              <AlertCircle className="h-5 w-5 text-red-500" />
              <span className="text-2xl font-bold">{stats.lowConfidence}</span>
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

      {/* Main Content: Side-by-side layout */}
      <div className="flex gap-4" style={{ height: 'calc(100vh - 280px)' }}>
        {/* Left Panel: Document List */}
        <Card className={editingDoc || viewingPdfDoc ? "w-1/3 flex flex-col" : "w-full"}>
          <CardHeader className="flex-shrink-0">
            <div className="flex items-center justify-between">
              <div>
                <CardTitle>Metadata Review</CardTitle>
                <CardDescription>
                  Review and correct document metadata for better search results
                </CardDescription>
              </div>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setShowImportDialog(true)}
                >
                  <Upload className="h-4 w-4 mr-2" />
                  Import
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => handleExport("bibtex")}
                  disabled={isExporting}
                >
                  {isExporting ? (
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  ) : (
                    <Download className="h-4 w-4 mr-2" />
                  )}
                  Export
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
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="pl-10"
                  />
                </div>
              </div>
              <Tabs value={filterType} onValueChange={(v) => setFilterType(v as typeof filterType)}>
                <TabsList>
                  <TabsTrigger value="needs_review">Needs Review</TabsTrigger>
                  <TabsTrigger value="low_confidence">Low Confidence</TabsTrigger>
                  <TabsTrigger value="all">All</TabsTrigger>
                </TabsList>
              </Tabs>
            </div>

            {error && (
              <div className="flex items-center gap-2 p-3 mb-4 text-red-600 bg-red-50 rounded-lg">
                <AlertCircle className="h-4 w-4" />
                {error}
              </div>
            )}

            {isLoading ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
              </div>
            ) : (
              <ScrollArea className="h-full">
                <div className="space-y-3 pr-2">
                  {filteredDocs.map((doc) => (
                    <Card 
                      key={doc.id} 
                      className={`hover:bg-muted/50 ${editingDoc?.id === doc.id ? 'ring-2 ring-primary' : ''} ${viewingPdfDoc?.id === doc.id ? 'ring-2 ring-blue-400' : ''}`}
                    >
                    <CardContent className="p-4">
                      <div className="space-y-3">
                        <div>
                          <div className="flex items-center gap-2 mb-1">
                            <h4 className="font-medium">{doc.title}</h4>
                            {doc.needs_review && (
                              <Badge variant="outline" className="text-yellow-600 border-yellow-500">
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
                            {doc.chunk_count} chunks indexed
                          </div>
                        </div>

                        <div className="flex gap-2 pt-2 border-t">
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={(e) => { e.stopPropagation(); openPdfViewer(doc); }}
                          >
                            <Eye className="h-4 w-4 mr-1" />
                            View PDF
                          </Button>
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={(e) => { e.stopPropagation(); openEditModal(doc); }}
                          >
                            <Edit2 className="h-4 w-4 mr-1" />
                            Edit Metadata
                          </Button>
                          {doc.needs_review && (
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={(e) => { e.stopPropagation(); markAsReviewed(doc.id); }}
                            >
                              <Check className="h-4 w-4 mr-1" />
                              Mark Reviewed
                            </Button>
                          )}
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                ))}

                {filteredDocs.length === 0 && (
                  <div className="text-center py-12 text-muted-foreground">
                    <CheckCircle className="h-12 w-12 mx-auto mb-3 text-green-500" />
                    <p>No documents need review!</p>
                  </div>
                )}
              </div>
            </ScrollArea>
          )}
        </CardContent>
      </Card>

        {/* Center Panel: Metadata Edit (side panel) */}
        {editingDoc && (
          <div className="w-1/3 h-full">
            <MetadataEditPanel
              document={editingDoc}
              editForm={editForm}
              setEditForm={setEditForm}
              onClose={() => setEditingDoc(null)}
              onSave={handleSave}
              onViewPdf={() => openPdfViewer(editingDoc)}
              isSaving={isSaving}
              isPdfOpen={viewingPdfDoc?.id === editingDoc.id}
            />
          </div>
        )}

        {/* Right Panel: PDF Viewer (Side Panel) */}
        {viewingPdfDoc && (
          <div className="w-1/3 flex flex-col border rounded-lg overflow-hidden bg-white h-full">
            {/* Minimal header with just close button */}
            <div className="flex items-center justify-between px-3 py-2 border-b bg-gray-50">
              <span className="text-sm font-medium truncate">{viewingPdfDoc.filename}</span>
              <Button 
                variant="ghost" 
                size="sm"
                onClick={closePdfViewer}
                title="Close PDF"
              >
                <X className="h-4 w-4" />
              </Button>
            </div>
            {/* PDF takes full remaining height */}
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

      {/* Import Dialog */}
      <BibliographyImportDialog
        open={showImportDialog}
        onOpenChange={setShowImportDialog}
        onImportComplete={fetchDocuments}
      />
    </div>
  );
}
