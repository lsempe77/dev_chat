"use client";

import { useState, useEffect, useCallback } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { 
  FileText, 
  Search,
  Edit2,
  Check,
  X,
  AlertCircle,
  CheckCircle,
  Loader2,
  ExternalLink,
  RefreshCw,
  Globe,
  Building,
  BookOpen,
  Beaker,
  Tag,
  Eye,
} from "lucide-react";
import { 
  getMetadataForReview, 
  getDocumentMetadata,
  updateDocumentMetadata,
  getPDFUrl,
  type DocumentMetadataDetail,
  type MetadataUpdateRequest,
} from "@/lib/admin-api";
import { PDFViewer } from "@/components/pdf";

const STUDY_TYPES = [
  "RCT",
  "quasi-experimental",
  "systematic-review",
  "meta-analysis",
  "observational",
  "qualitative",
  "mixed-methods",
  "other",
];

const SECTORS = [
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
];

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

  // Fetch documents
  const fetchDocuments = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await getMetadataForReview({
        filter: filterType === "all" ? undefined : filterType,
        limit: 100,
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
      title: doc.title,
      authors: doc.authors,
      year: doc.year,
      doi: doc.doi,
      journal: doc.journal,
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
      <div className="flex gap-4">
        {/* Left Panel: Document List */}
        <Card className={viewingPdfDoc ? "w-1/2" : "w-full"}>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle>Metadata Review</CardTitle>
                <CardDescription>
                  Review and correct document metadata for better search results
                </CardDescription>
              </div>
              <Button variant="outline" size="sm" onClick={fetchDocuments}>
                <RefreshCw className="h-4 w-4 mr-2" />
                Refresh
              </Button>
            </div>
          </CardHeader>
          <CardContent>
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
              <ScrollArea className={viewingPdfDoc ? "h-[600px]" : "h-[500px]"}>
                <div className="space-y-3">
                  {filteredDocs.map((doc) => (
                    <Card 
                      key={doc.id} 
                      className={`hover:bg-muted/50 cursor-pointer ${viewingPdfDoc?.id === doc.id ? 'ring-2 ring-primary' : ''}`}
                      onClick={() => openEditModal(doc)}
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

        {/* Right Panel: PDF Viewer (Side Panel) */}
        {viewingPdfDoc && (
          <div className="w-1/2 flex flex-col border rounded-lg overflow-hidden bg-white">
            {/* Minimal header with just close button */}
            <div className="flex items-center justify-between px-3 py-2 border-b bg-gray-50">
              <div className="flex items-center gap-2">
                <Button 
                  variant="outline" 
                  size="sm"
                  onClick={() => openEditModal(viewingPdfDoc)}
                  title="Edit metadata"
                >
                  <Edit2 className="h-4 w-4" />
                </Button>
              </div>
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
            <div className="flex-1 min-h-0" style={{ height: 'calc(100vh - 280px)' }}>
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

      {/* Edit Modal */}
      <Dialog open={!!editingDoc} onOpenChange={(open) => !open && setEditingDoc(null)}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Edit Document Metadata</DialogTitle>
            <DialogDescription>
              Update metadata fields for: {editingDoc?.filename}
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-4 py-4">
            <div className="grid grid-cols-4 items-center gap-4">
              <Label className="text-right">Title</Label>
              <Input
                className="col-span-3"
                value={editForm.title || ""}
                onChange={(e) => setEditForm({ ...editForm, title: e.target.value })}
              />
            </div>

            <div className="grid grid-cols-4 items-center gap-4">
              <Label className="text-right">Authors</Label>
              <Input
                className="col-span-3"
                value={editForm.authors?.join(", ") || ""}
                onChange={(e) => setEditForm({ 
                  ...editForm, 
                  authors: e.target.value.split(",").map(a => a.trim()).filter(Boolean) 
                })}
                placeholder="Comma-separated names"
              />
            </div>

            <div className="grid grid-cols-4 items-center gap-4">
              <Label className="text-right">Year</Label>
              <Input
                className="col-span-3"
                type="number"
                value={editForm.year || ""}
                onChange={(e) => setEditForm({ ...editForm, year: parseInt(e.target.value) || undefined })}
              />
            </div>

            <div className="grid grid-cols-4 items-center gap-4">
              <Label className="text-right">DOI</Label>
              <Input
                className="col-span-3"
                value={editForm.doi || ""}
                onChange={(e) => setEditForm({ ...editForm, doi: e.target.value })}
                placeholder="10.xxxx/yyyy"
              />
            </div>

            <div className="grid grid-cols-4 items-center gap-4">
              <Label className="text-right">Journal</Label>
              <Input
                className="col-span-3"
                value={editForm.journal || ""}
                onChange={(e) => setEditForm({ ...editForm, journal: e.target.value })}
              />
            </div>

            <div className="grid grid-cols-4 items-center gap-4">
              <Label className="text-right">Countries</Label>
              <Input
                className="col-span-3"
                value={editForm.countries?.join(", ") || ""}
                onChange={(e) => setEditForm({ 
                  ...editForm, 
                  countries: e.target.value.split(",").map(c => c.trim()).filter(Boolean) 
                })}
                placeholder="Comma-separated countries"
              />
            </div>

            <div className="grid grid-cols-4 items-center gap-4">
              <Label className="text-right">Sectors</Label>
              <div className="col-span-3 flex flex-wrap gap-2">
                {SECTORS.map((sector) => (
                  <Badge
                    key={sector}
                    variant={editForm.sectors?.includes(sector) ? "default" : "outline"}
                    className="cursor-pointer"
                    onClick={() => {
                      const current = editForm.sectors || [];
                      if (current.includes(sector)) {
                        setEditForm({ ...editForm, sectors: current.filter(s => s !== sector) });
                      } else {
                        setEditForm({ ...editForm, sectors: [...current, sector] });
                      }
                    }}
                  >
                    {sector}
                  </Badge>
                ))}
              </div>
            </div>

            <div className="grid grid-cols-4 items-center gap-4">
              <Label className="text-right">Study Type</Label>
              <Select
                value={editForm.study_type || ""}
                onValueChange={(value) => setEditForm({ ...editForm, study_type: value })}
              >
                <SelectTrigger className="col-span-3">
                  <SelectValue placeholder="Select study type" />
                </SelectTrigger>
                <SelectContent>
                  {STUDY_TYPES.map((type) => (
                    <SelectItem key={type} value={type}>
                      {type}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="grid grid-cols-4 items-center gap-4">
              <Label className="text-right">Intervention</Label>
              <Input
                className="col-span-3"
                value={editForm.intervention_type || ""}
                onChange={(e) => setEditForm({ ...editForm, intervention_type: e.target.value })}
                placeholder="e.g., cash transfer, training program"
              />
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setEditingDoc(null)}>
              Cancel
            </Button>
            <Button onClick={handleSave} disabled={isSaving}>
              {isSaving ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Saving...
                </>
              ) : (
                <>
                  <Check className="h-4 w-4 mr-2" />
                  Save Changes
                </>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
