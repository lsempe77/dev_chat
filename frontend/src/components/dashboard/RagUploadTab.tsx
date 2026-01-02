"use client";

import { useState, useCallback } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { 
  Upload, 
  FileText, 
  X, 
  Folder,
  CheckCircle,
  AlertCircle,
  Loader2,
  Copy
} from "lucide-react";

interface FileToUpload {
  file: File;
  status: "pending" | "uploading" | "completed" | "duplicate" | "error";
  progress: number;
  r2Key?: string;
  isDuplicate?: boolean;
  message?: string;
  error?: string;
}

interface RagUploadTabProps {
  ragId: string;
  accessToken: string;
  apiBaseUrl: string;
  onUploadComplete?: () => void;
}

// Batch size for uploads (to avoid Chrome's connection limit)
const BATCH_SIZE = 10;

export function RagUploadTab({ ragId, accessToken, apiBaseUrl, onUploadComplete }: RagUploadTabProps) {
  const [files, setFiles] = useState<FileToUpload[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [isDragging, setIsDragging] = useState(false);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    
    // Only accept PDFs
    const droppedFiles = Array.from(e.dataTransfer.files).filter(
      file => file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf")
    );
    
    const rejectedCount = e.dataTransfer.files.length - droppedFiles.length;
    if (rejectedCount > 0) {
      alert(`${rejectedCount} file(s) rejected. Only PDF files are supported.`);
    }
    
    addFiles(droppedFiles);
  }, []);

  const handleFileSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      const allFiles = Array.from(e.target.files);
      // Process async to avoid blocking UI with large folders
      setTimeout(() => {
        const pdfFiles = allFiles.filter(
          file => file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf")
        );
        const skippedCount = allFiles.length - pdfFiles.length;
        if (skippedCount > 0) {
          alert(`${skippedCount} non-PDF file(s) were skipped. Only PDF files are supported.`);
        }
        addFiles(pdfFiles);
      }, 0);
    }
  }, []);

  const addFiles = (newFiles: File[]) => {
    const fileObjects: FileToUpload[] = newFiles.map(file => ({
      file,
      status: "pending",
      progress: 0,
    }));
    setFiles(prev => [...prev, ...fileObjects]);
  };

  const removeFile = (index: number) => {
    setFiles(prev => prev.filter((_, i) => i !== index));
  };

  const clearCompleted = () => {
    setFiles(prev => prev.filter(f => f.status !== "completed" && f.status !== "duplicate"));
  };

  const uploadFiles = async () => {
    setIsUploading(true);
    
    // Get pending files and their indices
    const pendingIndices = files
      .map((f, i) => ({ file: f, index: i }))
      .filter(item => item.file.status === "pending");
    
    // Process in batches to avoid Chrome's connection limit
    for (let batchStart = 0; batchStart < pendingIndices.length; batchStart += BATCH_SIZE) {
      const batch = pendingIndices.slice(batchStart, batchStart + BATCH_SIZE);
      
      // Upload batch sequentially (one at a time to be safe)
      for (const { file: fileObj, index } of batch) {
        // Update status to uploading
        setFiles(prev => prev.map((f, idx) => 
          idx === index ? { ...f, status: "uploading" as const, progress: 10 } : f
        ));
        
        try {
          // Simulated progress updates
          const progressInterval = setInterval(() => {
            setFiles(prev => prev.map((f, idx) => 
              idx === index && f.progress < 90 ? { ...f, progress: f.progress + 10 } : f
            ));
          }, 200);
          
          // Call real API
          const formData = new FormData();
          formData.append("file", fileObj.file);
          
          const response = await fetch(`${apiBaseUrl}/rags/${ragId}/documents/upload`, {
            method: "POST",
            headers: {
              Authorization: `Bearer ${accessToken}`,
            },
            body: formData,
          });
          
          clearInterval(progressInterval);
          
          if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || `Upload failed: ${response.status}`);
          }
          
          const result = await response.json();
          
          // Check if it was a duplicate
          if (result.is_duplicate) {
            setFiles(prev => prev.map((f, idx) => 
              idx === index ? { 
                ...f, 
                status: "duplicate" as const, 
                progress: 100,
                r2Key: result.r2_key,
                isDuplicate: true,
                message: result.message || "Document already exists",
              } : f
            ));
          } else {
            setFiles(prev => prev.map((f, idx) => 
              idx === index ? { 
                ...f, 
                status: "completed" as const, 
                progress: 100,
                r2Key: result.r2_key,
              } : f
            ));
          }
          
        } catch (error) {
          setFiles(prev => prev.map((f, idx) => 
            idx === index ? { 
              ...f, 
              status: "error" as const, 
              error: error instanceof Error ? error.message : String(error) 
            } : f
          ));
        }
      }
    }
    
    setIsUploading(false);
    onUploadComplete?.();
  };

  const pendingCount = files.filter(f => f.status === "pending").length;
  const completedCount = files.filter(f => f.status === "completed").length;
  const duplicateCount = files.filter(f => f.status === "duplicate").length;
  const errorCount = files.filter(f => f.status === "error").length;

  return (
    <div className="grid gap-6 md:grid-cols-2">
      {/* Upload Zone */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Upload className="h-5 w-5" />
            Upload Documents
          </CardTitle>
          <CardDescription>
            Drag and drop PDF files or select from your computer. 
            Duplicate files are automatically detected.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Drop Zone */}
          <div
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            className={`
              border-2 border-dashed rounded-lg p-8 text-center transition-colors
              ${isDragging 
                ? "border-primary bg-primary/5" 
                : "border-muted-foreground/25 hover:border-muted-foreground/50"
              }
            `}
          >
            <Upload className="h-10 w-10 mx-auto mb-4 text-muted-foreground" />
            <p className="text-sm text-muted-foreground mb-2">
              Drop PDF files here (only PDFs accepted)
            </p>
            <p className="text-xs text-muted-foreground mb-4">
              or
            </p>
            <input
              type="file"
              id="file-upload"
              multiple
              accept=".pdf,application/pdf"
              onChange={handleFileSelect}
              className="hidden"
            />
            <label htmlFor="file-upload">
              <Button variant="outline" asChild>
                <span className="cursor-pointer">
                  <FileText className="h-4 w-4 mr-2" />
                  Select Files
                </span>
              </Button>
            </label>
          </div>

          {/* Folder Upload */}
          <div className="flex gap-2">
            <input
              type="file"
              id="folder-upload"
              // @ts-expect-error webkitdirectory is not in React types but widely supported
              webkitdirectory=""
              directory=""
              multiple
              onChange={handleFileSelect}
              className="hidden"
            />
            <label htmlFor="folder-upload" className="flex-1">
              <Button variant="outline" size="sm" className="w-full" asChild>
                <span className="cursor-pointer">
                  <Folder className="h-4 w-4 mr-2" />
                  Select Folder
                </span>
              </Button>
            </label>
          </div>
          
          {/* Batch info */}
          <p className="text-xs text-muted-foreground">
            Files are uploaded in batches of {BATCH_SIZE} to avoid browser limits.
          </p>
        </CardContent>
      </Card>

      {/* Upload Queue */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="flex items-center gap-2">
              <FileText className="h-5 w-5" />
              Upload Queue
              {files.length > 0 && (
                <Badge variant="secondary">{files.length}</Badge>
              )}
            </CardTitle>
            {(completedCount > 0 || duplicateCount > 0) && (
              <Button variant="ghost" size="sm" onClick={clearCompleted}>
                Clear completed
              </Button>
            )}
          </div>
          <CardDescription>
            {pendingCount > 0 
              ? `${pendingCount} file${pendingCount !== 1 ? "s" : ""} ready to upload`
              : duplicateCount > 0
                ? `${duplicateCount} duplicate${duplicateCount !== 1 ? "s" : ""} detected`
                : "No files in queue"
            }
          </CardDescription>
        </CardHeader>
        <CardContent>
          {files.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">
              <FileText className="h-10 w-10 mx-auto mb-2 opacity-50" />
              <p className="text-sm">No files added yet</p>
            </div>
          ) : (
            <>
              <ScrollArea className="h-[300px] pr-4">
                <div className="space-y-2">
                  {files.map((f, index) => (
                    <div
                      key={`${f.file.name}-${index}`}
                      className="flex items-center gap-3 p-2 rounded-lg border bg-card"
                    >
                      <FileText className="h-4 w-4 text-muted-foreground shrink-0" />
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium truncate">
                          {f.file.name}
                        </p>
                        <p className="text-xs text-muted-foreground">
                          {(f.file.size / 1024 / 1024).toFixed(2)} MB
                        </p>
                        {f.status === "uploading" && (
                          <div className="w-full bg-muted rounded-full h-1 mt-1">
                            <div 
                              className="bg-primary h-1 rounded-full transition-all"
                              style={{ width: `${f.progress}%` }}
                            />
                          </div>
                        )}
                        {f.status === "error" && f.error && (
                          <p className="text-xs text-red-500 truncate">{f.error}</p>
                        )}
                      </div>
                      <div className="shrink-0 flex items-center gap-2">
                        {f.status === "pending" && (
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-6 w-6"
                            onClick={() => removeFile(index)}
                          >
                            <X className="h-3 w-3" />
                          </Button>
                        )}
                        {f.status === "uploading" && (
                          <Loader2 className="h-4 w-4 animate-spin text-primary" />
                        )}
                        {f.status === "completed" && (
                          <CheckCircle className="h-4 w-4 text-green-500" />
                        )}
                        {f.status === "duplicate" && (
                          <Badge variant="secondary" className="text-xs">
                            <Copy className="h-3 w-3 mr-1" />
                            Exists
                          </Badge>
                        )}
                        {f.status === "error" && (
                          <AlertCircle className="h-4 w-4 text-red-500" />
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </ScrollArea>
              
              {/* Summary */}
              {(completedCount > 0 || duplicateCount > 0 || errorCount > 0) && (
                <Alert className="mt-4">
                  <AlertDescription className="text-sm">
                    {completedCount > 0 && (
                      <span className="text-green-600 mr-3">✓ {completedCount} uploaded</span>
                    )}
                    {duplicateCount > 0 && (
                      <span className="text-yellow-600 mr-3">⚠ {duplicateCount} duplicates</span>
                    )}
                    {errorCount > 0 && (
                      <span className="text-red-600">✗ {errorCount} failed</span>
                    )}
                  </AlertDescription>
                </Alert>
              )}
              
              <div className="mt-4 pt-4 border-t flex gap-2">
                <Button
                  onClick={uploadFiles}
                  disabled={isUploading || pendingCount === 0}
                  className="flex-1"
                >
                  {isUploading ? (
                    <>
                      <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                      Uploading...
                    </>
                  ) : (
                    <>
                      <Upload className="h-4 w-4 mr-2" />
                      Upload {pendingCount} file{pendingCount !== 1 ? "s" : ""}
                    </>
                  )}
                </Button>
                <Button
                  variant="outline"
                  onClick={() => setFiles([])}
                  disabled={isUploading}
                >
                  Clear All
                </Button>
              </div>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
