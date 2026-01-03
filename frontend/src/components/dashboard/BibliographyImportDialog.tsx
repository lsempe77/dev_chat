"use client";

import { useState, useCallback, useRef } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Upload,
  FileText,
  CheckCircle,
  AlertCircle,
  Loader2,
  Link2,
  X,
  FileUp,
  BookOpen,
} from "lucide-react";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface BibliographyMatchResult {
  entry_id: string;
  entry_title: string;
  entry_authors: string | null;
  entry_year: number | null;
  document_id: string | null;
  document_filename: string | null;
  confidence: number;
  match_method: string;
  match_details: string;
}

interface Document {
  id: string;
  filename: string;
  original_filename: string;
  title?: string;
}

interface BibliographyImportDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  ragId: string;
  accessToken: string;
  documents: Document[];
  onImportComplete?: () => void;
}

type ImportState = "upload" | "preview" | "applying";

export function BibliographyImportDialog({
  open,
  onOpenChange,
  ragId,
  accessToken,
  documents,
  onImportComplete,
}: BibliographyImportDialogProps) {
  const [state, setState] = useState<ImportState>("upload");
  const [isUploading, setIsUploading] = useState(false);
  const [isApplying, setIsApplying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fileName, setFileName] = useState<string | null>(null);
  const [dragActive, setDragActive] = useState(false);
  
  // Import results
  const [matched, setMatched] = useState<BibliographyMatchResult[]>([]);
  const [unmatched, setUnmatched] = useState<BibliographyMatchResult[]>([]);
  const [totalEntries, setTotalEntries] = useState(0);
  
  // Manual match selections: entry_id -> document_id
  const [manualMatches, setManualMatches] = useState<Record<string, string>>({});
  
  // Which matched entries to apply (by entry_id)
  const [selectedForApply, setSelectedForApply] = useState<Set<string>>(new Set());
  
  const fileInputRef = useRef<HTMLInputElement>(null);

  const reset = useCallback(() => {
    setState("upload");
    setError(null);
    setFileName(null);
    setMatched([]);
    setUnmatched([]);
    setTotalEntries(0);
    setManualMatches({});
    setSelectedForApply(new Set());
  }, []);

  const handleClose = useCallback(() => {
    reset();
    onOpenChange(false);
  }, [reset, onOpenChange]);

  const handleFileUpload = useCallback(async (file: File) => {
    const validExtensions = [".ris", ".bib", ".csv", ".txt"];
    const ext = file.name.toLowerCase().slice(file.name.lastIndexOf("."));
    
    if (!validExtensions.includes(ext)) {
      setError(`Unsupported file type. Allowed: ${validExtensions.join(", ")}`);
      return;
    }
    
    setIsUploading(true);
    setError(null);
    setFileName(file.name);
    
    try {
      const formData = new FormData();
      formData.append("file", file);
      
      const response = await fetch(
        `${API_BASE_URL}/rags/${ragId}/documents/import-bibliography`,
        {
          method: "POST",
          headers: { Authorization: `Bearer ${accessToken}` },
          body: formData,
        }
      );
      
      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || "Import failed");
      }
      
      const data = await response.json();
      
      setTotalEntries(data.total_entries);
      setMatched(data.matched || []);
      setUnmatched(data.unmatched || []);
      
      // Pre-select all matched entries for apply
      const matchedEntries = (data.matched || []) as BibliographyMatchResult[];
      const entryIds = matchedEntries
        .filter((m) => m.confidence >= 0.8)
        .map((m) => m.entry_id);
      setSelectedForApply(new Set(entryIds));
      
      setState("preview");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Import failed");
    } finally {
      setIsUploading(false);
    }
  }, [ragId, accessToken]);

  const handleDrag = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFileUpload(e.dataTransfer.files[0]);
    }
  }, [handleFileUpload]);

  const handleFileSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      handleFileUpload(e.target.files[0]);
    }
  }, [handleFileUpload]);

  const toggleSelectForApply = useCallback((entryId: string) => {
    setSelectedForApply((prev) => {
      const next = new Set(prev);
      if (next.has(entryId)) {
        next.delete(entryId);
      } else {
        next.add(entryId);
      }
      return next;
    });
  }, []);

  const handleManualMatch = useCallback((entryId: string, documentId: string) => {
    setManualMatches((prev) => ({ ...prev, [entryId]: documentId }));
    // Auto-select for apply
    setSelectedForApply((prev) => {
      const next = new Set(prev);
      next.add(entryId);
      return next;
    });
  }, []);

  const handleApplyMatches = useCallback(async () => {
    setIsApplying(true);
    setState("applying");
    setError(null);
    
    let applied = 0;
    let failed = 0;
    
    try {
      // Apply auto-matched entries that are selected
      for (const entry of matched) {
        if (!selectedForApply.has(entry.entry_id)) continue;
        if (!entry.document_id) continue;
        
        try {
          const response = await fetch(
            `${API_BASE_URL}/rags/${ragId}/documents/apply-match`,
            {
              method: "POST",
              headers: {
                "Content-Type": "application/json",
                Authorization: `Bearer ${accessToken}`,
              },
              body: JSON.stringify({
                entry_data: {
                  id: entry.entry_id,
                  title: entry.entry_title,
                  authors: entry.entry_authors,
                  year: entry.entry_year,
                },
                document_id: entry.document_id,
              }),
            }
          );
          
          if (response.ok) {
            applied++;
          } else {
            failed++;
          }
        } catch {
          failed++;
        }
      }
      
      // Apply manual matches for unmatched entries
      for (const entry of unmatched) {
        const docId = manualMatches[entry.entry_id];
        if (!docId || !selectedForApply.has(entry.entry_id)) continue;
        
        try {
          const response = await fetch(
            `${API_BASE_URL}/rags/${ragId}/documents/apply-match`,
            {
              method: "POST",
              headers: {
                "Content-Type": "application/json",
                Authorization: `Bearer ${accessToken}`,
              },
              body: JSON.stringify({
                entry_data: {
                  id: entry.entry_id,
                  title: entry.entry_title,
                  authors: entry.entry_authors,
                  year: entry.entry_year,
                },
                document_id: docId,
              }),
            }
          );
          
          if (response.ok) {
            applied++;
          } else {
            failed++;
          }
        } catch {
          failed++;
        }
      }
      
      if (applied > 0) {
        onImportComplete?.();
      }
      
      handleClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Apply failed");
      setState("preview");
    } finally {
      setIsApplying(false);
    }
  }, [matched, unmatched, selectedForApply, manualMatches, ragId, accessToken, handleClose, onImportComplete]);

  const getConfidenceBadge = (confidence: number, method: string) => {
    if (confidence >= 0.9) {
      return <Badge className="bg-green-500 text-xs">{Math.round(confidence * 100)}% ({method})</Badge>;
    } else if (confidence >= 0.7) {
      return <Badge className="bg-yellow-500 text-xs">{Math.round(confidence * 100)}% ({method})</Badge>;
    } else {
      return <Badge variant="secondary" className="text-xs">{Math.round(confidence * 100)}% ({method})</Badge>;
    }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) handleClose(); else onOpenChange(o); }}>
      <DialogContent className="max-w-4xl max-h-[85vh] overflow-hidden flex flex-col">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <BookOpen className="h-5 w-5" />
            Import Bibliography
          </DialogTitle>
          <DialogDescription>
            Import metadata from RIS, BibTeX, or CSV files and match to existing documents.
          </DialogDescription>
        </DialogHeader>

        {error && (
          <div className="bg-destructive/10 border border-destructive/20 text-destructive px-4 py-3 rounded-lg flex items-center gap-2">
            <AlertCircle className="h-4 w-4 flex-shrink-0" />
            <span className="text-sm">{error}</span>
            <Button variant="ghost" size="sm" onClick={() => setError(null)} className="ml-auto h-6">
              <X className="h-3 w-3" />
            </Button>
          </div>
        )}

        {/* Upload State */}
        {state === "upload" && (
          <div className="flex-1 flex flex-col">
            <div
              className={`flex-1 min-h-[250px] border-2 border-dashed rounded-lg flex flex-col items-center justify-center gap-4 transition-colors cursor-pointer ${
                dragActive ? "border-primary bg-primary/5" : "border-muted-foreground/25 hover:border-primary/50"
              }`}
              onDragEnter={handleDrag}
              onDragLeave={handleDrag}
              onDragOver={handleDrag}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
            >
              {isUploading ? (
                <>
                  <Loader2 className="h-12 w-12 text-primary animate-spin" />
                  <p className="text-sm text-muted-foreground">Parsing {fileName}...</p>
                </>
              ) : (
                <>
                  <FileUp className="h-12 w-12 text-muted-foreground" />
                  <div className="text-center">
                    <p className="font-medium">Drop file here or click to browse</p>
                    <p className="text-sm text-muted-foreground mt-1">
                      Supports RIS, BibTeX, and CSV files
                    </p>
                  </div>
                  <div className="flex gap-2 mt-2">
                    <Badge variant="outline">.ris</Badge>
                    <Badge variant="outline">.bib</Badge>
                    <Badge variant="outline">.csv</Badge>
                  </div>
                </>
              )}
              <input
                ref={fileInputRef}
                type="file"
                accept=".ris,.bib,.csv,.txt"
                className="hidden"
                onChange={handleFileSelect}
              />
            </div>
            
            <div className="mt-4 text-xs text-muted-foreground space-y-1">
              <p><strong>RIS:</strong> Export from Zotero, EndNote, Mendeley</p>
              <p><strong>BibTeX:</strong> Export from LaTeX reference managers</p>
              <p><strong>CSV:</strong> Must have columns: title, authors, year (optional: doi, journal)</p>
            </div>
          </div>
        )}

        {/* Preview State */}
        {state === "preview" && (
          <div className="flex-1 flex flex-col overflow-hidden">
            {/* Summary */}
            <div className="flex items-center gap-4 mb-4">
              <Badge variant="outline" className="text-sm">
                <FileText className="h-3 w-3 mr-1" />
                {fileName}
              </Badge>
              <div className="flex items-center gap-3 text-sm">
                <span className="flex items-center gap-1 text-green-600">
                  <CheckCircle className="h-4 w-4" />
                  {matched.length} matched
                </span>
                <span className="flex items-center gap-1 text-orange-600">
                  <AlertCircle className="h-4 w-4" />
                  {unmatched.length} unmatched
                </span>
                <span className="text-muted-foreground">
                  / {totalEntries} total
                </span>
              </div>
            </div>

            <ScrollArea className="flex-1 -mx-6 px-6">
              <div className="space-y-4">
                {/* Matched Entries */}
                {matched.length > 0 && (
                  <div>
                    <h4 className="font-medium text-sm mb-2 flex items-center gap-2">
                      <CheckCircle className="h-4 w-4 text-green-500" />
                      Matched Entries
                    </h4>
                    <div className="space-y-2">
                      {matched.map((entry) => (
                        <div
                          key={entry.entry_id}
                          className={`p-3 border rounded-lg transition-colors ${
                            selectedForApply.has(entry.entry_id)
                              ? "bg-green-50 dark:bg-green-950/20 border-green-200 dark:border-green-900"
                              : "hover:bg-muted/50"
                          }`}
                        >
                          <div className="flex items-start gap-3">
                            <input
                              type="checkbox"
                              checked={selectedForApply.has(entry.entry_id)}
                              onChange={() => toggleSelectForApply(entry.entry_id)}
                              className="mt-1 h-4 w-4"
                            />
                            <div className="flex-1 min-w-0">
                              <p className="font-medium text-sm line-clamp-2">{entry.entry_title}</p>
                              <p className="text-xs text-muted-foreground mt-0.5">
                                {entry.entry_authors && `${entry.entry_authors}`}
                                {entry.entry_year && ` (${entry.entry_year})`}
                              </p>
                            </div>
                            <div className="flex flex-col items-end gap-1">
                              {getConfidenceBadge(entry.confidence, entry.match_method)}
                              <div className="flex items-center gap-1 text-xs text-muted-foreground">
                                <Link2 className="h-3 w-3" />
                                <span className="truncate max-w-[150px]">{entry.document_filename}</span>
                              </div>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Unmatched Entries */}
                {unmatched.length > 0 && (
                  <div>
                    <h4 className="font-medium text-sm mb-2 flex items-center gap-2">
                      <AlertCircle className="h-4 w-4 text-orange-500" />
                      Unmatched Entries - Select Document to Match
                    </h4>
                    <div className="space-y-2">
                      {unmatched.map((entry) => (
                        <div
                          key={entry.entry_id}
                          className={`p-3 border rounded-lg transition-colors ${
                            manualMatches[entry.entry_id] && selectedForApply.has(entry.entry_id)
                              ? "bg-blue-50 dark:bg-blue-950/20 border-blue-200 dark:border-blue-900"
                              : "hover:bg-muted/50"
                          }`}
                        >
                          <div className="flex items-start gap-3">
                            <input
                              type="checkbox"
                              checked={selectedForApply.has(entry.entry_id)}
                              onChange={() => toggleSelectForApply(entry.entry_id)}
                              disabled={!manualMatches[entry.entry_id]}
                              className="mt-1 h-4 w-4"
                            />
                            <div className="flex-1 min-w-0">
                              <p className="font-medium text-sm line-clamp-2">{entry.entry_title}</p>
                              <p className="text-xs text-muted-foreground mt-0.5">
                                {entry.entry_authors && `${entry.entry_authors}`}
                                {entry.entry_year && ` (${entry.entry_year})`}
                              </p>
                            </div>
                            <div className="w-[220px]">
                              <Select
                                value={manualMatches[entry.entry_id] || ""}
                                onValueChange={(val) => handleManualMatch(entry.entry_id, val)}
                              >
                                <SelectTrigger className="h-8 text-xs">
                                  <SelectValue placeholder="Select document..." />
                                </SelectTrigger>
                                <SelectContent>
                                  {documents.map((doc) => (
                                    <SelectItem key={doc.id} value={doc.id} className="text-xs">
                                      <span className="truncate">
                                        {doc.title || doc.original_filename}
                                      </span>
                                    </SelectItem>
                                  ))}
                                </SelectContent>
                              </Select>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </ScrollArea>
          </div>
        )}

        {/* Applying State */}
        {state === "applying" && (
          <div className="flex-1 flex flex-col items-center justify-center gap-4 py-12">
            <Loader2 className="h-12 w-12 text-primary animate-spin" />
            <p className="text-muted-foreground">Applying metadata to documents...</p>
          </div>
        )}

        <DialogFooter className="mt-4">
          {state === "upload" && (
            <Button variant="outline" onClick={handleClose}>
              Cancel
            </Button>
          )}
          {state === "preview" && (
            <>
              <Button variant="outline" onClick={reset}>
                Upload Different File
              </Button>
              <Button
                onClick={handleApplyMatches}
                disabled={selectedForApply.size === 0 || isApplying}
              >
                {isApplying ? (
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                ) : (
                  <CheckCircle className="h-4 w-4 mr-2" />
                )}
                Apply {selectedForApply.size} Match{selectedForApply.size !== 1 ? "es" : ""}
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
