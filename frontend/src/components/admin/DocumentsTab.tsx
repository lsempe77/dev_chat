"use client";

import { useState, useEffect, useCallback } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { 
  FileText, 
  Search,
  Trash2,
  Download,
  Eye,
  RefreshCw,
  CheckCircle,
  Calendar,
  User,
  Hash,
  Loader2,
  AlertCircle,
  BookOpen,
  FileQuestion
} from "lucide-react";
import { 
  getDocuments, 
  deleteDocument, 
  reprocessDocument,
  getPDFUrl,
  type DocumentMetadata 
} from "@/lib/admin-api";

interface Document {
  id: string;
  title: string;
  filename: string;
  authors: string[];
  year?: number;
  status: "indexed" | "pending" | "error";
  pageCount: number;
  chunkCount: number;
  uploadedAt: string;
  processedAt?: string;
}

export function DocumentsTab() {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedDocs, setSelectedDocs] = useState<Set<string>>(new Set());
  const [isLoading, setIsLoading] = useState(true);
  const [isDeleting, setIsDeleting] = useState(false);
  const [isReprocessing, setIsReprocessing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [totalChunks, setTotalChunks] = useState(0);

  // Fetch documents from API
  const fetchDocuments = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await getDocuments({ search: searchQuery || undefined });
      // Map API response to component format
      const docs: Document[] = response.documents.map(d => ({
        id: d.id,
        title: d.title,
        filename: d.filename,
        authors: d.authors,
        year: d.year,
        status: d.status,
        pageCount: d.page_count,
        chunkCount: d.chunk_count,
        uploadedAt: d.uploaded_at,
        processedAt: d.processed_at,
      }));
      setDocuments(docs);
      setTotalChunks(response.total_chunks);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load documents");
    } finally {
      setIsLoading(false);
    }
  }, [searchQuery]);

  // Initial load
  useEffect(() => {
    fetchDocuments();
  }, [fetchDocuments]);

  const filteredDocs = documents.filter(doc => 
    doc.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
    doc.filename.toLowerCase().includes(searchQuery.toLowerCase()) ||
    doc.authors.some(a => a.toLowerCase().includes(searchQuery.toLowerCase()))
  );

  const toggleSelect = (id: string) => {
    setSelectedDocs(prev => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const selectAll = () => {
    if (selectedDocs.size === filteredDocs.length) {
      setSelectedDocs(new Set());
    } else {
      setSelectedDocs(new Set(filteredDocs.map(d => d.id)));
    }
  };

  const deleteSelected = async () => {
    if (!confirm(`Delete ${selectedDocs.size} document(s)? This cannot be undone.`)) {
      return;
    }
    
    setIsDeleting(true);
    try {
      // Delete all selected documents
      for (const docId of selectedDocs) {
        await deleteDocument(docId);
      }
      // Refresh the list
      await fetchDocuments();
      setSelectedDocs(new Set());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete documents");
    } finally {
      setIsDeleting(false);
    }
  };

  const reprocessSelected = async () => {
    setIsReprocessing(true);
    try {
      for (const docId of selectedDocs) {
        await reprocessDocument(docId);
      }
      // Refresh the list
      await fetchDocuments();
      setSelectedDocs(new Set());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to reprocess documents");
    } finally {
      setIsReprocessing(false);
    }
  };

  const exportDocuments = async () => {
    // Export as CSV
    const headers = ["Title", "Filename", "Authors", "Year", "Status", "Pages", "Chunks", "Uploaded"];
    const rows = documents.map(d => [
      d.title,
      d.filename,
      d.authors.join("; "),
      d.year || "",
      d.status,
      d.pageCount,
      d.chunkCount,
      formatDate(d.uploadedAt),
    ]);
    
    const csv = [headers.join(","), ...rows.map(r => r.map(c => `"${c}"`).join(","))].join("\n");
    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `documents_${new Date().toISOString().split("T")[0]}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleDateString("en-US", {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  };

  const indexedCount = documents.filter(d => d.status === "indexed").length;

  return (
    <div className="space-y-6">
      {/* Error Banner */}
      {error && (
        <div className="bg-destructive/10 border border-destructive/20 text-destructive px-4 py-3 rounded-lg flex items-center gap-2">
          <AlertCircle className="h-4 w-4" />
          <span>{error}</span>
          <Button variant="ghost" size="sm" onClick={() => setError(null)} className="ml-auto">
            Dismiss
          </Button>
        </div>
      )}
      
      {/* Stats */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Total Documents</p>
                <p className="text-2xl font-bold">
                  {isLoading ? <Loader2 className="h-6 w-6 animate-spin" /> : documents.length}
                </p>
              </div>
              <FileText className="h-8 w-8 text-muted-foreground" />
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Indexed</p>
                <p className="text-2xl font-bold">{indexedCount}</p>
              </div>
              <CheckCircle className="h-8 w-8 text-green-500" />
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Vector Chunks</p>
                <p className="text-2xl font-bold">{totalChunks.toLocaleString()}</p>
              </div>
              <Hash className="h-8 w-8 text-muted-foreground" />
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Documents Table */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="flex items-center gap-2">
                <FileText className="h-5 w-5" />
                Indexed Documents
              </CardTitle>
              <CardDescription>
                Manage documents in the knowledge base
              </CardDescription>
            </div>
            <Button variant="outline" size="sm" onClick={exportDocuments}>
              <Download className="h-4 w-4 mr-1" />
              Export CSV
            </Button>
          </div>
          
          {/* Search and Actions */}
          <div className="flex items-center gap-4 pt-4">
            <div className="relative flex-1 max-w-sm">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="Search documents..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-9"
              />
            </div>
            {selectedDocs.size > 0 && (
              <div className="flex items-center gap-2">
                <span className="text-sm text-muted-foreground">
                  {selectedDocs.size} selected
                </span>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={reprocessSelected}
                >
                  <RefreshCw className="h-4 w-4 mr-1" />
                  Reprocess
                </Button>
                <Button
                  variant="destructive"
                  size="sm"
                  onClick={deleteSelected}
                >
                  <Trash2 className="h-4 w-4 mr-1" />
                  Delete
                </Button>
              </div>
            )}
          </div>
        </CardHeader>
        <CardContent>
          <ScrollArea className="h-[500px]">
            <table className="w-full">
              <thead className="sticky top-0 bg-background border-b">
                <tr className="text-left text-sm text-muted-foreground">
                  <th className="p-2 w-8">
                    <input
                      type="checkbox"
                      checked={selectedDocs.size === filteredDocs.length && filteredDocs.length > 0}
                      onChange={selectAll}
                      className="rounded"
                    />
                  </th>
                  <th className="p-2">Document</th>
                  <th className="p-2 w-24">Year</th>
                  <th className="p-2 w-24">Status</th>
                  <th className="p-2 w-24 text-right">Chunks</th>
                  <th className="p-2 w-32">Uploaded</th>
                  <th className="p-2 w-20"></th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {filteredDocs.map((doc) => (
                  <tr 
                    key={doc.id}
                    className={`hover:bg-muted/50 ${selectedDocs.has(doc.id) ? "bg-muted/30" : ""}`}
                  >
                    <td className="p-2">
                      <input
                        type="checkbox"
                        checked={selectedDocs.has(doc.id)}
                        onChange={() => toggleSelect(doc.id)}
                        className="rounded"
                      />
                    </td>
                    <td className="p-2">
                      <div>
                        <div className="flex items-center gap-2">
                          <p className="font-medium line-clamp-1">{doc.title}</p>
                          {doc.filename.startsWith("imported_") && doc.chunkCount === 0 && (
                            <Badge variant="outline" className="shrink-0 text-xs text-blue-600 border-blue-300 bg-blue-50">
                              <BookOpen className="h-3 w-3 mr-1" />
                              Metadata Only
                            </Badge>
                          )}
                          {!doc.filename.startsWith("imported_") && doc.chunkCount === 0 && doc.status === "pending" && (
                            <Badge variant="outline" className="shrink-0 text-xs text-orange-600 border-orange-300 bg-orange-50">
                              <FileQuestion className="h-3 w-3 mr-1" />
                              Processing
                            </Badge>
                          )}
                        </div>
                        <div className="flex items-center gap-2 text-xs text-muted-foreground mt-0.5">
                          <User className="h-3 w-3" />
                          <span className="line-clamp-1">
                            {doc.authors.join(", ")}
                          </span>
                        </div>
                      </div>
                    </td>
                    <td className="p-2">
                      {doc.year && (
                        <div className="flex items-center gap-1 text-sm">
                          <Calendar className="h-3 w-3 text-muted-foreground" />
                          {doc.year}
                        </div>
                      )}
                    </td>
                    <td className="p-2">
                      {doc.status === "indexed" ? (
                        <Badge className="bg-green-500">Indexed</Badge>
                      ) : doc.status === "pending" ? (
                        <Badge variant="secondary">Pending</Badge>
                      ) : (
                        <Badge variant="destructive">Error</Badge>
                      )}
                    </td>
                    <td className="p-2 text-right text-sm">{doc.chunkCount}</td>
                    <td className="p-2 text-sm text-muted-foreground">
                      {formatDate(doc.uploadedAt)}
                    </td>
                    <td className="p-2">
                      <div className="flex items-center gap-1">
                        {/* Only show PDF buttons if there's a real PDF (not imported metadata) */}
                        {!doc.filename.startsWith("imported_") ? (
                          <>
                            <Button 
                              variant="ghost" 
                              size="icon" 
                              className="h-8 w-8"
                              title="View PDF"
                              onClick={async () => {
                                try {
                                  const response = await getPDFUrl(doc.id);
                                  window.open(response.url, '_blank');
                                } catch (err) {
                                  setError(err instanceof Error ? err.message : "Failed to load PDF");
                                }
                              }}
                            >
                              <Eye className="h-4 w-4" />
                            </Button>
                            <Button 
                              variant="ghost" 
                              size="icon" 
                              className="h-8 w-8"
                              title="Download PDF"
                              onClick={async () => {
                                try {
                                  const response = await getPDFUrl(doc.id);
                                  const a = document.createElement('a');
                                  a.href = response.url;
                                  a.download = doc.filename || `${doc.id}.pdf`;
                                  a.target = '_blank';
                                  a.click();
                                } catch (err) {
                                  setError(err instanceof Error ? err.message : "Failed to download PDF");
                                }
                              }}
                            >
                              <Download className="h-4 w-4" />
                            </Button>
                          </>
                        ) : (
                          <span className="text-xs text-muted-foreground italic px-2">No PDF</span>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            
            {filteredDocs.length === 0 && (
              <div className="text-center py-8 text-muted-foreground">
                <FileText className="h-10 w-10 mx-auto mb-2 opacity-50" />
                <p className="text-sm">
                  {searchQuery ? "No documents match your search" : "No documents indexed yet"}
                </p>
              </div>
            )}
          </ScrollArea>
        </CardContent>
      </Card>
    </div>
  );
}
