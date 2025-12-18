"use client";

import { useState } from "react";
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
  Hash
} from "lucide-react";

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

// Mock data - replace with API calls
const mockDocuments: Document[] = [
  {
    id: "1",
    title: "The Impact of Cash Transfers on Educational Outcomes in Kenya",
    filename: "cash_transfers_kenya_2023.pdf",
    authors: ["Smith, J.", "Ochieng, M.", "Johnson, L."],
    year: 2023,
    status: "indexed",
    pageCount: 45,
    chunkCount: 234,
    uploadedAt: new Date(Date.now() - 86400000 * 3).toISOString(),
    processedAt: new Date(Date.now() - 86400000 * 3 + 3600000).toISOString(),
  },
  {
    id: "2",
    title: "Systematic Review of Health Interventions in South Asia",
    filename: "health_interventions_sa.pdf",
    authors: ["Patel, R.", "Kumar, A."],
    year: 2022,
    status: "indexed",
    pageCount: 128,
    chunkCount: 567,
    uploadedAt: new Date(Date.now() - 86400000 * 7).toISOString(),
    processedAt: new Date(Date.now() - 86400000 * 7 + 7200000).toISOString(),
  },
  {
    id: "3",
    title: "Agricultural Productivity Programs: A Meta-Analysis",
    filename: "agriculture_meta_2024.pdf",
    authors: ["Chen, W.", "Müller, H.", "Santos, P."],
    year: 2024,
    status: "indexed",
    pageCount: 67,
    chunkCount: 312,
    uploadedAt: new Date(Date.now() - 86400000).toISOString(),
    processedAt: new Date(Date.now() - 86400000 + 1800000).toISOString(),
  },
  {
    id: "4",
    title: "Water and Sanitation RCT Results",
    filename: "wash_rct_results.pdf",
    authors: ["Brown, A."],
    year: 2021,
    status: "pending",
    pageCount: 32,
    chunkCount: 0,
    uploadedAt: new Date(Date.now() - 3600000).toISOString(),
  },
];

export function DocumentsTab() {
  const [documents, setDocuments] = useState<Document[]>(mockDocuments);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedDocs, setSelectedDocs] = useState<Set<string>>(new Set());

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
    // TODO: Implement delete API call
    console.log("Deleting:", Array.from(selectedDocs));
    setDocuments(prev => prev.filter(d => !selectedDocs.has(d.id)));
    setSelectedDocs(new Set());
  };

  const reprocessSelected = async () => {
    // TODO: Implement reprocess API call
    console.log("Reprocessing:", Array.from(selectedDocs));
  };

  const exportDocuments = async () => {
    // TODO: Implement export functionality
    console.log("Exporting documents metadata...");
  };

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleDateString("en-US", {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  };

  const totalChunks = documents.reduce((sum, d) => sum + d.chunkCount, 0);
  const totalPages = documents.reduce((sum, d) => sum + d.pageCount, 0);
  const indexedCount = documents.filter(d => d.status === "indexed").length;

  return (
    <div className="space-y-6">
      {/* Stats */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Total Documents</p>
                <p className="text-2xl font-bold">{documents.length}</p>
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
                <p className="text-sm text-muted-foreground">Total Pages</p>
                <p className="text-2xl font-bold">{totalPages.toLocaleString()}</p>
              </div>
              <FileText className="h-8 w-8 text-muted-foreground" />
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
                  <th className="p-2 w-24 text-right">Pages</th>
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
                        <p className="font-medium line-clamp-1">{doc.title}</p>
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
                    <td className="p-2 text-right text-sm">{doc.pageCount}</td>
                    <td className="p-2 text-right text-sm">{doc.chunkCount}</td>
                    <td className="p-2 text-sm text-muted-foreground">
                      {formatDate(doc.uploadedAt)}
                    </td>
                    <td className="p-2">
                      <div className="flex items-center gap-1">
                        <Button variant="ghost" size="icon" className="h-8 w-8">
                          <Eye className="h-4 w-4" />
                        </Button>
                        <Button variant="ghost" size="icon" className="h-8 w-8">
                          <Download className="h-4 w-4" />
                        </Button>
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
