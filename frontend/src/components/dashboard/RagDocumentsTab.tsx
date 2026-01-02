"use client";

import { useState, useEffect, useCallback } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import { ScrollArea } from "@/components/ui/scroll-area";
import { 
  FileText, 
  Search,
  Trash2,
  Download,
  Eye,
  RefreshCw,
  CheckCircle,
  Hash,
  Loader2,
  AlertCircle,
  Clock,
} from "lucide-react";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface Document {
  id: string;
  filename: string;
  original_filename: string;
  title?: string;
  authors?: string[];
  year?: number;
  doi?: string;
  status: "pending" | "processing" | "completed" | "failed";
  error_message: string | null;
  chunk_count: number;
  created_at: string;
  processed_at: string | null;
}

interface RagDocumentsTabProps {
  ragId: string;
  accessToken: string;
  onDocumentsChanged?: () => void;
}

export function RagDocumentsTab({ ragId, accessToken, onDocumentsChanged }: RagDocumentsTabProps) {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedDocs, setSelectedDocs] = useState<Set<string>>(new Set());
  const [isLoading, setIsLoading] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Fetch documents
  const fetchDocuments = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE_URL}/rags/${ragId}/documents`, {
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (!response.ok) throw new Error("Failed to fetch documents");
      const data = await response.json();
      setDocuments(data.documents || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load documents");
    } finally {
      setIsLoading(false);
    }
  }, [ragId, accessToken]);

  useEffect(() => {
    fetchDocuments();
  }, [fetchDocuments]);

  // Filter documents
  const filteredDocs = documents.filter(doc => {
    const query = searchQuery.toLowerCase();
    return (
      doc.original_filename.toLowerCase().includes(query) ||
      doc.filename.toLowerCase().includes(query) ||
      (doc.title && doc.title.toLowerCase().includes(query)) ||
      (doc.authors && doc.authors.some(a => a.toLowerCase().includes(query)))
    );
  });

  // Toggle selection
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

  // Select all
  const selectAll = () => {
    if (selectedDocs.size === filteredDocs.length) {
      setSelectedDocs(new Set());
    } else {
      setSelectedDocs(new Set(filteredDocs.map(d => d.id)));
    }
  };

  // Delete document
  const deleteDocument = async (docId: string) => {
    try {
      const response = await fetch(`${API_BASE_URL}/rags/${ragId}/documents/${docId}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (!response.ok) throw new Error("Failed to delete document");
      await fetchDocuments();
      onDocumentsChanged?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete document");
    }
  };

  // Delete selected
  const deleteSelected = async () => {
    if (!confirm(`Delete ${selectedDocs.size} document(s)? This cannot be undone.`)) return;
    
    setIsDeleting(true);
    try {
      for (const docId of selectedDocs) {
        await fetch(`${API_BASE_URL}/rags/${ragId}/documents/${docId}`, {
          method: "DELETE",
          headers: { Authorization: `Bearer ${accessToken}` },
        });
      }
      setSelectedDocs(new Set());
      await fetchDocuments();
      onDocumentsChanged?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete documents");
    } finally {
      setIsDeleting(false);
    }
  };

  // Export as CSV
  const exportDocuments = () => {
    const headers = ["Filename", "Title", "Authors", "Year", "Status", "Chunks", "Created"];
    const rows = documents.map(d => [
      d.original_filename,
      d.title || "",
      d.authors?.join("; ") || "",
      d.year || "",
      d.status,
      d.chunk_count,
      formatDate(d.created_at),
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

  // Stats
  const completedCount = documents.filter(d => d.status === "completed").length;
  const pendingCount = documents.filter(d => d.status === "pending").length;
  const failedCount = documents.filter(d => d.status === "failed").length;
  const totalChunks = documents.reduce((sum, d) => sum + d.chunk_count, 0);

  const getStatusIcon = (status: string) => {
    switch (status) {
      case "completed": return <CheckCircle className="h-4 w-4 text-green-500" />;
      case "processing": return <Loader2 className="h-4 w-4 text-blue-500 animate-spin" />;
      case "failed": return <AlertCircle className="h-4 w-4 text-red-500" />;
      default: return <Clock className="h-4 w-4 text-muted-foreground" />;
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case "completed": return <Badge className="bg-green-500">Completed</Badge>;
      case "processing": return <Badge className="bg-blue-500">Processing</Badge>;
      case "failed": return <Badge variant="destructive">Failed</Badge>;
      default: return <Badge variant="secondary">Pending</Badge>;
    }
  };

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

      {/* Stats Cards */}
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
                <p className="text-sm text-muted-foreground">Completed</p>
                <p className="text-2xl font-bold">{completedCount}</p>
              </div>
              <CheckCircle className="h-8 w-8 text-green-500" />
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Pending</p>
                <p className="text-2xl font-bold">{pendingCount}</p>
              </div>
              <Clock className="h-8 w-8 text-muted-foreground" />
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
                Documents
              </CardTitle>
              <CardDescription>
                Manage documents in this knowledge base
              </CardDescription>
            </div>
            <div className="flex items-center gap-2">
              <Button variant="outline" size="sm" onClick={fetchDocuments} disabled={isLoading}>
                <RefreshCw className={`h-4 w-4 mr-1 ${isLoading ? "animate-spin" : ""}`} />
                Refresh
              </Button>
              <Button variant="outline" size="sm" onClick={exportDocuments}>
                <Download className="h-4 w-4 mr-1" />
                Export CSV
              </Button>
            </div>
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
                  variant="destructive"
                  size="sm"
                  onClick={deleteSelected}
                  disabled={isDeleting}
                >
                  {isDeleting ? (
                    <Loader2 className="h-4 w-4 mr-1 animate-spin" />
                  ) : (
                    <Trash2 className="h-4 w-4 mr-1" />
                  )}
                  Delete Selected
                </Button>
              </div>
            )}
          </div>
        </CardHeader>
        <CardContent>
          {documents.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">
              <FileText className="h-10 w-10 mx-auto mb-2 opacity-50" />
              <p className="text-sm">No documents yet</p>
              <p className="text-xs mt-1">Upload PDFs to get started</p>
            </div>
          ) : (
            <ScrollArea className="h-[400px]">
              <div className="space-y-2">
                {/* Header Row */}
                <div className="flex items-center gap-3 p-2 bg-muted/50 rounded-lg text-sm font-medium">
                  <Checkbox
                    checked={selectedDocs.size === filteredDocs.length && filteredDocs.length > 0}
                    onCheckedChange={selectAll}
                  />
                  <span className="flex-1">Document</span>
                  <span className="w-24 text-center">Status</span>
                  <span className="w-20 text-center">Chunks</span>
                  <span className="w-24 text-center">Date</span>
                  <span className="w-10"></span>
                </div>
                
                {/* Document Rows */}
                {filteredDocs.map(doc => (
                  <div
                    key={doc.id}
                    className={`flex items-center gap-3 p-3 rounded-lg border transition-colors ${
                      selectedDocs.has(doc.id) ? "bg-primary/5 border-primary/20" : "hover:bg-muted/50"
                    }`}
                  >
                    <Checkbox
                      checked={selectedDocs.has(doc.id)}
                      onCheckedChange={() => toggleSelect(doc.id)}
                    />
                    <div className="flex-1 min-w-0">
                      <p className="font-medium truncate">
                        {doc.title || doc.original_filename}
                      </p>
                      {doc.title && (
                        <p className="text-xs text-muted-foreground truncate">
                          {doc.original_filename}
                        </p>
                      )}
                      {doc.authors && doc.authors.length > 0 && (
                        <p className="text-xs text-muted-foreground truncate">
                          {doc.authors.slice(0, 2).join(", ")}{doc.authors.length > 2 ? ` +${doc.authors.length - 2}` : ""}
                          {doc.year && ` (${doc.year})`}
                        </p>
                      )}
                    </div>
                    <div className="w-24 flex justify-center">
                      {getStatusBadge(doc.status)}
                    </div>
                    <div className="w-20 text-center text-sm text-muted-foreground">
                      {doc.chunk_count}
                    </div>
                    <div className="w-24 text-center text-xs text-muted-foreground">
                      {formatDate(doc.created_at)}
                    </div>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8"
                      onClick={() => deleteDocument(doc.id)}
                    >
                      <Trash2 className="h-4 w-4 text-destructive" />
                    </Button>
                  </div>
                ))}
              </div>
            </ScrollArea>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
