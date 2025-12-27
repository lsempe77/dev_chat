"use client";

import { useState, useCallback } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Upload,
  FileText,
  Loader2,
  CheckCircle,
  AlertTriangle,
  X,
  Book,
} from "lucide-react";
import {
  previewBibliographyImport,
  confirmBibliographyImport,
  type ImportedEntry,
  type ImportPreviewResponse,
} from "@/lib/admin-api";

interface BibliographyImportDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onImportComplete: () => void;
}

export function BibliographyImportDialog({
  open,
  onOpenChange,
  onImportComplete,
}: BibliographyImportDialogProps) {
  const [file, setFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [isImporting, setIsImporting] = useState(false);
  const [preview, setPreview] = useState<ImportPreviewResponse | null>(null);
  const [selectedEntries, setSelectedEntries] = useState<Set<number>>(new Set());
  const [skipDuplicates, setSkipDuplicates] = useState(true);
  const [mergeDuplicates, setMergeDuplicates] = useState(false);
  const [enrichFromDoi, setEnrichFromDoi] = useState(true);
  const [importResult, setImportResult] = useState<{
    imported: number;
    skipped: number;
    updated: number;
    enriched: number;
    errors: string[];
  } | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Reset state when dialog closes
  const handleOpenChange = (newOpen: boolean) => {
    if (!newOpen) {
      setFile(null);
      setPreview(null);
      setSelectedEntries(new Set());
      setImportResult(null);
      setError(null);
      setIsUploading(false);  // Reset loading state
      setIsImporting(false);  // Reset loading state
    }
    onOpenChange(newOpen);
  };

  // Handle file selection
  const handleFileSelect = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = e.target.files?.[0];
    if (!selectedFile) return;

    setFile(selectedFile);
    setError(null);
    setPreview(null);
    setImportResult(null);
    setIsUploading(true);

    try {
      const result = await previewBibliographyImport(selectedFile);
      setPreview(result);
      // Select all non-duplicate entries by default
      const nonDuplicateIndices = new Set(
        result.entries
          .map((entry, idx) => (!result.duplicates.includes(entry.title) ? idx : -1))
          .filter((idx) => idx >= 0)
      );
      setSelectedEntries(nonDuplicateIndices);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to parse file");
    } finally {
      setIsUploading(false);
    }
  }, []);

  // Toggle entry selection
  const toggleEntry = (index: number) => {
    const newSelected = new Set(selectedEntries);
    if (newSelected.has(index)) {
      newSelected.delete(index);
    } else {
      newSelected.add(index);
    }
    setSelectedEntries(newSelected);
  };

  // Select/deselect all
  const toggleAll = () => {
    if (selectedEntries.size === preview?.entries.length) {
      setSelectedEntries(new Set());
    } else {
      setSelectedEntries(new Set(preview?.entries.map((_, idx) => idx) || []));
    }
  };

  // Import selected entries
  const handleImport = async () => {
    if (!preview) return;

    const entriesToImport = preview.entries.filter((_, idx) => selectedEntries.has(idx));
    if (entriesToImport.length === 0) {
      setError("No entries selected for import");
      return;
    }

    setIsImporting(true);
    setError(null);

    try {
      const result = await confirmBibliographyImport(entriesToImport, {
        skipDuplicates,
        mergeDuplicates,
        enrichFromDoi,
      });
      setImportResult({
        imported: result.imported_count,
        skipped: result.skipped_count,
        updated: result.updated_count,
        enriched: result.enriched_count,
        errors: result.errors,
      });
      
      if (result.imported_count > 0 || result.updated_count > 0) {
        onImportComplete();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Import failed");
    } finally {
      setIsImporting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="max-w-5xl w-[90vw] h-[80vh] flex flex-col overflow-hidden">
        <DialogHeader className="shrink-0">
          <DialogTitle className="flex items-center gap-2">
            <Book className="h-5 w-5" />
            Import Bibliography
          </DialogTitle>
          <DialogDescription>
            Import references from RIS, BibTeX, or CSV files
          </DialogDescription>
        </DialogHeader>

        {/* Success state */}
        {importResult && (
          <div className="flex-1 flex flex-col items-center justify-center py-8">
            <CheckCircle className="h-16 w-16 text-green-500 mb-4" />
            <h3 className="text-xl font-semibold mb-2">Import Complete</h3>
            <div className="text-muted-foreground mb-4 text-center space-y-1">
              <p>
                <span className="font-semibold text-green-600">{importResult.imported}</span> entries imported
                {importResult.updated > 0 && (
                  <>, <span className="font-semibold text-blue-600">{importResult.updated}</span> updated</>
                )}
                {importResult.skipped > 0 && (
                  <>, <span className="text-muted-foreground">{importResult.skipped}</span> skipped</>
                )}
              </p>
              {importResult.enriched > 0 && (
                <p className="text-sm text-blue-600">
                  ✓ {importResult.enriched} entries enriched with DOI metadata
                </p>
              )}
            </div>
            {importResult.errors.length > 0 && (
              <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4 max-w-md">
                <h4 className="font-medium text-yellow-800 mb-2">Warnings:</h4>
                <ul className="text-sm text-yellow-700 space-y-1">
                  {importResult.errors.slice(0, 5).map((err, idx) => (
                    <li key={idx}>• {err}</li>
                  ))}
                  {importResult.errors.length > 5 && (
                    <li>...and {importResult.errors.length - 5} more</li>
                  )}
                </ul>
              </div>
            )}
            <Button className="mt-6" onClick={() => handleOpenChange(false)}>
              Close
            </Button>
          </div>
        )}

        {/* File upload state */}
        {!importResult && !preview && (
          <div className="flex-1 flex flex-col items-center justify-center py-12">
            <div className="border-2 border-dashed border-muted-foreground/25 rounded-lg p-12 text-center">
              {isUploading ? (
                <Loader2 className="h-12 w-12 animate-spin text-muted-foreground mx-auto mb-4" />
              ) : (
                <Upload className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
              )}
              <h3 className="text-lg font-medium mb-2">
                {isUploading ? "Parsing file..." : "Drop your file here"}
              </h3>
              <p className="text-sm text-muted-foreground mb-4">
                Supports .ris, .bib, and .csv files
              </p>
              <Label htmlFor="file-upload" className="cursor-pointer">
                <Button variant="outline" disabled={isUploading} asChild>
                  <span>
                    <FileText className="h-4 w-4 mr-2" />
                    Choose File
                  </span>
                </Button>
                <Input
                  id="file-upload"
                  type="file"
                  accept=".ris,.bib,.csv"
                  className="hidden"
                  onChange={handleFileSelect}
                  disabled={isUploading}
                />
              </Label>
            </div>
          </div>
        )}

        {/* Preview state */}
        {!importResult && preview && (
          <div className="flex flex-col flex-1 min-h-0 overflow-hidden">
            {/* Header with stats */}
            <div className="shrink-0 flex items-center justify-between py-2 border-b">
              <div className="flex items-center gap-4">
                <Badge variant="outline">
                  {preview.parsed_count} entries found
                </Badge>
                {preview.duplicates.length > 0 && (
                  <Badge variant="secondary" className="text-yellow-600">
                    <AlertTriangle className="h-3 w-3 mr-1" />
                    {preview.duplicates.length} duplicates
                  </Badge>
                )}
                <span className="text-sm text-muted-foreground">
                  {selectedEntries.size} selected
                </span>
              </div>
            </div>

            {/* Import options */}
            <div className="shrink-0 flex flex-wrap items-center gap-4 py-3 px-1 border-b bg-muted/30">
              <div className="flex items-center gap-2">
                <Checkbox
                  id="skip-duplicates"
                  checked={skipDuplicates && !mergeDuplicates}
                  disabled={mergeDuplicates}
                  onCheckedChange={(checked: boolean | "indeterminate") => setSkipDuplicates(checked === true)}
                />
                <Label htmlFor="skip-duplicates" className="text-sm">
                  Skip duplicates
                </Label>
              </div>
              <div className="flex items-center gap-2">
                <Checkbox
                  id="merge-duplicates"
                  checked={mergeDuplicates}
                  onCheckedChange={(checked: boolean | "indeterminate") => {
                    setMergeDuplicates(checked === true);
                    if (checked) setSkipDuplicates(false);
                  }}
                />
                <Label htmlFor="merge-duplicates" className="text-sm">
                  Update existing with richer metadata
                </Label>
              </div>
              <div className="flex items-center gap-2">
                <Checkbox
                  id="enrich-doi"
                  checked={enrichFromDoi}
                  onCheckedChange={(checked: boolean | "indeterminate") => setEnrichFromDoi(checked === true)}
                />
                <Label htmlFor="enrich-doi" className="text-sm">
                  Enrich from DOI (CrossRef)
                </Label>
              </div>
            </div>

            <ScrollArea className="flex-1 min-h-0 overflow-auto">
              <div className="space-y-2 py-2 pr-4">
                {/* Select all header */}
                <div className="flex items-center gap-2 py-2 border-b sticky top-0 bg-background z-10">
                  <Checkbox
                    checked={selectedEntries.size === preview.entries.length}
                    onCheckedChange={toggleAll}
                  />
                  <span className="text-sm font-medium">Select All</span>
                </div>

                {preview.entries.map((entry, idx) => {
                  const isDuplicate = preview.duplicates.includes(entry.title);
                  return (
                    <div
                      key={idx}
                      className={`flex items-start gap-3 p-3 rounded-lg border ${
                        isDuplicate ? "bg-yellow-50 border-yellow-200" : "bg-background"
                      }`}
                    >
                      <Checkbox
                        checked={selectedEntries.has(idx)}
                        onCheckedChange={() => toggleEntry(idx)}
                      />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <span className="font-medium truncate">{entry.title}</span>
                          {isDuplicate && (
                            <Badge variant="secondary" className="text-yellow-600 shrink-0">
                              Duplicate
                            </Badge>
                          )}
                        </div>
                        <div className="flex flex-wrap gap-2 text-sm text-muted-foreground">
                          {entry.authors.length > 0 && (
                            <span>
                              {entry.authors.slice(0, 2).join(", ")}
                              {entry.authors.length > 2 ? " et al." : ""}
                            </span>
                          )}
                          {entry.year && <span>• {entry.year}</span>}
                          {entry.journal && <span>• {entry.journal}</span>}
                          {entry.doi && (
                            <Badge variant="outline" className="text-xs">
                              DOI
                            </Badge>
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </ScrollArea>

            {preview.errors.length > 0 && (
              <div className="shrink-0 bg-red-50 border border-red-200 rounded-lg p-3 text-sm text-red-700">
                <strong>Parse errors:</strong> {preview.errors.join(", ")}
              </div>
            )}

            {/* Footer - always visible at bottom */}
            <div className="shrink-0 flex justify-end gap-2 border-t pt-4 mt-2">
              <Button variant="outline" onClick={() => setPreview(null)}>
                Back
              </Button>
              <Button
                onClick={handleImport}
                disabled={isImporting || selectedEntries.size === 0}
              >
                {isImporting ? (
                  <>
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    Importing...
                  </>
                ) : (
                  <>Import {selectedEntries.size} Entries</>
                )}
              </Button>
            </div>
          </div>
        )}

        {error && (
          <div className="shrink-0 flex items-center gap-2 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700">
            <AlertTriangle className="h-4 w-4" />
            {error}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
